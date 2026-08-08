import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { basename, resolve } from 'node:path';

const source = resolve(process.env.SOURCE_WORKFLOW_EXPORT || process.argv[2] || '/private/tmp/adflow-current-n8n-workflows.json');
const outputDirectory = resolve(process.env.PUBLIC_WORKFLOW_DIR || 'n8n-workflows/public');

const selected = [
  {
    name: '大海浮光 AIGC｜03 脚本到视频任务',
    file: '03-script-to-storyboard.json',
    publicName: '大海浮光 AIGC｜03 脚本到导演分镜（公开模板）',
  },
  {
    name: '大海浮光 AIGC｜04 视频任务到成片',
    file: '04-video-generation.json',
    publicName: '大海浮光 AIGC｜04 视频生成与成片（公开模板）',
  },
  {
    name: '大海浮光 AIGC｜05 分镜图生成',
    file: '05-storyboard-images.json',
    publicName: '大海浮光 AIGC｜05 分镜图生成（公开模板）',
  },
];

const secretKeyPattern = /(authorization|api[_-]?key|access[_-]?token|app[_-]?secret|client[_-]?secret|password)/i;
const resourceKeyPattern = /^(app[_-]?id|app[_-]?token|base[_-]?token|table[_-]?id|bucket|bucketName)$/i;

function sanitizeString(value, key = '') {
  if (!value) return value;
  if (secretKeyPattern.test(key) && !value.includes('{{') && !value.includes('$env')) {
    return 'CONFIGURE_IN_N8N_CREDENTIALS';
  }
  if (resourceKeyPattern.test(key) && !value.includes('{{') && !value.includes('$env')) {
    return `YOUR_${key.replace(/([a-z])([A-Z])/g, '$1_$2').replace(/-/g, '_').toUpperCase()}`;
  }

  const sanitized = value
    .replace(/Bearer\s+(?!\{\{|\$env|YOUR_)[A-Za-z0-9._~+/-]{12,}/gi, 'Bearer CONFIGURE_IN_N8N_CREDENTIALS')
    .replace(/(["']app_id["']\s*:\s*["'])[^"']+(["'])/gi, '$1YOUR_FEISHU_APP_ID$2')
    .replace(/(["']app_secret["']\s*:\s*["'])[^"']+(["'])/gi, '$1CONFIGURE_IN_N8N_CREDENTIALS$2')
    .replace(/\/apps\/[A-Za-z0-9_-]+\/tables\/[A-Za-z0-9_-]+/g, '/apps/YOUR_FEISHU_APP_TOKEN/tables/YOUR_FEISHU_TABLE_ID')
    .replace(/\/apps\/[A-Za-z0-9_-]+/g, '/apps/YOUR_FEISHU_APP_TOKEN')
    .replace(/\btbl[A-Za-z0-9_-]{8,}\b/g, 'YOUR_FEISHU_TABLE_ID')
    .replace(/\b[A-Za-z0-9_-]{8,}\.tos-cn-[A-Za-z0-9-]+\.volces\.com\b/g, 'YOUR_BUCKET.tos-cn-region.volces.com')
    .replace(/\/Users\/cuc2023\/[^\s"'`\\]+/g, '/path/to/local/runtime')
    .replace(/https:\/\/api\.deepseek\.com\/chat\/completions/g, '={{ $env.DEEPSEEK_API_URL || "https://api.deepseek.com/chat/completions" }}');

  // Repair Python-style literals accidentally pasted into n8n JavaScript Code nodes.
  return key === 'jsCode'
    ? sanitized.replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false').replace(/\bNone\b/g, 'null')
    : sanitized;
}

function sanitize(value, key = '') {
  if (Array.isArray(value)) return value.map((item) => sanitize(item, key));
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([childKey]) => childKey !== 'webhookId')
        .map(([childKey, child]) => {
          if (childKey === 'credentials' && child && typeof child === 'object') {
            const credentials = Object.fromEntries(
              Object.entries(child).map(([type, credential]) => [
                type,
                { id: `YOUR_${type.toUpperCase()}_CREDENTIAL_ID`, name: `Configure ${type} credential` },
              ]),
            );
            return [childKey, credentials];
          }
          return [childKey, sanitize(child, childKey)];
        }),
    );
  }
  return typeof value === 'string' ? sanitizeString(value, key) : value;
}

const parsed = JSON.parse(await readFile(source, 'utf8'));
const workflows = Array.isArray(parsed) ? parsed : [parsed];
await mkdir(outputDirectory, { recursive: true });

for (const definition of selected) {
  const workflow = workflows.find((item) => item.name === definition.name);
  if (!workflow) throw new Error(`Workflow not found in ${basename(source)}: ${definition.name}`);
  const publicWorkflow = {
    name: definition.publicName,
    nodes: sanitize(workflow.nodes || []),
    connections: sanitize(workflow.connections || {}),
    settings: sanitize({ ...(workflow.settings || {}), executionOrder: 'v1' }),
    active: false,
    meta: {
      publicTemplate: true,
      sourceWorkflowName: definition.name,
      note: 'Bind your own credentials and replace resource placeholders before publishing.',
    },
  };
  await writeFile(resolve(outputDirectory, definition.file), `${JSON.stringify(publicWorkflow, null, 2)}\n`);
  console.log(`Wrote ${definition.file}`);
}

import { readdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const roots = [
  'README.md',
  '.env.example',
  'docs/ARCHITECTURE.md',
  'docs/SETUP.md',
  'docs/WORKFLOW_CONTRACTS.md',
  'frontend/server.mjs',
  'frontend/open-design.html',
];

for (const file of await readdir('n8n-workflows/public')) {
  if (file.endsWith('.json')) roots.push(`n8n-workflows/public/${file}`);
}

const patterns = [
  { name: 'private bearer token', value: /Bearer\s+(?!CONFIGURE_|YOUR_|\{\{|\$env)[A-Za-z0-9._~+/-]{16,}/i },
  { name: 'private API key', value: /\b(?:sk|ark)-[A-Za-z0-9_-]{16,}\b/i },
  { name: 'Feishu application ID', value: /\bcli_[A-Za-z0-9_-]{12,}\b/ },
  { name: 'inline application secret', value: /["']app_secret["']\s*:\s*["'](?!CONFIGURE_|YOUR_)[^"']{12,}["']/i },
  { name: 'personal absolute path', value: /\/Users\/cuc2023\// },
  { name: 'Feishu app token', value: /\/apps\/(?!YOUR_)[A-Za-z0-9_-]{20,}/ },
  { name: 'Feishu table ID', value: /\btbl[A-Za-z0-9_-]{8,}\b/ },
  { name: 'private object storage host', value: /\b(?!YOUR_BUCKET)[A-Za-z0-9_-]{12,}\.tos-cn-[A-Za-z0-9-]+\.volces\.com\b/ },
];

const failures = [];
for (const file of roots) {
  const text = await readFile(resolve(file), 'utf8');
  for (const pattern of patterns) {
    if (pattern.value.test(text)) failures.push(`${file}: ${pattern.name}`);
  }
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log(`No known secrets found in ${roots.length} public files.`);

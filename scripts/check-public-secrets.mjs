import { execFile } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const binaryExtensions = new Set([
  '.7z', '.avi', '.gif', '.ico', '.jpeg', '.jpg', '.mov', '.mp3', '.mp4',
  '.pdf', '.png', '.tar', '.webm', '.webp', '.woff', '.woff2', '.zip',
]);

const { stdout } = await execFileAsync(
  'git',
  ['ls-files', '--cached', '--others', '--exclude-standard', '-z'],
  { encoding: 'utf8' },
);
const files = stdout.split('\0').filter(Boolean);
const failures = [];

if (!files.includes('.env.example')) failures.push('缺少 .env.example 配置模板');
if (!files.includes('.gitignore')) failures.push('缺少 .gitignore 保护规则');

const forbiddenFiles = files.filter((file) => {
  const normalized = file.replaceAll('\\', '/');
  return normalized === '.env'
    || /(^|\/)\.env\.(?!example$)/.test(normalized)
    || /(^|\/)(?:\.n8n|node_modules)(?:\/|$)/.test(normalized)
    || /\.(?:sqlite(?:-[^/]+)?|db(?:-[^/]+)?)$/i.test(normalized);
});
for (const file of forbiddenFiles) failures.push(`${file}: 不应提交本地配置或数据库文件`);

const patterns = [
  { name: 'private bearer token', value: /Bearer\s+(?!CONFIGURE_|YOUR_|\{\{|\$env)[A-Za-z0-9._~+/-]{16,}/i },
  { name: 'private API key', value: /\b(?:sk|ark)-[A-Za-z0-9_-]{16,}\b/i },
  { name: 'Feishu application ID', value: /\bcli_[A-Za-z0-9_-]{12,}\b/ },
  { name: 'inline application secret', value: /["']app_secret["']\s*:\s*["'](?!CONFIGURE_|YOUR_)[^"']{12,}["']/i },
  { name: 'personal absolute path', value: /\/(?:Users|home)\/(?!YOUR_|<)[A-Za-z0-9._-]+(?:\/|$)/ },
  { name: 'Feishu app token', value: /\/apps\/(?!YOUR_)[A-Za-z0-9_-]{20,}/ },
  { name: 'Feishu table ID', value: /\btbl[A-Za-z0-9_-]{8,}\b/ },
  { name: 'private object storage host', value: /\b(?!YOUR_BUCKET)[A-Za-z0-9_-]{12,}\.tos-cn-[A-Za-z0-9-]+\.volces\.com\b/ },
];

for (const file of files) {
  if (binaryExtensions.has(extname(file).toLowerCase())) continue;
  let buffer;
  try {
    buffer = await readFile(file);
  } catch (error) {
    failures.push(`${file}: 无法读取（${error.message}）`);
    continue;
  }
  if (buffer.includes(0)) continue;
  const source = buffer.toString('utf8');
  for (const pattern of patterns) {
    if (pattern.value.test(source)) failures.push(`${file}: ${pattern.name}`);
  }
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log(`No known secrets found in ${files.length} tracked or unignored text files.`);

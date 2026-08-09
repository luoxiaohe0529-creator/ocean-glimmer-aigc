import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const directory = mkdtempSync(join(tmpdir(), 'ocean-tos-credential-'));
const output = join(directory, 'credentials.json');
execFileSync('n8n', ['export:credentials', '--all', '--decrypted', `--output=${output}`], { stdio: 'ignore' });
const credentials = JSON.parse(readFileSync(output, 'utf8'));
const credential = credentials.find((item) => item.name === '火山引擎') || credentials.find((item) => item.name === '火山 TOS');
if (!credential) throw new Error('n8n 中找不到“火山引擎”或“火山 TOS”凭据');
const data = typeof credential.data === 'string' ? JSON.parse(credential.data) : credential.data;
if (!data?.accessKeyId || !data?.secretAccessKey) throw new Error('TOS 凭据缺少 Access Key 或 Secret Key');

const envPath = new URL('../.env', import.meta.url);
let env = readFileSync(envPath, 'utf8');
const setValue = (name, value) => {
  const line = `${name}=${String(value).replace(/[\r\n]/g, '')}`;
  const pattern = new RegExp(`^${name}=.*$`, 'm');
  env = pattern.test(env) ? env.replace(pattern, line) : `${env.replace(/\s*$/, '')}\n${line}\n`;
};
setValue('TOS_ACCESS_KEY_ID', data.accessKeyId);
setValue('TOS_SECRET_ACCESS_KEY', data.secretAccessKey);
writeFileSync(envPath, env, { mode: 0o600 });
console.log('TOS 凭据已安全迁移到本地 .env（未显示密钥）。');

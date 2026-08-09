import { copyFileSync, existsSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import Database from 'better-sqlite3';

const root = path.resolve(import.meta.dirname, '..');
const sourcePath = path.join(root, 'n8n-workflows/generated/live-stage4-providers.json');
const dbPath = process.env.N8N_DB_PATH || path.join(process.env.HOME || '', '.n8n/database.sqlite');

if (!existsSync(sourcePath)) throw new Error(`找不到工作流模板: ${sourcePath}`);
if (!existsSync(dbPath)) throw new Error(`找不到 n8n 数据库: ${dbPath}`);
try {
  execFileSync('lsof', ['-tiTCP:5678', '-sTCP:LISTEN'], { stdio: 'ignore' });
  throw new Error('n8n 仍在运行。请在 n8n 终端按 Control+C 后重新执行。');
} catch (error) {
  if (error.message.includes('仍在运行')) throw error;
}

const workflow = JSON.parse(readFileSync(sourcePath, 'utf8'))[0];
const stamp = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14);
const backupPath = `${dbPath}.before-stage4-recovery-${stamp}`;
copyFileSync(dbPath, backupPath);

const db = new Database(dbPath);
const row = db.prepare('SELECT id, versionCounter FROM workflow_entity WHERE id = ?').get(workflow.id);
if (!row) {
  db.close();
  throw new Error(`n8n 中找不到 Stage 4 工作流: ${workflow.id}`);
}

const nodes = JSON.stringify(workflow.nodes);
const connections = JSON.stringify(workflow.connections);
db.prepare('UPDATE workflow_entity SET nodes = ?, connections = ?, description = ?, updatedAt = CURRENT_TIMESTAMP, versionCounter = ? WHERE id = ?')
  .run(nodes, connections, workflow.description || '', Number(row.versionCounter || 1) + 1, row.id);

const latest = db.prepare('SELECT versionId FROM workflow_history WHERE workflowId = ? ORDER BY createdAt DESC LIMIT 1').get(row.id);
const published = db.prepare('SELECT publishedVersionId FROM workflow_published_version WHERE workflowId = ?').get(row.id);
const versions = [...new Set([latest?.versionId, published?.publishedVersionId].filter(Boolean))];
for (const versionId of versions) {
  db.prepare('UPDATE workflow_history SET nodes = ?, connections = ?, updatedAt = CURRENT_TIMESTAMP WHERE versionId = ?')
    .run(nodes, connections, versionId);
}
db.close();

console.log(`已恢复 Seedance 主线路并安装完整前端回写: ${workflow.name}`);
console.log(`数据库备份: ${backupPath}`);
console.log('现在执行 n8n start。');

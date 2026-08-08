import { copyFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import Database from 'better-sqlite3';
import { stage4PrepCode } from './stage4-prep-code.mjs';

const root = path.resolve(import.meta.dirname, '..');
function patchWorkflow(parsed) {
  const workflow = Array.isArray(parsed) ? parsed[0] : parsed;
  if (!workflow || !Array.isArray(workflow.nodes)) throw new Error('不是有效的 n8n 工作流 JSON');

  const prep = workflow.nodes.find((node) => /^整理.*参数/.test(node.name));
  const seedance = workflow.nodes.find((node) => node.name === 'Seedance 2.0｜创建15秒视频');
  const seedanceStatus = workflow.nodes.find((node) => node.name === 'Seedance 2.0｜查询生成状态');
  if (!prep?.parameters?.jsCode) throw new Error('找不到 Stage 4 参数整理节点');
  if (!seedance?.parameters) throw new Error('找不到 Seedance 创建节点');
  if (!seedanceStatus?.parameters) throw new Error('找不到 Seedance 状态查询节点');

  prep.parameters.jsCode = stage4PrepCode();

  const body = String(seedance.parameters.jsonBody || '');
  const dynamicBody = body.replace(/resolution:\s*["']480p["']/, 'resolution: $json.resolution || "480p"');
  if (dynamicBody === body && !body.includes('resolution: $json.resolution')) {
    throw new Error('Seedance 节点没有找到固定分辨率配置');
  }
  seedance.parameters.jsonBody = dynamicBody;

  // 查询是幂等 GET；对瞬时连接重置重试，避免已创建的任务被误判为整条流程失败。
  seedanceStatus.retryOnFail = true;
  seedanceStatus.maxTries = 4;
  seedanceStatus.waitBetweenTries = 10000;
  return Array.isArray(parsed) ? [workflow] : workflow;
}

function patchFile(filePath) {
  if (!existsSync(filePath)) return false;
  const parsed = JSON.parse(readFileSync(filePath, 'utf8'));
  const patched = patchWorkflow(parsed);
  writeFileSync(filePath, `${JSON.stringify(patched, null, 2)}\n`);
  console.log(`已更新工作流模板: ${filePath}`);
  return true;
}

const localFiles = [
  path.join(root, 'n8n-workflows/public/04-video-generation.json'),
  path.join(root, 'n8n-workflows/generated/live-stage4-providers.json'),
];
for (const file of localFiles) patchFile(file);

if (process.argv.includes('--live')) {
  const dbPath = process.env.N8N_DB_PATH || path.join(process.env.HOME || '', '.n8n/database.sqlite');
  if (!existsSync(dbPath)) throw new Error(`找不到 n8n 数据库: ${dbPath}`);
  try {
    execFileSync('lsof', ['-tiTCP:5678', '-sTCP:LISTEN'], { stdio: 'ignore' });
    throw new Error('n8n 仍在运行，请先按 Ctrl+C 停止 n8n，再执行 --live');
  } catch (error) {
    if (error.message.includes('仍在运行')) throw error;
  }

  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14);
  const backupPath = `${dbPath}.before-stage4-resolution-${stamp}`;
  copyFileSync(dbPath, backupPath);
  const db = new Database(dbPath);
  const workflowName = process.env.N8N_VIDEO_WORKFLOW_NAME || '摄影摄像｜中英文视频生成与成片';
  const row = db.prepare('SELECT id, nodes, versionCounter FROM workflow_entity WHERE name = ?').get(workflowName);
  if (!row) {
    db.close();
    throw new Error(`找不到当前视频工作流: ${workflowName}`);
  }

  const nodes = patchWorkflow({ nodes: JSON.parse(row.nodes) }).nodes;
  const nodesJson = JSON.stringify(nodes);
  db.prepare('UPDATE workflow_entity SET nodes = ?, updatedAt = CURRENT_TIMESTAMP, versionCounter = ? WHERE id = ?')
    .run(nodesJson, Number(row.versionCounter || 1) + 1, row.id);

  const latestHistory = db.prepare('SELECT versionId FROM workflow_history WHERE workflowId = ? ORDER BY createdAt DESC LIMIT 1').get(row.id);
  const published = db.prepare('SELECT publishedVersionId FROM workflow_published_version WHERE workflowId = ?').get(row.id);
  const versionIds = [...new Set([latestHistory?.versionId, published?.publishedVersionId].filter(Boolean))];
  for (const versionId of versionIds) {
    db.prepare('UPDATE workflow_history SET nodes = ?, updatedAt = CURRENT_TIMESTAMP WHERE versionId = ?')
      .run(nodesJson, versionId);
  }

  db.close();
  console.log(`已更新当前 n8n 工作流: ${workflowName}`);
  console.log(`数据库备份: ${backupPath}`);
  console.log(`已同步当前版本快照: ${versionIds.length} 个`);
}

console.log(process.argv.includes('--live') ? 'Stage 4 筛选器、创意方案、完整 Mood Board、无字幕规则、分辨率和状态查询重试已同步到 n8n。请重启 n8n 后测试。' : '本地模板已更新；当前 n8n 数据库请停止 n8n 后使用 --live 同步。');

import { copyFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import Database from 'better-sqlite3';

const dbPath = process.env.N8N_DB_PATH || path.join(process.env.HOME || '', '.n8n/database.sqlite');
const workflowName = '系统｜产品图片上传到火山 TOS';
const webhookPath = process.env.N8N_ASSET_UPLOAD_WORKFLOW || 'ai-ad-asset-upload';
const bucketName = String(process.env.TOS_BUCKET || '').trim();

if (!bucketName || bucketName.startsWith('YOUR_')) {
  throw new Error('请先设置 TOS_BUCKET，再安装图片上传工作流。');
}

if (!existsSync(dbPath)) throw new Error(`找不到 n8n 数据库: ${dbPath}`);
try {
  execFileSync('lsof', ['-tiTCP:5678', '-sTCP:LISTEN'], { stdio: 'ignore' });
  throw new Error('n8n 仍在运行。请在运行 n8n 的窗口按 Control+C，再重新执行本命令。');
} catch (error) {
  if (error.message.includes('n8n 仍在运行')) throw error;
}

const stamp = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14);
const backupPath = `${dbPath}.before-asset-upload-${stamp}`;
copyFileSync(dbPath, backupPath);

const db = new Database(dbPath);
const credential = db.prepare(`
  SELECT id, name FROM credentials_entity
  WHERE type = 'aws' AND name IN ('火山引擎', '火山 TOS')
  ORDER BY CASE name WHEN '火山引擎' THEN 0 ELSE 1 END
  LIMIT 1
`).get();
if (!credential) {
  db.close();
  throw new Error('n8n 中找不到现有的火山 TOS 凭据');
}

const workflowId = db.prepare('SELECT id FROM workflow_entity WHERE name = ?').get(workflowName)?.id || randomUUID();
const versionId = randomUUID();
const webhookNodeId = randomUUID();
const uploadNodeId = randomUUID();
const responseNodeId = randomUUID();
const nodes = [
  {
    parameters: {
      httpMethod: 'POST',
      path: webhookPath,
      responseMode: 'lastNode',
      options: { rawBody: true },
    },
    id: webhookNodeId,
    name: '接收产品图片',
    type: 'n8n-nodes-base.webhook',
    typeVersion: 2.1,
    position: [0, 0],
    webhookId: randomUUID(),
  },
  {
    parameters: {
      operation: 'upload',
      bucketName,
      fileName: '={{ $json.query.key }}',
      binaryData: true,
      binaryPropertyName: 'data',
      additionalFields: {},
    },
    id: uploadNodeId,
    name: '上传到火山 TOS',
    type: 'n8n-nodes-base.awsS3',
    typeVersion: 2,
    position: [240, 0],
    credentials: { aws: { id: credential.id, name: credential.name } },
  },
  {
    parameters: {
      jsCode: 'return [{json:{ok:true,storage:"tos"}}];',
    },
    id: responseNodeId,
    name: '返回上传成功',
    type: 'n8n-nodes-base.code',
    typeVersion: 2,
    position: [480, 0],
  },
];
const connections = {
  接收产品图片: { main: [[{ node: '上传到火山 TOS', type: 'main', index: 0 }]] },
  '上传到火山 TOS': { main: [[{ node: '返回上传成功', type: 'main', index: 0 }]] },
};
const nodesJson = JSON.stringify(nodes);
const connectionsJson = JSON.stringify(connections);

const install = db.transaction(() => {
  db.prepare('DELETE FROM webhook_entity WHERE webhookPath = ? AND method = ?').run(webhookPath, 'POST');
  const existing = db.prepare('SELECT id FROM workflow_entity WHERE id = ?').get(workflowId);
  if (existing) {
    db.prepare(`UPDATE workflow_entity SET name=?, active=1, nodes=?, connections=?, settings=?, versionId=?, updatedAt=CURRENT_TIMESTAMP, isArchived=0 WHERE id=?`)
      .run(workflowName, nodesJson, connectionsJson, JSON.stringify({ executionOrder: 'v1', binaryMode: 'separate' }), versionId, workflowId);
    db.prepare('DELETE FROM workflow_history WHERE workflowId = ?').run(workflowId);
  } else {
    db.prepare(`INSERT INTO workflow_entity (id,name,active,nodes,connections,settings,versionId,isArchived,versionCounter) VALUES (?,?,?,?,?,?,?,0,1)`)
      .run(workflowId, workflowName, 1, nodesJson, connectionsJson, JSON.stringify({ executionOrder: 'v1', binaryMode: 'separate' }), versionId);
  }
  db.prepare(`INSERT INTO workflow_history (versionId,workflowId,authors,nodes,connections,name,autosaved) VALUES (?,?,?,?,?,?,0)`)
    .run(versionId, workflowId, '晓荷 罗', nodesJson, connectionsJson, workflowName);
  db.prepare(`INSERT INTO webhook_entity (workflowId,webhookPath,method,node,webhookId,pathLength) VALUES (?,?,?,?,?,?)`)
    .run(workflowId, webhookPath, 'POST', '接收产品图片', nodes[0].webhookId, webhookPath.length);
});

install();
db.close();
console.log(`已安装 TOS 图片上传工作流: ${workflowName}`);
console.log(`已复用 n8n 凭据: ${credential.name}`);
console.log(`数据库备份: ${backupPath}`);
console.log('现在重新启动项目即可。');

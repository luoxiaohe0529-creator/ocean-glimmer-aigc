import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2] || path.resolve('n8n-workflows/generated/live-stage4-providers.json');
const envelope = JSON.parse(fs.readFileSync(target, 'utf8'));
const workflow = Array.isArray(envelope) ? envelope[0] : envelope;
const edge = (node) => ({ node, type: 'main', index: 0 });
const find = (name) => workflow.nodes.find((node) => node.name === name);
const prepName = '整理视频生成参数与语言路由';

let normalize = find('整理视频失败结果');
if (!normalize) {
  normalize = {
    id: crypto.randomUUID(),
    name: '整理视频失败结果',
    type: 'n8n-nodes-base.code',
    typeVersion: 2,
    position: [4300, 720],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const failed=$input.first().json;const source=$("${prepName}").first().json;const detail=failed.error?.message||failed.error||failed.message||failed.description||failed.response?.body?.message||failed.response?.body||"视频生成服务执行失败";return [{json:{ok:false,status:"error",error:"video_generation_failed",message:typeof detail==="string"?detail:JSON.stringify(detail),video_task_id:source.video_task_id,provider:source.provider||"seedance-official"}}];`,
    },
  };
  workflow.nodes.push(normalize);
}

let callback = find('回调前端｜写入视频失败');
if (!callback) {
  callback = {
    id: crypto.randomUUID(),
    name: '回调前端｜写入视频失败',
    type: 'n8n-nodes-base.httpRequest',
    typeVersion: 4.4,
    position: [4560, 720],
    retryOnFail: true,
    maxTries: 3,
    waitBetweenTries: 5000,
    parameters: {
      method: 'POST',
      url: `={{ $("${prepName}").first().json.callback_url }}`,
      sendBody: true,
      specifyBody: 'json',
      jsonBody: '={{ $json }}',
      options: { timeout: 30000, response: { response: { responseFormat: 'json' } } },
    },
  };
  workflow.nodes.push(callback);
}

workflow.connections[normalize.name] = { main: [[edge(callback.name)]] };

const directFailureNodes = [
  'Seedance 2.0｜查询生成状态',
  '检查视频状态',
  'KIE 适配器｜创建 Veo 3.1 视频',
  'KIE 适配器｜查询 Veo 3.1 状态',
  '检查 Veo 3.1 状态',
  'KIE 适配器｜创建可灵 3.0 视频',
  'KIE 适配器｜查询可灵 3.0 状态',
  '检查可灵 3.0 状态',
];

for (const name of directFailureNodes) {
  const node = find(name);
  if (!node) continue;
  node.onError = 'continueErrorOutput';
  const current = workflow.connections[name]?.main || [];
  workflow.connections[name] = { main: [current[0] || [], [edge(normalize.name)]] };
}

const classify = find('识别 Seedance 创建拦截');
if (classify) {
  classify.onError = 'continueErrorOutput';
  const current = workflow.connections[classify.name]?.main || [];
  workflow.connections[classify.name] = { main: [current[0] || [], [edge(normalize.name)]] };
}

workflow.description = '立即返回任务 ID；中文视频沿用 Seedance 主线路。成功和失败都会回调前端，避免任务永久停留在 queued。';
fs.writeFileSync(target, `${JSON.stringify(Array.isArray(envelope) ? [workflow] : workflow, null, 2)}\n`);
console.log(`Stage 4 failure callback fixed: ${workflow.id}`);

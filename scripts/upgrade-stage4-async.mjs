import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2] || path.resolve('n8n-workflows/generated/live-stage4-providers.json');
const envelope = JSON.parse(fs.readFileSync(target, 'utf8'));
const workflow = Array.isArray(envelope) ? envelope[0] : envelope;
const node = (name) => workflow.nodes.find((item) => item.name === name);
const edge = (name) => ({ node: name, type: 'main', index: 0 });

const prep = node('整理视频生成参数与语言路由');
const loop = node('逐段生成视频');
const respond = node('响应前端') || node('立即返回视频任务 ID');
const final = node('返回前端｜可发布成片');
if (!prep || !loop || !respond || !final) throw new Error('Stage 4 节点结构不完整');

respond.name = '立即返回视频任务 ID';
respond.position = [448, 992];
respond.parameters.respondWith = 'json';
respond.parameters.responseBody = '={{ { ok: true, status: "queued", video_task_id: $json.video_task_id, poll_after_ms: 5000 } }}';
respond.parameters.options = {
  responseCode: 202,
  responseHeaders: { entries: [{ name: 'Content-Type', value: 'application/json; charset=utf-8' }] },
};

let callback = node('回调前端｜写入视频结果');
if (!callback) {
  callback = {
    id: crypto.randomUUID(),
    name: '回调前端｜写入视频结果',
    type: 'n8n-nodes-base.httpRequest',
    typeVersion: 4.4,
    position: [1340, 912],
    retryOnFail: true,
    maxTries: 3,
    waitBetweenTries: 5000,
    parameters: {
      method: 'POST',
      url: '={{ $("整理视频生成参数与语言路由").first().json.callback_url }}',
      sendBody: true,
      specifyBody: 'json',
      jsonBody: '={{ { ...$json, video_task_id: $("整理视频生成参数与语言路由").first().json.video_task_id } }}',
      options: { timeout: 30000, response: { response: { responseFormat: 'json' } } },
    },
  };
  workflow.nodes.push(callback);
}

workflow.connections[prep.name] = { main: [[edge(respond.name)]] };
workflow.connections[respond.name] = { main: [[edge(loop.name)]] };
workflow.connections[final.name] = { main: [[edge(callback.name)]] };
delete workflow.connections['响应前端'];
workflow.description = '立即返回视频任务 ID，后台继续执行 Seedance、Veo 或可灵生成，并在完成后回调前端；避免长连接断开导致 fetch failed。';

fs.writeFileSync(target, `${JSON.stringify(Array.isArray(envelope) ? [workflow] : workflow, null, 2)}\n`);
console.log(`Upgraded ${workflow.id}: ${workflow.name}`);

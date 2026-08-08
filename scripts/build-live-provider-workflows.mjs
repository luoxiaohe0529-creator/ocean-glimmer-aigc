import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { stage4PrepCode } from './stage4-prep-code.mjs';

const root = path.resolve(import.meta.dirname, '..');
const sourceDir = process.argv[2] || path.join(root, 'backups/live-n8n-pre-kie-20260801-205059');
const outputDir = process.argv[3] || path.join(root, 'n8n-workflows/generated');

const readWorkflow = (file) => JSON.parse(fs.readFileSync(path.join(sourceDir, file), 'utf8'))[0];
const id = () => crypto.randomUUID();
const edge = (node) => ({ node, type: 'main', index: 0 });
const clone = (value) => JSON.parse(JSON.stringify(value));
const getNode = (workflow, name) => {
  const node = workflow.nodes.find((entry) => entry.name === name);
  if (!node) throw new Error(`Missing node: ${name}`);
  return node;
};
const codeNode = (name, position, jsCode) => ({
  id: id(), name, type: 'n8n-nodes-base.code', typeVersion: 2, position,
  parameters: { mode: 'runOnceForAllItems', jsCode },
});
const httpNode = (name, position, url, jsonBody) => ({
  id: id(), name, type: 'n8n-nodes-base.httpRequest', typeVersion: 4.4, position,
  retryOnFail: true, maxTries: 3, waitBetweenTries: 5000,
  parameters: {
    method: 'POST', url, sendBody: true, specifyBody: 'json', jsonBody,
    options: { timeout: 180000, response: { response: { responseFormat: 'json' } } },
  },
});
const ifNode = (name, position, expression) => ({
  id: id(), name, type: 'n8n-nodes-base.if', typeVersion: 2.3, position,
  parameters: { conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'loose' }, conditions: [{ leftValue: expression, operator: { type: 'boolean', operation: 'true' }, rightValue: '' }], combinator: 'and' }, options: {} },
});
const waitNode = (name, position, amount = 20) => ({
  id: id(), webhookId: id(), name, type: 'n8n-nodes-base.wait', typeVersion: 1.1, position,
  parameters: { resume: 'timeInterval', amount, unit: 'seconds' },
});

function buildStage5() {
  const workflow = readWorkflow('stage5-live.json');
  const webhook = clone(getNode(workflow, '前端｜提交分镜图任务'));
  const respond = clone(getNode(workflow, '响应前端'));
  const prompt = codeNode('组装 Image 2 / Nano Banana Pro 提示词', [240, 0], `const incoming=$input.first().json;const body=incoming.body||incoming;
const isCharacter=["generate_character","generate_character_reference"].includes(body.action);
if(isCharacter){
  const charType=body.character_type||"真人达人";const charDesc=body.character_description||"";
  const refs=(body.character_reference_images||[]).map(v=>v?.url||v).filter(Boolean);
  const product=body.product_brief||{};const pn=product["产品名称"]||product.product_name||"";
  const prompt=charType+"角色设定图。角色描述："+charDesc+"。全身正面站立，清晰展示面部特征、发型、服装与整体气质。纯色背景，柔和影棚光，超写实，9:16竖屏。"+(pn?"产品："+pn+"。角色形象需与品牌调性一致。":"");
  return[{json:{kind:"character",model:refs.length?"gpt-image-2-image-to-image":"gpt-image-2-text-to-image",prompt,reference_images:refs,aspect_ratio:"9:16"}}];
}
let shots=body.storyboard;if(typeof shots==="string"){try{shots=JSON.parse(shots);}catch(e){throw new Error("storyboard 不是有效 JSON");}}
if(!Array.isArray(shots)||!shots.length)throw new Error("缺少 storyboard 数组");
const product=body.product_brief||{};const pn=product["产品名称"]||product.product_name||"产品";
const selling=product["核心卖点"]||product.selling_points||"";const sell=Array.isArray(selling)?selling.join(" · "):String(selling);
const refs=(body.product_images||[]).map(v=>v?.url||v).filter(Boolean);
const panels=shots.map((shot,i)=>"Panel "+(i+1)+": "+(shot.image_prompt||shot.visual||shot.description||shot.scene_description||shot.prompt||""));
const prompt="Create one coherent 9:16 storyboard contact sheet with "+shots.length+" clearly separated panels. "+panels.join(" ")+" Product: "+pn+". Key features: "+sell+". Keep product, cast, lighting and art direction consistent. No text, logos or watermarks.";
return[{json:{kind:"storyboard",model:"nano-banana-pro",video_task_id:body.video_task_id||body.task_id||"",product_record_id:body.product_record_id||"",prompt,reference_images:refs,aspect_ratio:"9:16",resolution:"2K",shot_count:shots.length,source_shots:shots}}];`);
  const create = httpNode('KIE 适配器｜创建图片任务', [520, 0], '={{ $json.kind === "character" ? "http://127.0.0.1:8787/providers/kie/character" : "http://127.0.0.1:8787/providers/kie/storyboard" }}', '={{ { prompt: $json.prompt, reference_images: $json.reference_images, aspect_ratio: $json.aspect_ratio, resolution: $json.resolution || "2K" } }}');
  const save = codeNode('保存 KIE 图片任务上下文', [780, 0], `const created=$input.first().json;const source=$("组装 Image 2 / Nano Banana Pro 提示词").first().json;const taskId=created.task_id||created.taskId||created.data?.taskId;if(!taskId)throw new Error("KIE 未返回图片任务 ID");return[{json:{...source,kie_task_id:String(taskId),_poll_count:0}}];`);
  const wait = waitNode('等待图片生成', [1040, 0], 20);
  const query = httpNode('KIE 适配器｜查询图片状态', [1300, 0], 'http://127.0.0.1:8787/providers/kie/status', '={{ { task_id: $json.kie_task_id, kind: $json.kind } }}');
  const normalize = codeNode('检查图片任务状态', [1560, 0], `const result=$input.first().json;const context=$("等待图片生成").item.json;const status=String(result.status||"unknown").toLowerCase();if(["fail","failed","error"].includes(status))throw new Error("KIE 图片生成失败");const count=Number(context._poll_count||0)+1;if(count>45)throw new Error("KIE 图片生成超时");const urls=(result.urls||[]).filter(Boolean);return[{json:{...context,status,image_urls:urls,completed:status==="success"&&urls.length>0,_poll_count:count}}];`);
  const done = ifNode('图片生成完成？', [1810, 0], '={{ $json.completed }}');
  const output = codeNode('返回前端｜图片 JSON', [2070, -120], `const data=$input.first().json;const urls=(data.image_urls||[]).filter(Boolean);if(!urls.length)throw new Error("图片任务成功但没有 URL");const character=data.kind==="character";return[{json:{ok:true,status:"completed",provider:"kie.ai",model:data.model,kind:data.kind,count:urls.length,images:urls,urls,image_url:urls[0],storyboard_image_url:character?undefined:urls[0],character_image_url:character?urls[0]:undefined,storyboard_images:character?[]:urls.map((url,index)=>({index,url,image_url:url}))}}];`);
  respond.position = [2320, -120];
  workflow.name = '编剧导演｜分镜图与主角形象生成';
  workflow.nodes = [webhook, prompt, create, save, wait, query, normalize, done, output, respond];
  workflow.connections = {
    [webhook.name]: { main: [[edge(prompt.name)]] },
    [prompt.name]: { main: [[edge(create.name)]] },
    [create.name]: { main: [[edge(save.name)]] },
    [save.name]: { main: [[edge(wait.name)]] },
    [wait.name]: { main: [[edge(query.name)]] },
    [query.name]: { main: [[edge(normalize.name)]] },
    [normalize.name]: { main: [[edge(done.name)]] },
    [done.name]: { main: [[edge(output.name)], [edge(wait.name)]] },
    [output.name]: { main: [[edge(respond.name)]] },
  };
  return workflow;
}

function buildStage4() {
  const workflow = readWorkflow('stage4-live.json');
  const keep = ['前端｜提交视频生成','整理Seedance生成参数','逐段生成视频','Seedance 2.0｜创建15秒视频','保存视频任务上下文','等待视频生成','Seedance 2.0｜查询生成状态','检查视频状态','视频是否生成完成','汇总视频结果','飞书｜获取应用令牌','飞书｜回写成片链接与成功状态','返回前端｜可发布成片','响应前端'];
  const nodes = keep.map((name) => clone(getNode(workflow, name)));
  const prep = nodes.find((node) => node.name === '整理Seedance生成参数');
  prep.name = '整理视频生成参数与语言路由';
  prep.parameters.jsCode = stage4PrepCode();
  const loop = nodes.find((node) => node.name === '逐段生成视频');
  const seedCreate = nodes.find((node) => node.name === 'Seedance 2.0｜创建15秒视频');
  const seedQuery = nodes.find((node) => node.name === 'Seedance 2.0｜查询生成状态');
  seedCreate.parameters.jsonBody = String(seedCreate.parameters.jsonBody || '').replace('resolution: "480p"', 'resolution: $json.resolution || "480p"');
  seedCreate.onError = 'continueErrorOutput';
  seedQuery.retryOnFail = true;
  seedQuery.maxTries = 4;
  seedQuery.waitBetweenTries = 10000;
  for (const node of nodes) {
    for (const header of node.parameters?.headerParameters?.parameters || []) {
      if (String(header.name).toLowerCase() === 'authorization' && /ark-|bearer/i.test(String(header.value))) {
        header.value = '=Bearer {{$env.SEEDANCE_API_KEY}}';
      }
    }
  }
  const seedStatus = nodes.find((node) => node.name === '检查视频状态');
  seedStatus.parameters.jsCode = `const result=$input.first().json;const context=$("等待视频生成").item.json;
const status=String(result.status||result.data?.status||"").toLowerCase();
const raw=JSON.stringify(result).toLowerCase();
const blocked=/(face|facial|portrait|identity|celebrity|human|safety|moderation|content.?policy|blocked|intercept|人脸|真人|肖像|人物|安全|审核|拦截)/.test(raw);
const failed=["failed","error","cancelled","blocked","rejected"].includes(status);
const pollCount=Number(context._poll_count||0)+1;if(pollCount>40)throw new Error("Seedance 生成超时：已查询 40 次");
if(failed&&blocked)return[{json:{...context,fallback_required:true,fallback_reason:"seedance_face_or_safety_block",seedance_error:result,_poll_count:pollCount}}];
if(failed)throw new Error("Seedance 生成失败："+(result.error?.message||result.message||status));
const videoUrl=result.content?.video_url||result.video_url||result.result_url||result.data?.video_url||result.data?.url||result.url||"";
return[{json:{...context,seedance_result:result,status,is_completed:["completed","succeeded"].includes(status)&&Boolean(videoUrl),fallback_required:false,video_url:videoUrl,result_url:videoUrl,_poll_count:pollCount}}];`;
  const summary = nodes.find((node) => node.name === '汇总视频结果');
  summary.parameters.jsCode = summary.parameters.jsCode.replace('status:(json.video_url||json.result_url)?"completed":"error",', 'status:(json.video_url||json.result_url)?"completed":"error",\n    provider:json.provider||"seedance-official",');
  summary.parameters.jsCode = summary.parameters.jsCode.replace('product_record_id:input.product_record_id,', 'product_record_id:input.product_record_id,\n  provider:segments[0]?.provider||input.provider||"seedance-official",');
  const route = ifNode('英文视频？走 Veo 3.1', [650, 420], '={{ $json.use_veo }}');
  const veoCreate = httpNode('KIE 适配器｜创建 Veo 3.1 视频', [900, 560], 'http://127.0.0.1:8787/providers/kie/overseas-video', '={{ { prompt: $json.video_prompt, image_urls: $json.ref_images, model: "veo3_fast", aspect_ratio: "9:16", enable_fallback: true, enable_translation: true } }}');
  const veoSave = codeNode('保存 Veo 3.1 任务上下文', [1160, 560], `const created=$input.first().json;const source=$("英文视频？走 Veo 3.1").item.json;const taskId=created.task_id||created.taskId||created.data?.taskId;if(!taskId)throw new Error("KIE 未返回 Veo 3.1 任务 ID");return[{json:{...source,kie_task_id:String(taskId),provider:"kie.ai/veo3.1",_poll_count:0}}];`);
  const veoWait = waitNode('等待 Veo 3.1 生成', [1420, 560], 20);
  const veoQuery = httpNode('KIE 适配器｜查询 Veo 3.1 状态', [1680, 560], 'http://127.0.0.1:8787/providers/kie/status', '={{ { task_id: $json.kie_task_id, kind: "overseas_video" } }}');
  const veoStatus = codeNode('检查 Veo 3.1 状态', [1940, 560], `const result=$input.first().json;const context=$("等待 Veo 3.1 生成").item.json;const status=String(result.status||"unknown").toLowerCase();if(["failed","error"].includes(status))throw new Error("Veo 3.1 生成失败");const count=Number(context._poll_count||0)+1;if(count>60)throw new Error("Veo 3.1 生成超时");const url=(result.urls||[])[0]||"";return[{json:{...context,status,is_completed:status==="succeeded"&&Boolean(url),video_url:url,result_url:url,_poll_count:count}}];`);
  const veoDone = ifNode('Veo 3.1 生成完成？', [2200, 560], '={{ $json.is_completed }}');
  const seedCreateError = codeNode('识别 Seedance 创建拦截', [900, 300], `const error=$input.first().json;const source=$("英文视频？走 Veo 3.1").item.json;const raw=JSON.stringify(error).toLowerCase();const blocked=/(face|facial|portrait|identity|celebrity|human|safety|moderation|content.?policy|blocked|intercept|人脸|真人|肖像|人物|安全|审核|拦截)/.test(raw);if(!blocked)throw new Error("Seedance 创建失败："+JSON.stringify(error));return[{json:{...source,fallback_required:true,fallback_reason:"seedance_face_or_safety_block",seedance_error:error}}];`);
  const seedFallback = ifNode('Seedance 需要切换可灵？', [2200, 280], '={{ $json.fallback_required === true }}');
  const klingPrep = codeNode('准备可灵 3.0 回退', [2460, 300], `const data=$input.first().json;return[{json:{...data,_kling_context:JSON.stringify(data)}}];`);
  const klingCreate = httpNode('KIE 适配器｜创建可灵 3.0 视频', [2720, 300], 'http://127.0.0.1:8787/providers/kie/kling-video', '={{ { prompt: $json.video_prompt, image_urls: $json.ref_images, duration: $json.duration || 15, aspect_ratio: "9:16", mode: "pro", sound: true } }}');
  const klingSave = codeNode('保存可灵 3.0 任务上下文', [2980, 300], `const created=$input.first().json;const source=$("准备可灵 3.0 回退").item.json;const taskId=created.task_id||created.taskId||created.data?.taskId;if(!taskId)throw new Error("可灵 3.0 未返回任务 ID");return[{json:{...source,kie_task_id:String(taskId),provider:"kie.ai/kling-3.0-fallback",_poll_count:0}}];`);
  const klingWait = waitNode('等待可灵 3.0 生成', [3240, 300], 20);
  const klingQuery = httpNode('KIE 适配器｜查询可灵 3.0 状态', [3500, 300], 'http://127.0.0.1:8787/providers/kie/status', '={{ { task_id: $json.kie_task_id, kind: "kling_video" } }}');
  const klingStatus = codeNode('检查可灵 3.0 状态', [3760, 300], `const result=$input.first().json;const context=$("等待可灵 3.0 生成").item.json;const status=String(result.status||"unknown").toLowerCase();if(["failed","error"].includes(status))throw new Error("可灵 3.0 生成失败");const count=Number(context._poll_count||0)+1;if(count>60)throw new Error("可灵 3.0 生成超时");const url=(result.urls||[])[0]||"";return[{json:{...context,status,is_completed:status==="succeeded"&&Boolean(url),video_url:url,result_url:url,_poll_count:count}}];`);
  const klingDone = ifNode('可灵 3.0 生成完成？', [4020, 300], '={{ $json.is_completed }}');
  const nodeMap = Object.fromEntries(nodes.map((node) => [node.name, node]));
  workflow.name = '摄影摄像｜中英文视频生成与成片';
  workflow.nodes = [...nodes, route, veoCreate, veoSave, veoWait, veoQuery, veoStatus, veoDone, seedCreateError, seedFallback, klingPrep, klingCreate, klingSave, klingWait, klingQuery, klingStatus, klingDone];
  workflow.connections = {
    '前端｜提交视频生成': { main: [[edge(prep.name)]] },
    [prep.name]: { main: [[edge(loop.name)]] },
    [loop.name]: { main: [[edge(summary.name)], [edge(route.name)]] },
    [route.name]: { main: [[edge(veoCreate.name)], [edge('Seedance 2.0｜创建15秒视频')]] },
    'Seedance 2.0｜创建15秒视频': { main: [[edge('保存视频任务上下文')], [edge(seedCreateError.name)]] },
    '保存视频任务上下文': { main: [[edge('等待视频生成')]] },
    '等待视频生成': { main: [[edge('Seedance 2.0｜查询生成状态')]] },
    'Seedance 2.0｜查询生成状态': { main: [[edge('检查视频状态')]] },
    '检查视频状态': { main: [[edge(seedFallback.name)]] },
    [seedFallback.name]: { main: [[edge(klingPrep.name)], [edge('视频是否生成完成')]] },
    [seedCreateError.name]: { main: [[edge(klingPrep.name)]] },
    '视频是否生成完成': { main: [[edge(loop.name)], [edge('等待视频生成')]] },
    [veoCreate.name]: { main: [[edge(veoSave.name)]] },
    [veoSave.name]: { main: [[edge(veoWait.name)]] },
    [veoWait.name]: { main: [[edge(veoQuery.name)]] },
    [veoQuery.name]: { main: [[edge(veoStatus.name)]] },
    [veoStatus.name]: { main: [[edge(veoDone.name)]] },
    [veoDone.name]: { main: [[edge(loop.name)], [edge(veoWait.name)]] },
    [klingPrep.name]: { main: [[edge(klingCreate.name)]] },
    [klingCreate.name]: { main: [[edge(klingSave.name)]] },
    [klingSave.name]: { main: [[edge(klingWait.name)]] },
    [klingWait.name]: { main: [[edge(klingQuery.name)]] },
    [klingQuery.name]: { main: [[edge(klingStatus.name)]] },
    [klingStatus.name]: { main: [[edge(klingDone.name)]] },
    [klingDone.name]: { main: [[edge(loop.name)], [edge(klingWait.name)]] },
    [summary.name]: { main: [[edge('飞书｜获取应用令牌')]] },
    '飞书｜获取应用令牌': { main: [[edge('飞书｜回写成片链接与成功状态')]] },
    '飞书｜回写成片链接与成功状态': { main: [[edge('返回前端｜可发布成片')]] },
    '返回前端｜可发布成片': { main: [[edge('响应前端')]] },
  };
  void nodeMap;
  return workflow;
}

fs.mkdirSync(outputDir, { recursive: true });
for (const [filename, workflow] of [['live-stage4-providers.json', buildStage4()], ['live-stage5-providers.json', buildStage5()]]) {
  fs.writeFileSync(path.join(outputDir, filename), JSON.stringify([workflow], null, 2) + '\n');
  console.log(`${filename}: ${workflow.id} ${workflow.name} (${workflow.nodes.length} nodes)`);
}

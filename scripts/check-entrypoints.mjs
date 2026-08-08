import { readFile } from 'node:fs/promises';

const mainHtml = await readFile('frontend/open-design.html', 'utf8');
const server = await readFile('frontend/server.mjs', 'utf8');

const legacyRoutes = [
  '/api/workflow/stage-1/url',
  '/api/workflow/stage-1/document',
  '/api/workflow/stage-1/tvc',
  '/api/workflow/stage-2',
  '/api/workflow/stage-3',
];

const failures = [];
const htmlLegacyGuard = mainHtml.match(/var disabledLegacyContentPaths=\{([\s\S]*?)\};/)?.[1] || '';
const serverLegacyGuard = server.match(/const disabledLegacyContentRoutes = new Set\(\[([\s\S]*?)\]\);/)?.[1] || '';
for (const route of legacyRoutes) {
  const htmlCount = (htmlLegacyGuard.match(new RegExp(`['\"]${route.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}['\"]\\s*:\\s*true`, 'g')) || []).length;
  const serverCount = (serverLegacyGuard.match(new RegExp(`['\"]${route.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}['\"]`, 'g')) || []).length;
  if (htmlCount !== 1) failures.push(`主前端旧路由 ${route} 应只存在于兼容保护表，实际 ${htmlCount} 处`);
  if (serverCount !== 1) failures.push(`服务端旧路由 ${route} 应只存在于禁用表，实际 ${serverCount} 处`);
}

for (const marker of ['nativeWorkflowFetch', 'delegatedClickBound']) {
  if (mainHtml.includes(marker)) failures.push(`主前端仍包含历史重复绑定标记：${marker}`);
}

const bindCount = (mainHtml.match(/function bind\s*\(/g) || []).length;
if (bindCount !== 1) failures.push(`主前端基础绑定函数应只有 1 个，实际 ${bindCount} 个`);

const fetchWrapperCount = (mainHtml.match(/window\.fetch\s*=\s*function/g) || []).length;
if (fetchWrapperCount !== 1) failures.push(`主前端统一请求包装器应只有 1 个，实际 ${fetchWrapperCount} 个`);

if (mainHtml.includes('Stage 1 review surface for the complete Mood Board')) {
  failures.push('主前端仍包含重复的独立 Mood Board 区块');
}

for (const group of ['tvc-brand-v3', 'tvc-social-fastcut-v3', 'tvc-material-v3']) {
  if (!mainHtml.includes(group)) failures.push(`Stage 1 缺少高端 TVC 模板路线：${group}`);
}

if (!mainHtml.includes('box.className="hook-mood-inline"')) {
  failures.push('Stage 1 Hook 卡片缺少内嵌 Mood Board');
}

for (const action of ['confirm-hook', 'go-video']) {
  const handlerPattern = new RegExp(`closest\\('\\[data-action=\\"${action}\\"\\]'\\)`);
  if (!handlerPattern.test(mainHtml)) failures.push(`主前端缺少 ${action} 的阶段跳转处理`);
}

if (!mainHtml.includes('data-action="regenerate-creative"')) {
  failures.push('编剧导演完成态缺少“重新生成脚本”动作');
}
if (mainHtml.includes('onerror="this.parentElement.remove()"')) {
  failures.push('产品图加载失败仍只隐藏 DOM，图片计数会失真');
}
if (mainHtml.includes('未写入对象存储，请重新上传')) {
  failures.push('产品图区域仍暴露对象存储失败提示');
}
if (!server.includes('async function persistUploadedImages(payload)')) {
  failures.push('图片上传缺少统一 TOS 持久化入口');
}
if (!server.includes('N8N_ASSET_UPLOAD_WORKFLOW')) {
  failures.push('图片上传没有接入唯一的 n8n TOS 上传工作流');
}
if (server.includes("storage: 'local'") || mainHtml.includes('/generated/uploads/')) {
  failures.push('图片上传仍包含本地路径兜底，无法保证公网 URL');
}

if (!mainHtml.includes('function navigateToStage(stage)')) {
  failures.push('主前端缺少统一阶段跳转函数');
}

for (const pattern of [
  /return\s+fetch\("\/api\/fast\/stage-[123]"/g,
  /return\s+originalFetch\("\/api\/workflow\/stage-[123]"/g,
]) {
  const matches = mainHtml.match(pattern) || [];
  if (matches.length) failures.push(`主前端仍包含内容阶段 fallback：${matches.join(', ')}`);
}

const expectedEntries = [
  '/api/fast/stage-1',
  '/api/fast/stage-2',
  '/api/fast/stage-3',
  '/api/workflow/stage-4',
];
for (const route of expectedEntries) {
  if (!mainHtml.includes(route)) failures.push(`主前端缺少正式入口：${route}`);
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('Entry-point contract passed: Python Stage 1/2/3 + n8n media Stage 4.');

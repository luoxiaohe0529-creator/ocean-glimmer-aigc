const STORAGE_KEY = 'ai-ad-video-factory-workbench-v3';
const demoMode = new URLSearchParams(location.search).get('demo') === '1';

const steps = [
  { id: 1, short: '产品', name: '产品输入', note: '输入产品资料' },
  { id: 2, short: 'Hook', name: 'Hook 角度', note: '选择一个创意入口' },
  { id: 3, short: '脚本', name: '脚本确认', note: '确认脚本内容' },
  { id: 4, short: '视频', name: '成片结果', note: '生成并查看成片' },
];

const initialState = () => ({
  stage: 1,
  completed: 0,
  contentType: '种草视频',
  sourceMode: 'url',
  product: { language: '中文', content_type: '种草视频' },
  brief: null,
  hooks: [],
  selectedHookId: '',
  filters: { category: '全部', awareness: '全部', emotion: '全部' },
  script: null,
  scriptConfirmed: false,
  videoTask: null,
  final: null,
  busy: false,
  message: '',
  error: '',
});

let state = { ...initialState(), ...readState() };
state.filters = { ...initialState().filters, ...(state.filters || {}) };

function readState() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; }
}

function saveState() {
  const clean = { ...state, busy: false, message: '', error: '' };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(clean));
}

function setState(patch) {
  state = { ...state, ...patch };
  saveState();
  render();
}

function esc(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function lines(value) {
  if (Array.isArray(value)) return value.flatMap(lines).filter(Boolean);
  if (value == null) return [];
  return String(value).split(/\n|；|;/).map(item => item.trim()).filter(Boolean);
}

function withBreaks(value = '') {
  return esc(value).replaceAll('\n', '<br>');
}

function currentStep() {
  return Math.max(1, Math.min(4, Number(state.stage) || 1));
}

function canOpen(id) {
  return id <= state.completed + 1;
}

function render() {
  const stage = currentStep();
  document.body.dataset.stage = String(stage);
  document.querySelector('#app').innerHTML = `
    <div class="app-shell">
      <header class="app-header">
        <a class="brand" href="?demo=${demoMode ? '1' : '0'}" data-action="home" aria-label="AI广告视频工厂">
          <span class="brand-symbol">AI</span>
          <span><strong>广告视频工厂</strong><small>AI AD VIDEO FACTORY</small></span>
        </a>
        <div class="header-center"><span class="header-caption">PROJECT 01</span><b>${esc(state.product?.project_name || state.product?.product_name || '未命名项目')}</b></div>
        <div class="header-actions"><span class="connection"><i></i>${demoMode ? '演示模式' : '工作流已连接'}</span><button class="icon-button" type="button" data-action="reset" title="新建项目" aria-label="新建项目">＋</button></div>
      </header>
      <div class="app-body">
        <aside class="step-rail" aria-label="创作步骤">
          <div class="rail-title">创作流程 <span>04</span></div>
          <nav>${steps.map(step => renderStep(step, stage)).join('')}</nav>
          <div class="rail-foot"><span>SEEDANCE 2.0</span><span>FEISHU / N8N</span></div>
        </aside>
        <main class="page">
          ${renderWorkspaceStatus()}
          ${renderAlerts()}
          ${stage === 1 ? renderProductPage() : ''}
          ${stage === 2 ? renderHookPage() : ''}
          ${stage === 3 ? renderScriptPage() : ''}
          ${stage === 4 ? renderVideoPage() : ''}
        </main>
      </div>
    </div>`;
  bindEvents();
}

function renderStep(step, stage) {
  const done = step.id <= state.completed;
  const locked = !canOpen(step.id) && !demoMode;
  return `<button type="button" class="step-item ${stage === step.id ? 'active' : ''} ${done ? 'done' : ''} ${locked ? 'locked' : ''}" data-stage="${step.id}" ${locked ? 'disabled' : ''}>
    <span class="step-number">0${step.id}</span><span class="step-copy"><b>${esc(step.name)}</b><small>${esc(step.note)}</small></span><span class="step-check">${done ? '✓' : locked ? '—' : '·'}</span>
  </button>`;
}

function renderAlerts() {
  if (state.error) return `<div class="notice error"><strong>需要处理</strong><span>${withBreaks(state.error)}</span><button type="button" data-action="clear-alert" aria-label="关闭">×</button></div>`;
  if (state.message) return `<div class="notice success"><strong>已完成</strong><span>${withBreaks(state.message)}</span><button type="button" data-action="clear-alert" aria-label="关闭">×</button></div>`;
  return '';
}

function renderWorkspaceStatus() {
  const status = state.final ? '视频已返回' : state.videoTask ? '视频任务已准备' : state.hooks.length ? 'Hooks ready' : 'Queued';
  const detail = state.final ? '可以播放或下载成片' : state.videoTask ? '等待执行 Seedance 2.0' : state.hooks.length ? `${state.hooks.length} 条创意角度可选` : '等待产品资料';
  return `<div class="workspace-status"><span class="status-badge"><i></i>${status}</span><span>${esc(detail)}</span><small>${demoMode ? 'Demo' : 'n8n workflow'}</small></div>`;
}

function renderPageHeader(kicker, title, description, meta = '') {
  return `<div class="page-header"><div><span class="kicker">${esc(kicker)}</span><h1>${title}</h1><p>${esc(description)}</p></div>${meta ? `<div class="header-meta">${meta}</div>` : ''}</div>`;
}

function renderProductPage() {
  const p = state.product || {};
  return `<section class="page-section">
    ${renderPageHeader('01 / PRODUCT INPUT', '先把产品放到桌面上。', '选择要生成的内容类型，再提供产品链接或产品图。完成后右侧会立即显示产品简报。', `<span>输入</span><strong>产品资料</strong>`)}
    <div class="split-view product-view">
      <section class="input-panel">
        <div class="panel-heading"><span class="panel-index">01</span><div><b>内容类型</b><small>决定后面的创作路径</small></div></div>
        <div class="type-list">
          ${typeOption('种草视频', '产品主图直接进入 Seedance 图生视频', '种')}
          ${typeOption('达人带货视频', '先生成固定达人手持产品图，再图生视频口播', '达')}
          ${typeOption('TVC广告', '以白底产品图为唯一产品形态依据', 'T')}
        </div>
        <div class="panel-heading second"><span class="panel-index">02</span><div><b>产品资料</b><small>${state.contentType === 'TVC广告' ? 'TVC 使用产品白底图或参考图' : '商品链接与产品图二选一'}</small></div></div>
        <div class="segmented"><button type="button" class="${state.sourceMode === 'url' ? 'selected' : ''}" data-source="url">商品链接</button><button type="button" class="${state.sourceMode === 'image' ? 'selected' : ''}" data-source="image">产品白底图</button></div>
        ${state.sourceMode === 'url' ? renderUrlInput(p) : renderImageInput(p)}
      </section>
      <section class="result-panel brief-panel">${renderBriefResult()}</section>
    </div>
  </section>`;
}

function typeOption(type, detail, mark) {
  const selected = state.contentType === type;
  return `<button type="button" class="type-option ${selected ? 'selected' : ''}" data-content-type="${esc(type)}"><span class="type-mark">${mark}</span><span><b>${esc(type)}</b><small>${esc(detail)}</small></span><i>${selected ? '✓' : '＋'}</i></button>`;
}

function languageField(p) {
  const value = p.language || '中文';
  return `<label class="field"><span>脚本语言</span><select name="language"><option value="中文" ${value === '中文' ? 'selected' : ''}>中文</option><option value="英文" ${value === '英文' ? 'selected' : ''}>英文</option></select></label>`;
}

function renderUrlInput(p) {
  return `<form id="url-form" class="form-stack">
    <label class="field"><span>商品网页链接 <em>必填</em></span><input name="product_url" type="url" value="${esc(p.product_url || '')}" placeholder="https://..." required></label>
    <div class="field-row">${languageField(p)}<label class="field"><span>项目名称 <em>可选</em></span><input name="project_name" value="${esc(p.project_name || '')}" placeholder="例如：夏日新品短片"></label></div>
    <div class="field-row"><label class="field"><span>达人设定 <em>${state.contentType === '达人带货视频' ? '建议填写' : '可选'}</em></span><input name="creator_profile" value="${esc(p.creator_profile || '')}" placeholder="固定达人、年龄、气质、服饰"></label><label class="field"><span>目标人群 <em>可选</em></span><input name="target_audience" value="${esc(p.target_audience || '')}" placeholder="网页没有写清楚时补充"></label></div>
    <label class="field"><span>补充卖点 <em>可选</em></span><textarea name="selected_benefits" rows="2" placeholder="不填则由网页资料提炼">${esc(p.core_benefits || '')}</textarea></label>
    <button class="primary" type="submit" ${state.busy ? 'disabled' : ''}><span>${state.busy ? '正在整理…' : '分析产品并生成 Hook'}</span><b>→</b></button>
  </form>`;
}

function renderImageInput(p) {
  return `<form id="image-form" class="form-stack">
    <div class="upload-box"><input id="product-image" name="product_image" type="file" accept="image/*" required><label for="product-image"><span class="upload-icon">↑</span><span><b class="upload-name">${esc(p.file_name || '选择产品白底图')}</b><small>图片会交给对象存储生成 public URL</small></span><i>选择文件</i></label></div>
    <div class="field-row"><label class="field"><span>产品名称 <em>建议填写</em></span><input name="product_name" value="${esc(p.product_name || '')}" placeholder="例如：某某香水"></label>${languageField(p)}</div>
    <label class="field"><span>重要产品卖点 <em>必填</em></span><textarea name="selected_benefits" rows="3" placeholder="材质、香调、核心功效、使用场景、必须展示的细节" required>${esc(p.core_benefits || '')}</textarea></label>
    <div class="field-row"><label class="field"><span>视觉风格 <em>可选</em></span><input name="visual_style" value="${esc(p.visual_style || (state.contentType === 'TVC广告' ? '高级棚拍、克制光影' : '真实、自然、可信'))}"></label><label class="field"><span>甲方限制 <em>可选</em></span><input name="restrictions" value="${esc(p.restrictions || '产品不变形、不改包装')}"></label></div>
    <button class="primary" type="submit" ${state.busy ? 'disabled' : ''}><span>${state.busy ? '正在整理…' : '生成产品简报与 Hook'}</span><b>→</b></button>
  </form>`;
}

function renderBriefResult() {
  if (!state.brief) return `<div class="result-empty"><span class="result-label">OUTPUT / PRODUCT BRIEF</span><div class="empty-symbol">＋</div><h2>产品结果会出现在这里</h2><p>提交产品资料后，这里会展示产品名称、品类、卖点、受众与创作方向。</p><div class="skeleton"><i></i><i></i><i></i></div></div>`;
  const b = state.brief;
  return `<div class="result-content"><div class="result-title"><div><span class="result-label">OUTPUT / PRODUCT BRIEF</span><h2>${esc(b.product || '待命名产品')}</h2></div><span class="pill">已整理</span></div><dl class="brief-list"><div><dt>品类</dt><dd>${esc(b.category || '待识别')}</dd></div><div><dt>目标受众</dt><dd>${esc(b.audience || '待识别')}</dd></div><div class="wide"><dt>核心卖点</dt><dd class="chips">${lines(b.benefits).map(x => `<span>${esc(x)}</span>`).join('') || '网页资料已写入上下文'}</dd></div><div class="wide"><dt>创作方向</dt><dd>${esc(b.direction || b.summary || '已写入后续工作流')}</dd></div><div class="wide"><dt>素材状态</dt><dd>${esc(state.product?.product_image_url ? '产品图已准备' : '等待工作流返回产品图')}</dd></div></dl><div class="result-footer"><span>下一步</span><strong>右侧选择 Hook →</strong></div></div>`;
}

function renderHookPage() {
  if (!state.hooks.length) return renderGate(2, '还没有 Hook 结果', '先完成第 01 步，Hook 会以可筛选的结果列表出现在右侧。');
  const visible = filteredHooks();
  return `<section class="page-section">
    ${renderPageHeader('02 / HOOK ANGLES', '先看结果，再选方向。', '所有 Hook 都来自产品简报。左侧只负责筛选和选择，右侧展示完整创意结果。', `<span>结果</span><strong>${visible.length} / ${state.hooks.length}</strong>`)}
    <div class="split-view hook-view">
      <section class="input-panel filter-panel"><div class="panel-heading"><span class="panel-index">02</span><div><b>筛选与选择</b><small>选择一个创意角度进入脚本</small></div></div>${filterField('category', 'Hook 类型')}${filterField('awareness', '认知阶段')}${filterField('emotion', '情绪触发')}<div class="selection-note">${state.selectedHookId ? `<span class="selected-dot"></span><b>已选择一个 Hook</b><small>右侧卡片已标记，点击继续生成脚本。</small>` : `<span class="selected-dot muted"></span><b>还没有选择</b><small>从右侧结果中选择一个最适合的角度。</small>`}</div><button class="primary full" type="button" data-action="make-script" ${!state.selectedHookId || state.busy ? 'disabled' : ''}><span>${state.busy ? '生成脚本中…' : '用这个 Hook 生成脚本'}</span><b>→</b></button></section>
      <section class="result-panel hook-results"><div class="result-toolbar"><div><span class="result-label">OUTPUT / HOOK GALLERY</span><h2>${state.brief?.product ? esc(state.brief.product) : '产品 Hook 结果'}</h2></div><span class="count-badge">${String(visible.length).padStart(2, '0')} 条</span></div><div class="context-strip"><span>${esc(state.product?.language || '中文')}</span><b>${esc(lines(state.brief?.benefits || state.product?.core_benefits)[0] || '产品卖点已写入上下文')}</b><small>${esc(state.contentType)}</small></div><div class="hook-list">${visible.length ? visible.map(renderHookRow).join('') : '<div class="no-result">当前筛选没有结果，换一个筛选条件试试。</div>'}</div></section>
    </div>
  </section>`;
}

function filterField(kind, label) {
  const values = [...new Set(state.hooks.map(item => item[kind === 'category' ? 'hook_category' : kind === 'awareness' ? 'awareness_stage' : 'emotional_trigger']).filter(Boolean))];
  const selected = state.filters[kind];
  return `<label class="filter-field"><span>${esc(label)}</span><select data-filter="${kind}"><option value="全部">全部</option>${values.map(value => `<option value="${esc(value)}" ${selected === value ? 'selected' : ''}>${esc(value)}</option>`).join('')}</select></label>`;
}

function filteredHooks() {
  const f = state.filters;
  return state.hooks.filter(item => (f.category === '全部' || item.hook_category === f.category) && (f.awareness === '全部' || item.awareness_stage === f.awareness) && (f.emotion === '全部' || item.emotional_trigger === f.emotion));
}

function renderHookRow(hook) {
  const selected = state.selectedHookId === hook.hook_record_id;
  const language = state.product?.language || '中文';
  const opening = language === '英文' ? (hook.opening_en || hook.opening_zh) : (hook.opening_zh || hook.opening_en);
  return `<label class="hook-row ${selected ? 'selected' : ''}"><input type="radio" name="hook" value="${esc(hook.hook_record_id)}" ${selected ? 'checked' : ''}><span class="hook-index">${String(hook.index || 1).padStart(2, '0')}</span><span class="hook-body"><b>${esc(hook.concept || hook.hook_concept || '未命名 Hook')}</b><span class="hook-opening">${withBreaks(opening || '暂无开头文案')}</span><span class="hook-tags"><i>${esc(hook.hook_category || 'Hook')}</i><i>${esc(hook.awareness_stage || '产品认知')}</i><i>${esc(hook.emotional_trigger || '情绪触发')}</i></span><small>${esc(hook.visual_opening || hook.scene || hook.benefit_bridge || '从产品细节进入，连接核心卖点')}</small></span><span class="hook-score">${esc(hook.score || '—')}<small>/10</small></span><span class="hook-arrow">${selected ? '✓' : '→'}</span></label>`;
}

function renderScriptPage() {
  if (!state.script) return renderGate(3, '脚本还没有生成', '在第 02 步选择一个 Hook，结构化脚本会出现在右侧。');
  const s = state.script.script_preview || {};
  const language = state.script.language || state.product?.language || '中文';
  const full = language === '英文' ? (s.full_script_en || s.full_script) : (s.full_script_zh || s.full_script);
  return `<section class="page-section">${renderPageHeader('03 / SCRIPT REVIEW', '把选中的角度变成一条脚本。', '语言从第 01 步继承，视频层只负责执行已经确认的脚本。', `<span>${esc(language)}</span><strong>脚本待确认</strong>`)}<div class="split-view script-view"><section class="input-panel review-panel"><div class="panel-heading"><span class="panel-index">03</span><div><b>进入视频前检查</b><small>确认后创建视频任务</small></div></div><div class="review-line"><span>内容类型</span><b>${esc(state.contentType)}</b></div><div class="review-line"><span>脚本语言</span><b>${esc(language)}</b></div><div class="review-line"><span>Hook 状态</span><b>已选择</b></div><label class="confirm-line"><input id="confirm-script" type="checkbox" ${state.scriptConfirmed ? 'checked' : ''}><span>我确认这版脚本可以进入视频生成</span></label><button class="primary full" type="button" data-action="make-video-task" ${!state.scriptConfirmed || state.busy ? 'disabled' : ''}><span>${state.busy ? '准备中…' : '确认脚本并进入视频'}</span><b>→</b></button><button class="secondary full" type="button" data-action="back-hooks">返回 Hook</button></section><section class="result-panel script-result"><div class="result-toolbar"><div><span class="result-label">OUTPUT / WORKING SCRIPT</span><h2>${esc(s.title || '结构化脚本')}</h2></div><span class="pill">${esc(language)}</span></div><div class="script-copy">${withBreaks(full || '暂未收到脚本内容')}</div><div class="script-meta"><div><span>口播</span><p>${withBreaks(s.voiceover || '无口播')}</p></div><div><span>CTA</span><p>${withBreaks(language === '英文' ? (s.cta_en || s.cta_zh) : (s.cta_zh || s.cta_en) || '无')}</p></div><div><span>画面逻辑</span><p>${withBreaks(s.shot_summary || '已写入视频任务')}</p></div></div></section></div></section>`;
}

function renderVideoPage() {
  if (!state.videoTask) return renderGate(4, '视频任务还没有准备好', '确认第 03 步脚本后，视频执行结果会出现在这里。');
  const task = state.videoTask.task_preview || {};
  const final = state.final;
  const url = getVideoUrl(final);
  const playable = isPlayable(url);
  const productImageUrl = state.product?.product_image_url || task.image_source || '等待产品素材地址回写';
  const scriptText = state.script?.script_preview?.full_script_zh || state.script?.script_preview?.full_script_en || state.script?.script_preview?.full_script || '已确认脚本将作为视频生成依据。';
  return `<section class="page-section video-page">${renderPageHeader('04 / VIDEO', playable ? '成片已经返回。' : final ? '视频任务已提交。' : '最后生成视频。', playable ? '结果会出现在右侧。' : '只执行已经确认的脚本和素材。', `<span>ENGINE</span><strong>SEEDANCE 2.0</strong>`)}<div class="split-view video-workspace"><section class="input-panel video-input-panel"><div class="panel-heading"><span class="panel-index">04</span><div><b>生成参数</b><small>上游内容已锁定</small></div></div><label class="field"><span>内容类型</span><input value="${esc(task.content_type || state.contentType)}" readonly></label><label class="field"><span>产品素材</span><input value="${esc(productImageUrl)}" readonly></label><label class="field"><span>已确认脚本</span><textarea rows="5" readonly>${esc(scriptText)}</textarea></label><div class="video-mini-meta"><span>${esc(task.language || state.product?.language || '中文')}</span><span>${esc(task.product_name || state.brief?.product || state.product?.product_name || '产品')}</span></div>${!final ? `<button class="primary full" type="button" data-action="run-video" ${state.busy ? 'disabled' : ''}><span>${state.busy ? '生成任务提交中…' : '开始生成成片'}</span><b>→</b></button>` : ''}<button class="secondary full" type="button" data-action="back-script">返回脚本</button></section><section class="video-result-panel">${renderVideoOutput(final, url, playable)}</section></div></section>`;
}

function renderVideoOutput(final, url, playable) {
  if (!final) return `<div class="video-empty"><div class="video-glyph">▶</div><span class="result-label">OUTPUT / FINAL VIDEO</span><h2>成片结果会出现在这里</h2><p>点击右侧开始生成。返回真实视频地址后，播放器、打开和下载操作会自动出现。</p></div>`;
  if (playable) return `<div class="video-player-wrap"><video class="video-player" controls playsinline preload="metadata" src="${esc(url)}"></video><div class="media-actions"><a href="${esc(url)}" target="_blank" rel="noreferrer">打开视频 ↗</a><a href="${esc(url)}" download>下载成片 ↓</a></div></div>`;
  return `<div class="video-empty returned"><div class="video-glyph">◷</div><span class="result-label">OUTPUT / TASK STATUS</span><h2>${esc(final.status || '视频生成中')}</h2><p>n8n 已返回任务状态，但当前还没有可播放的视频 URL。请等待轮询完成或检查对象存储回写。</p><div class="status-line"><span>任务状态</span><b>${esc(final.video_status || final.status || 'processing')}</b></div></div>`;
}

function renderGate(stage, title, description) {
  return `<section class="gate"><span class="gate-number">0${stage}</span><div><span class="kicker">STAGE ${String(stage).padStart(2, '0')} / WAITING</span><h1>${esc(title)}</h1><p>${esc(description)}</p></div></section>`;
}

function getVideoUrl(value) {
  if (!value) return '';
  return value.video_url || value.output_url || value.file_url || value.result?.video_url || value.data?.video_url || '';
}

function isPlayable(url) {
  return /^https?:\/\//i.test(String(url || '')) && !/example\.com|placeholder/i.test(String(url));
}

function formObject(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  return data;
}

function backendContentType() {
  return state.contentType === '达人带货视频' ? '固定达人口播' : state.contentType === 'TVC广告' ? '高端产品展示TVC' : '种草视频';
}

function normalizeBrief(response, body) {
  const raw = response.product_brief || response.brief || response.product_summary || response.strategy || {};
  const b = typeof raw === 'string' ? { summary: raw } : raw;
  return {
    product: b.product || b.product_name || response.product_name || body.product_name || '待命名产品',
    category: b.category || b.product_category || response.product_category || '待识别',
    audience: b.audience || b.target_audience || response.target_audience || body.target_audience || '待识别',
    benefits: lines(b.benefits || b.core_benefits || response.core_benefits || body.selected_benefits),
    direction: b.direction || b.positioning || b.campaign_direction || '',
    summary: b.summary || response.product_summary || '',
  };
}

function normalizeHooks(response) {
  if (Array.isArray(response.hooks) && response.hooks.length) return response.hooks;
  if (Array.isArray(response.items) && response.items.length) return response.items;
  if (Array.isArray(response.hook_record_ids)) return response.hook_record_ids.map((id, index) => ({ hook_record_id: id, index: index + 1, concept: `Hook ${index + 1}`, opening_zh: '等待 Hook 详情回写', hook_category: '待分类', awareness_stage: '产品认知', emotional_trigger: '待识别', score: '—' }));
  return [];
}

async function request(path, body, multipart = false) {
  if (demoMode) return demoResponse(path, body);
  const response = await fetch(path, { method: 'POST', body: multipart ? body : JSON.stringify(body), headers: multipart ? {} : { 'Content-Type': 'application/json' } });
  const raw = await response.text();
  let data;
  try { data = JSON.parse(raw); } catch { data = { ok: false, message: raw || `HTTP ${response.status}` }; }
  if (!response.ok || data.ok === false) throw new Error(data.message || data.error_message || `工作流执行失败（${response.status}）`);
  return data;
}

async function run(action) {
  setState({ busy: true, error: '', message: '' });
  try { await action(); } catch (error) { setState({ busy: false, error: error.message || String(error) }); }
}

async function submitUrl(event) {
  event.preventDefault();
  const body = formObject(event.currentTarget);
  if (state.contentType === 'TVC广告') return setState({ error: 'TVC 广告请切换到产品白底图入口。' });
  body.content_type = backendContentType();
  await run(async () => {
    const response = await request('/api/workflow/stage-1/url', body);
    const brief = normalizeBrief(response, body);
    const hooks = normalizeHooks(response);
    setState({ busy: false, stage: 2, completed: 1, product: { ...body, product_name: brief.product, product_record_id: response.product_record_id, language: body.language, content_type: body.content_type }, brief, hooks, selectedHookId: '', message: `产品简报已完成，右侧收到 ${hooks.length || 0} 个 Hook 结果。` });
  });
}

async function submitImage(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const file = form.querySelector('#product-image')?.files?.[0];
  const data = formObject(form);
  if (!file) return setState({ error: '请先选择产品白底图。' });
  if (!lines(data.selected_benefits).length) return setState({ error: '白底图入口必须填写重要产品卖点。' });
  const payload = new FormData();
  Object.entries(data).forEach(([key, value]) => { if (key !== 'product_image') payload.append(key, value); });
  payload.append('content_type', backendContentType());
  payload.append('file_name', file.name);
  payload.append('product_image', file, file.name);
  await run(async () => {
    const response = await request('/api/workflow/stage-1/tvc', payload, true);
    const brief = normalizeBrief(response, data);
    const hooks = normalizeHooks(response);
    setState({ busy: false, stage: 2, completed: 1, product: { ...data, file_name: file.name, product_name: brief.product, product_record_id: response.product_record_id, product_image_url: response.product_image_url || '', language: data.language, content_type: '高端产品展示TVC' }, brief, hooks, selectedHookId: '', message: `产品简报已完成，右侧收到 ${hooks.length || 0} 个 Hook 结果。` });
  });
}

async function makeScript() {
  const hook = state.hooks.find(item => item.hook_record_id === state.selectedHookId);
  if (!hook) return setState({ error: '请先从右侧选择一个 Hook。' });
  await run(async () => {
    const response = await request('/api/workflow/stage-2', { product_record_id: state.product.product_record_id, hook_record_id: hook.hook_record_id, content_type: state.product.content_type, language: state.product.language });
    setState({ busy: false, stage: 3, completed: 2, script: response, scriptConfirmed: false, message: '脚本结果已生成，请检查后继续。' });
  });
}

async function makeVideoTask() {
  if (!state.scriptConfirmed) return setState({ error: '请先确认脚本内容。' });
  await run(async () => {
    const response = await request('/api/workflow/stage-3', { script_record_id: state.script.script_record_id, product_record_id: state.product.product_record_id, hook_record_id: state.script.hook_record_id || state.selectedHookId, language: state.script.language || state.product.language, content_type: state.product.content_type, confirm_script: true });
    setState({ busy: false, stage: 4, completed: 3, videoTask: response, final: null, message: '脚本已确认，视频任务已经准备好。' });
  });
}

async function runVideo() {
  if (!state.videoTask?.video_task_record_id) return setState({ error: '缺少视频任务 ID。' });
  await run(async () => {
    const response = await request('/api/workflow/stage-4', { video_task_record_id: state.videoTask.video_task_record_id });
    setState({ busy: false, completed: 4, final: response, message: isPlayable(getVideoUrl(response)) ? '成片已返回，可以播放和下载。' : '任务已返回，正在等待视频地址回写。' });
  });
}

function createDemoHooks() {
  const rows = [
    ['问题切入', '问题意识', '好奇', '你买产品，第一眼到底在看什么？', '从用户真实判断开始，让产品自然出现。'],
    ['视觉展示', '产品认知', '惊喜', '光线一转，细节就出来了。', '用材质、纹理和高光建立第一眼记忆。'],
    ['情绪向往', '问题意识', '向往', '真正懂生活的人，会在意这一处。', '把产品放进用户想要的生活状态。'],
    ['产品特写', '产品认知', '质感', '先让质感说话。', '微距放大产品结构和工艺。'],
    ['场景切入', '问题意识', '安心', '每天都在用，为什么还要将就？', '从使用场景进入产品价值。'],
    ['反常识', '方案比较', '好奇', '贵的不是包装，是这一层细节。', '用一个判断建立记忆点。'],
    ['对比验证', '方案比较', '信任', '同样的场景，差别在这里。', '把卖点放进可感知的对比。'],
    ['长期陪伴', '购买决策', '安心', '给自己一件每天都想用的东西。', '从功能转向长期陪伴感。'],
    ['生活方式', '购买决策', '向往', '把高级感留在每天的细节里。', '用克制画面表达生活质感。'],
    ['手持体验', '产品认知', '惊喜', '拿起来的第一秒，就知道不一样。', '用手感和动作完成判断。'],
    ['分享冲动', '购买决策', '好奇', '这一眼，值得被拍下来。', '让产品成为内容里的视觉锚点。'],
    ['明确推荐', '购买决策', '信任', '如果只能推荐一个，我会选它。', '用明确选择完成推荐。'],
  ];
  return rows.map((row, index) => ({ hook_record_id: `demo-hook-${index + 1}`, index: index + 1, hook_category: row[0], awareness_stage: row[1], emotional_trigger: row[2], concept: row[3], opening_zh: row[3], opening_en: ['What do you really notice first?', 'One turn of light reveals the detail.', 'People who care about life notice this.', 'Let the texture speak first.', 'Why settle for less every day?', 'The price is in this detail.', 'The difference is right here.', 'Choose something you want to use every day.', 'Keep the luxury in the everyday.', 'You can feel the difference in one second.', 'This deserves to be seen.', 'If I recommend one, it is this one.'][index], visual_opening: row[4], benefit_bridge: '自然连接产品卖点', score: (9.4 - index * 0.13).toFixed(1) }));
}

function demoResponse(path, body) {
  if (path.includes('stage-1')) {
    const isTvc = body.content_type === '高端产品展示TVC';
    const name = body.product_name || (isTvc ? '示例高端香水' : '示例产品');
    const hooks = createDemoHooks();
    return { ok: true, product_record_id: 'demo-product-001', product_name: name, language: body.language || '中文', content_type: body.content_type || '种草视频', product_image_url: '', product_brief: { product: name, category: isTvc ? '高端香水 / 美妆' : '生活方式产品', audience: '关注品质、审美与真实使用体验的消费者', benefits: lines(body.selected_benefits).length ? lines(body.selected_benefits) : ['材质与细节值得被看见', '进入真实生活场景', '高级但不过度张扬'], direction: isTvc ? '以产品本身为唯一主角，用克制光影完成高级展示。' : '从真实使用场景切入，把卖点转译成可感知的体验。' }, hooks };
  }
  if (path.includes('stage-2')) return { ok: true, script_record_id: 'demo-script-001', product_record_id: body.product_record_id, hook_record_id: body.hook_record_id, language: body.language || '中文', content_type: body.content_type, script_preview: { title: '让产品自己成为记忆点', full_script_zh: '你不需要解释每一个细节。让光线、质感和它进入生活的方式，替用户把选择变得清楚。', full_script_en: 'You do not need to explain every detail. Let the light, the texture, and the way it fits into real life make the choice feel obvious.', voiceover: body.content_type === '高端产品展示TVC' ? '' : '你不需要解释每一个细节。让产品自己成为记忆点。', cta_zh: '现在了解更多', cta_en: 'Discover more', shot_summary: '开场停留 → 卖点出现 → 使用场景 → 产品与 CTA 收束' } };
  if (path.includes('stage-3')) return { ok: true, video_task_record_id: 'demo-video-001', product_record_id: body.product_record_id, script_record_id: body.script_record_id, content_type: body.content_type, language: body.language, task_preview: { title: '让产品自己成为记忆点', product_name: state.brief?.product || '示例产品', content_type: body.content_type, language: body.language, image_source: body.content_type === '高端产品展示TVC' ? '白底产品图 / public URL' : body.content_type === '固定达人口播' ? '01 阶段文生图：固定达人手持产品图' : '网页抓取产品图', video_prompt: '使用已确认脚本和上游素材；Seedance 2.0 图生视频；保持产品真实结构。', voiceover: body.content_type === '高端产品展示TVC' ? '' : '你不需要解释每一个细节。让产品自己成为记忆点。' } };
  return { ok: true, status: '视频任务已提交', video_status: 'processing', provider: 'Seedance 2.0', postprocess: '等待视频地址回写；ChatCut 可用于后处理' };
}

function demoProductState() {
  const body = { product_name: '演示产品', language: '中文', content_type: backendContentType(), selected_benefits: '材质与细节值得被看见；进入真实生活场景' };
  const response = demoResponse('/api/workflow/stage-1/url', body);
  return { product: { ...body, product_record_id: response.product_record_id }, brief: normalizeBrief(response, body), hooks: normalizeHooks(response) };
}

function openDemoStage(id) {
  const productState = demoProductState();
  const hook = productState.hooks[0];
  const script = demoResponse('/api/workflow/stage-2', { product_record_id: productState.product.product_record_id, hook_record_id: hook.hook_record_id, content_type: productState.product.content_type, language: productState.product.language });
  if (id === 2) return setState({ ...productState, stage: 2, completed: 1, selectedHookId: '', message: '演示结果已加载，可以直接查看右侧 Hook。', error: '' });
  if (id === 3) return setState({ ...productState, stage: 3, completed: 2, selectedHookId: hook.hook_record_id, script, scriptConfirmed: false, message: '演示脚本已加载，可以直接查看脚本结果。', error: '' });
  const videoTask = demoResponse('/api/workflow/stage-3', { product_record_id: productState.product.product_record_id, script_record_id: script.script_record_id, hook_record_id: hook.hook_record_id, content_type: productState.product.content_type, language: productState.product.language });
  return setState({ ...productState, stage: 4, completed: 3, selectedHookId: hook.hook_record_id, script, scriptConfirmed: true, videoTask, final: null, message: '演示视频结果页已加载，可以查看执行信息。', error: '' });
}

function bindEvents() {
  document.querySelectorAll('[data-stage]').forEach(button => button.addEventListener('click', () => {
    const id = Number(button.dataset.stage);
    if (!canOpen(id)) {
      if (demoMode && id > 1) return openDemoStage(id);
      return setState({ error: `请先完成第 ${String(id - 1).padStart(2, '0')} 步。` });
    }
    setState({ stage: id, error: '', message: '' });
  }));
  document.querySelectorAll('[data-content-type]').forEach(button => button.addEventListener('click', () => {
    const type = button.dataset.contentType;
    setState({ contentType: type, sourceMode: type === 'TVC广告' ? 'image' : state.sourceMode, product: { ...state.product, content_type: type === '达人带货视频' ? '固定达人口播' : type === 'TVC广告' ? '高端产品展示TVC' : '种草视频' }, error: '' });
  }));
  document.querySelectorAll('[data-source]').forEach(button => button.addEventListener('click', () => {
    if (state.contentType === 'TVC广告' && button.dataset.source === 'url') return setState({ error: 'TVC 广告请使用产品白底图入口。' });
    setState({ sourceMode: button.dataset.source, error: '' });
  }));
  document.querySelectorAll('[data-filter]').forEach(select => select.addEventListener('change', event => setState({ filters: { ...state.filters, [event.target.dataset.filter]: event.target.value } })));
  document.querySelectorAll('input[name="hook"]').forEach(input => input.addEventListener('change', event => setState({ selectedHookId: event.target.value, error: '' })));
  document.querySelectorAll('.hook-row').forEach(row => row.addEventListener('click', event => {
    if (event.target.closest('input[name="hook"]')) return;
    event.preventDefault();
    const input = row.querySelector('input[name="hook"]');
    if (input) setState({ selectedHookId: input.value, error: '' });
  }));
  document.querySelector('#url-form')?.addEventListener('submit', submitUrl);
  document.querySelector('#image-form')?.addEventListener('submit', submitImage);
  document.querySelector('[data-action="make-script"]')?.addEventListener('click', makeScript);
  document.querySelector('[data-action="make-video-task"]')?.addEventListener('click', makeVideoTask);
  document.querySelector('[data-action="run-video"]')?.addEventListener('click', runVideo);
  document.querySelector('[data-action="back-hooks"]')?.addEventListener('click', () => setState({ stage: 2, error: '', message: '' }));
  document.querySelector('[data-action="back-script"]')?.addEventListener('click', () => setState({ stage: 3, final: null, error: '', message: '' }));
  document.querySelector('[data-action="clear-alert"]')?.addEventListener('click', () => setState({ error: '', message: '' }));
  document.querySelector('[data-action="reset"]')?.addEventListener('click', () => { localStorage.removeItem(STORAGE_KEY); state = initialState(); render(); });
  document.querySelector('#confirm-script')?.addEventListener('change', event => setState({ scriptConfirmed: event.target.checked, error: '' }));
  document.querySelector('#product-image')?.addEventListener('change', event => { const name = event.target.files?.[0]?.name; if (name) { const label = document.querySelector('.upload-name'); if (label) label.textContent = name; } });
}

render();

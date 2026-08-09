import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { mkdir, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';
import { tmpdir } from 'node:os';
import { execFile } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const execFileAsync = promisify(execFile);
const root = fileURLToPath(new URL('.', import.meta.url)).replace(/[\\/]$/, '');
const port = Number(process.env.PORT || 4174);
const n8nBaseUrl = String(process.env.N8N_BASE_URL || 'http://localhost:5678').replace(/\/+$/, '');
const pythonBaseUrl = String(process.env.PYTHON_SERVICE_URL || 'http://127.0.0.1:8787').replace(/\/+$/, '');
const webhookPrefix = String(process.env.N8N_WEBHOOK_PREFIX || 'webhook').replace(/^\/+|\/+$/g, '');
const requestTimeoutMs = Number(process.env.N8N_REQUEST_TIMEOUT_MS || 180000);
const videoRequestTimeoutMs = Number(process.env.N8N_VIDEO_REQUEST_TIMEOUT_MS || 600000);
const runtimeDirectory = join(root, 'runtime');
const latestVideoPath = join(runtimeDirectory, 'latest-video.json');
const videoTasksDirectory = join(runtimeDirectory, 'video-tasks');
const pythonInflight = new Map();

const workflowRoutes = {
  '/api/workflow/stage-2/optimize': process.env.N8N_STAGE2_OPTIMIZE_WORKFLOW || 'ai-ad-hook-optimize',
  '/api/workflow/stage-4': process.env.N8N_STAGE4_WORKFLOW || 'ai-ad-video-task-v2',
  '/api/workflow/stage-5': process.env.N8N_STAGE5_WORKFLOW || 'aigc-storyboard-images-v1',
  '/api/workflow/stage-6': process.env.N8N_STAGE6_WORKFLOW || 'ai-ad-video-concat',
};

const postRoutes = { ...workflowRoutes };

const pythonRoutes = {
  '/api/fast/stage-1': '/stage-1',
  '/api/fast/stage-2': '/stage-2',
  '/api/fast/stage-3': '/stage-3',
  '/api/media/edit': '/media/edit',
  '/api/media/align-subtitles': '/media/align-subtitles',
  '/api/media/jianying-package': '/media/jianying-package',
  '/api/media/chatcut-handoff': '/media/chatcut-handoff',
  '/api/providers/topaz/enhance': '/providers/topaz/enhance',
  '/api/providers/topaz/status': '/providers/topaz/status',
  '/api/providers/minimax/music': '/providers/minimax/music',
  '/api/providers/kie/character': '/providers/kie/character',
  '/api/providers/kie/storyboard': '/providers/kie/storyboard',
  '/api/providers/kie/overseas-video': '/providers/kie/overseas-video',
  '/api/providers/kie/status': '/providers/kie/status',
};

async function persistUploadedImages(payload) {
  if (!Array.isArray(payload) || !payload.length) throw new Error('图片请求格式无效');
  const upstream = await fetch(`${pythonBaseUrl}/upload-images`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload.slice(0, 9)),
      signal: AbortSignal.timeout(60000),
  });
  const responseText = await upstream.text();
  if (!upstream.ok) {
    let message = responseText;
    try { message = JSON.parse(responseText).message || JSON.parse(responseText).error || responseText; } catch {}
    throw new Error(`Python 图片上传失败 (HTTP ${upstream.status}): ${String(message).slice(0, 200)}`);
  }
  const result = JSON.parse(responseText || '{}');
  return Array.isArray(result.images) ? result.images : [];
}

const disabledLegacyContentRoutes = new Set([
  '/api/workflow/stage-1/url',
  '/api/workflow/stage-1/document',
  '/api/workflow/stage-1/tvc',
  '/api/workflow/stage-2',
  '/api/workflow/stage-3',
]);

const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.mp4': 'video/mp4',
  '.mov': 'video/quicktime',
  '.webm': 'video/webm',
};

function send(res, status, body, type = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  res.end(body);
}

const videoUrlKeys = [
  'video_url', 'videoUrl', 'result_url', 'resultUrl', 'public_url', 'publicUrl',
  'output_url', 'outputUrl', 'download_url', 'downloadUrl', 'resultUrls',
  'result_urls', 'fullResultUrls', 'full_result_urls', 'urls', 'url',
];

function findVideoUrls(value, depth = 0, found = [], seen = new Set()) {
  if (depth > 12 || value == null || found.length >= 50) return found;
  if (typeof value === 'string') {
    if (/^https?:\/\/\S+$/i.test(value)) {
      if (!found.includes(value)) found.push(value);
      return found;
    }
    try { return findVideoUrls(JSON.parse(value), depth + 1, found, seen); } catch { return found; }
  }
  if (typeof value !== 'object' || seen.has(value)) return found;
  seen.add(value);
  if (Array.isArray(value)) {
    for (const item of value) findVideoUrls(item, depth + 1, found, seen);
    return found;
  }
  for (const key of videoUrlKeys) {
    if (value[key] != null) findVideoUrls(value[key], depth + 1, found, seen);
  }
  for (const child of Object.values(value)) findVideoUrls(child, depth + 1, found, seen);
  return found;
}

function findVideoUrl(value) {
  return findVideoUrls(value)[0] || '';
}

function normalizeVideoResponse(responseBody) {
  let payload;
  try { payload = JSON.parse(Buffer.from(responseBody).toString('utf8') || '{}'); } catch { return responseBody; }
  const urls = findVideoUrls(payload);
  if (!urls.length) return responseBody;
  const segments = urls.map((url, index) => ({
    segment_index: index + 1,
    total_segments: urls.length,
    video_url: url,
    url,
    status: 'completed',
  }));
  const videoUrl = (urls[0] && urls[0].startsWith('http')) ? urls[0] : (payload.video_url?.startsWith?.('http') ? payload.video_url : '');
  const normalized = Array.isArray(payload)
    ? { ok: true, status: 'completed', raw: payload, segments, video_url: videoUrl, result_url: videoUrl, count: urls.length }
    : { ...payload, ok: payload.ok !== false, status: payload.status || 'completed', segments: payload.segments?.length ? payload.segments : segments, video_url: videoUrl, result_url: videoUrl, count: payload.count || urls.length };
  return Buffer.from(JSON.stringify(normalized));
}

async function saveLatestVideo(requestBody, responseBody) {
  try {
    const requestPayload = JSON.parse(requestBody.toString('utf8') || '{}');
    const responseText = Buffer.from(responseBody).toString('utf8');
    const responsePayload = JSON.parse(responseText || '{}');
    const videoUrl = findVideoUrl(responsePayload);
    if (!videoUrl) return;
    await mkdir(runtimeDirectory, { recursive: true });
    const urls = findVideoUrls(responsePayload);
    const segments = urls.map((url, index) => ({
      segment_index: index + 1,
      total_segments: urls.length,
      video_url: url,
      url,
      status: 'completed',
    }));
    await writeFile(latestVideoPath, JSON.stringify({
      ok: true,
      status: 'completed',
      video_url: videoUrl,
      result_url: videoUrl,
      segments,
      count: segments.length,
      video_task_id: requestPayload.video_task_id || '',
      product_record_id: requestPayload.product_record_id || '',
      product_brief: requestPayload.product_brief || null,
      hook: requestPayload.hook || null,
      creative_plan: requestPayload.creative_plan || requestPayload.selected_plan || null,
      selected_mood_board: requestPayload.selected_mood_board || null,
      selected_plan_id: requestPayload.selected_plan_id || '',
      resolution: requestPayload.resolution || '480p',
      no_subtitles: requestPayload.no_subtitles === true,
      knowledge_trace: requestPayload.knowledge_trace || {},
      pipeline_trace: requestPayload.pipeline_trace || {},
      duration: requestPayload.duration || 15,
      updated_at: new Date().toISOString(),
    }, null, 2));
  } catch (error) {
    console.warn(`无法保存最近成片：${error.message}`);
  }
}

function safeTaskId(value) {
  return String(value || '').trim().replace(/[^a-zA-Z0-9._-]/g, '').slice(0, 160);
}

function videoTaskPath(taskId) {
  const safe = safeTaskId(taskId);
  if (!safe) throw new Error('缺少 video_task_id');
  return join(videoTasksDirectory, `${safe}.json`);
}

async function readVideoTask(taskId) {
  return JSON.parse(await readFile(videoTaskPath(taskId), 'utf8'));
}

async function writeVideoTask(taskId, patch) {
  await mkdir(videoTasksDirectory, { recursive: true });
  let current = {};
  try { current = await readVideoTask(taskId); } catch {}
  const next = { ...current, ...patch, video_task_id: safeTaskId(taskId), updated_at: new Date().toISOString() };
  await writeFile(videoTaskPath(taskId), JSON.stringify(next, null, 2));
  return next;
}

async function readRequestBody(req, maxBytes = 30 * 1024 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > maxBytes) throw new Error('文件过大，单次上传请控制在 25MB 内');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

function decodeXmlText(xml) {
  return String(xml)
    .replace(/<\/(?:w:p|a:p|row|si)>/g, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/[ \t]+/g, ' ')
    .replace(/\n\s+/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function imageMime(name) {
  const extension = extname(name).toLowerCase();
  return {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
  }[extension] || '';
}

async function unzipEntry(filePath, entry, binary = false) {
  const { stdout } = await execFileAsync('unzip', ['-p', filePath, entry], {
    encoding: binary ? 'buffer' : 'utf8',
    maxBuffer: 30 * 1024 * 1024,
  });
  return stdout;
}

async function extractOfficeDocument(filePath, extension) {
  const { stdout } = await execFileAsync('unzip', ['-Z1', filePath], {
    encoding: 'utf8',
    maxBuffer: 4 * 1024 * 1024,
  });
  const entries = stdout.split(/\r?\n/).filter(Boolean);
  const textPatterns = extension === '.docx'
    ? [/^word\/document\.xml$/]
    : extension === '.pptx'
      ? [/^ppt\/slides\/slide\d+\.xml$/]
      : [/^xl\/sharedStrings\.xml$/, /^xl\/worksheets\/sheet\d+\.xml$/];
  const mediaPrefix = extension === '.docx' ? 'word/media/' : extension === '.pptx' ? 'ppt/media/' : 'xl/media/';
  const textEntries = entries
    .filter((entry) => textPatterns.some((pattern) => pattern.test(entry)))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  const textParts = [];
  for (const entry of textEntries) {
    const text = decodeXmlText(await unzipEntry(filePath, entry));
    if (text) textParts.push(text);
  }
  const imageEntries = entries.filter((entry) => entry.startsWith(mediaPrefix) && imageMime(entry)).slice(0, 9);
  const images = [];
  for (const entry of imageEntries) {
    const data = await unzipEntry(filePath, entry, true);
    const mime = imageMime(entry);
    if (data.length <= 5 * 1024 * 1024) {
      images.push({
        name: entry.split('/').pop(),
        mime,
        dataUrl: `data:${mime};base64,${data.toString('base64')}`,
      });
    }
  }
  return { text: textParts.join('\n\n'), images };
}

async function extractProductDocument(req, res) {
  let tempDirectory = '';
  try {
    const rawBody = await readRequestBody(req);
    const payload = JSON.parse(rawBody.toString('utf8') || '{}');
    const extension = extname(String(payload.name || '')).toLowerCase();
    if (!['.docx', '.xlsx', '.pptx'].includes(extension)) {
      send(res, 415, JSON.stringify({ ok: false, message: '仅支持 DOCX、XLSX 和 PPTX 文件' }));
      return;
    }
    const match = String(payload.dataUrl || '').match(/^data:[^;]+;base64,(.+)$/s);
    if (!match) throw new Error('文件内容无效');
    tempDirectory = await mkdtemp(join(tmpdir(), 'adflow-document-'));
    const filePath = join(tempDirectory, `product${extension}`);
    await writeFile(filePath, Buffer.from(match[1], 'base64'));
    const result = await extractOfficeDocument(filePath, extension);
    if (!result.text && !result.images.length) throw new Error('没有从文件中提取到可用内容');
    send(res, 200, JSON.stringify({
      ok: true,
      name: payload.name,
      text: result.text,
      images: result.images,
    }));
  } catch (error) {
    send(res, 400, JSON.stringify({ ok: false, message: error.message }));
  } finally {
    if (tempDirectory) await rm(tempDirectory, { recursive: true, force: true });
  }
}

async function proxyPost(req, res, pathname) {
  const workflowPath = postRoutes[pathname];
  let body = await readRequestBody(req);
  // External video providers cannot fetch browser-local blob: URLs. Keep only
  // uploaded HTTPS assets in the stage-4 payload.
  if (pathname === '/api/workflow/stage-4') {
    try {
      const parsed = JSON.parse(body);
      const isRemote = (value) => typeof value === 'string' && /^https:\/\//i.test(value);
      if (!isRemote(parsed.product_image_url)) parsed.product_image_url = '';
      if (!isRemote(parsed.storyboard_image)) parsed.storyboard_image = '';
      if (Array.isArray(parsed.product_images)) parsed.product_images = parsed.product_images.filter(isRemote);
      if (Array.isArray(parsed.storyboard_images)) parsed.storyboard_images = parsed.storyboard_images.filter((item) => {
        const value = typeof item === 'string' ? item : item?.url || item?.image_url;
        return isRemote(value);
      });
      parsed.callback_url = `http://127.0.0.1:${port}/api/video/callback`;
      body = JSON.stringify(parsed);
    } catch {
      // Let n8n return its normal validation error for malformed payloads.
    }
  }
  const headers = {};
  if (req.headers['content-type']) headers['content-type'] = req.headers['content-type'];
  const target = `${n8nBaseUrl}/${webhookPrefix}/${workflowPath}`;
  const timeoutMs = pathname === '/api/workflow/stage-4' || pathname === '/api/workflow/stage-6'
    ? videoRequestTimeoutMs
    : requestTimeoutMs;

  try {
    const upstream = await fetch(target, {
      method: 'POST',
      headers,
      body,
      signal: AbortSignal.timeout(timeoutMs),
    });
    let responseBody = Buffer.from(await upstream.arrayBuffer());
    if (pathname === '/api/workflow/stage-4' && upstream.ok) {
      const responsePayload = JSON.parse(responseBody.toString('utf8') || '{}');
      const requestPayload = JSON.parse(body.toString('utf8') || '{}');
      const taskId = responsePayload.video_task_id || requestPayload.video_task_id;
      if (responsePayload.status === 'queued' && taskId) {
        await writeVideoTask(taskId, {
          ok: true,
          status: 'queued',
          submitted_at: new Date().toISOString(),
          request: requestPayload,
        });
      } else {
        responseBody = normalizeVideoResponse(responseBody);
        await saveLatestVideo(body, responseBody);
      }
    }
    res.writeHead(upstream.status, {
      'Content-Type': upstream.headers.get('content-type') || 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(Buffer.from(responseBody));
  } catch (error) {
    const timedOut = error.name === 'TimeoutError';
    send(res, timedOut ? 504 : 502, JSON.stringify({
      ok: false,
      error: timedOut ? 'n8n_timeout' : 'n8n_unreachable',
      message: timedOut ? 'n8n 工作流执行超时' : `无法连接 n8n：${error.message}`,
      target,
    }));
  }
}

async function proxyPython(req, res, pathname) {
  const body = await readRequestBody(req, 40 * 1024 * 1024);
  const target = `${pythonBaseUrl}${pythonRoutes[pathname]}`;
  let dedupeKey = '';
  if (pathname === '/api/fast/stage-1') {
    try {
      const payload = JSON.parse(body.toString('utf8') || '{}');
      // Old and new Stage 1 listeners can submit slightly different optional
      // fields. Normalize the stable product inputs so repeated clicks share
      // one upstream generation instead of starting multiple model calls.
      dedupeKey = createHash('sha256').update(JSON.stringify({
        product_url: payload.product_url || '',
        campaign_theme: payload.campaign_theme || '',
        content_type: payload.content_type || '真人口播带货',
        language: payload.language || '中文',
        product_images: payload.product_images || [],
        document_text: payload.document_text || '',
        filter_values: payload.filter_values || {},
        resolution: payload.resolution || '480p',
      })).digest('hex');
    } catch {
      dedupeKey = createHash('sha256').update(body).digest('hex');
    }
  }
  const requestKey = dedupeKey ? `${pathname}:${dedupeKey}` : '';
  let requestPromise = requestKey ? pythonInflight.get(requestKey) : null;
  if (!requestPromise) {
    requestPromise = (async () => {
      const upstream = await fetch(target, {
        method: 'POST',
        headers: { 'content-type': req.headers['content-type'] || 'application/json' },
        body,
        signal: AbortSignal.timeout(
          pathname === '/api/fast/stage-1'
            ? 10 * 60 * 1000
            : pathname.startsWith('/api/media/')
              ? 15 * 60 * 1000
              : requestTimeoutMs
        ),
      });
      return {
        status: upstream.status,
        contentType: upstream.headers.get('content-type') || 'application/json; charset=utf-8',
        body: Buffer.from(await upstream.arrayBuffer()),
      };
    })();
    if (requestKey) pythonInflight.set(requestKey, requestPromise);
  } else {
    console.warn(`[python] duplicate Stage 1 request joined: ${requestKey.slice(-12)}`);
  }
  try {
    const result = await requestPromise;
    console.info(`[python] ${pathname} -> ${result.status}${requestKey ? ` (${requestKey.slice(-12)})` : ''}`);
    res.writeHead(result.status, {
      'Content-Type': result.contentType,
      'Cache-Control': 'no-store',
    });
    res.end(result.body);
  } catch (error) {
    const timedOut = error.name === 'TimeoutError';
    console.warn(`[python] ${pathname} failed: ${error.message}`);
    send(res, timedOut ? 504 : 502, JSON.stringify({
      ok: false,
      error: timedOut ? 'python_timeout' : 'python_unreachable',
      message: timedOut ? 'Python 服务执行超时' : `无法连接 Python 服务：${error.message}`,
      target,
    }));
  } finally {
    if (requestKey && pythonInflight.get(requestKey) === requestPromise) pythonInflight.delete(requestKey);
  }
}

async function proxyPythonGet(res, targetPath) {
  const target = `${pythonBaseUrl}${targetPath}`;
  try {
    const upstream = await fetch(target, { signal: AbortSignal.timeout(15000) });
    const responseBody = await upstream.arrayBuffer();
    res.writeHead(upstream.status, {
      'Content-Type': upstream.headers.get('content-type') || 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(Buffer.from(responseBody));
  } catch (error) {
    send(res, 502, JSON.stringify({
      ok: false,
      error: 'python_unreachable',
      message: `无法连接 Python 知识库服务：${error.message}`,
      target,
    }));
  }
}

async function serveStatic(req, res, pathname) {
  const requested = pathname === '/' ? '/open-design.html' : pathname;
  const filePath = normalize(join(root, requested));
  if (!filePath.startsWith(root + sep) && filePath !== join(root, 'index.html')) {
    send(res, 403, JSON.stringify({ ok: false, error: 'forbidden' }));
    return;
  }

  try {
    const fileStat = await stat(filePath);
    if (!fileStat.isFile()) throw new Error('not a file');
    const type = contentTypes[extname(filePath)] || 'application/octet-stream';
    const range = req.headers.range;

    if (range && type.startsWith('video/')) {
      const match = /^bytes=(\d*)-(\d*)$/.exec(range);
      if (!match) {
        res.writeHead(416, { 'Content-Range': `bytes */${fileStat.size}` });
        res.end();
        return;
      }

      const start = match[1] ? Number(match[1]) : 0;
      const end = match[2] ? Math.min(Number(match[2]), fileStat.size - 1) : fileStat.size - 1;
      if (start > end || start >= fileStat.size) {
        res.writeHead(416, { 'Content-Range': `bytes */${fileStat.size}` });
        res.end();
        return;
      }

      res.writeHead(206, {
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'public, max-age=3600',
        'Content-Length': end - start + 1,
        'Content-Range': `bytes ${start}-${end}/${fileStat.size}`,
        'Content-Type': type,
      });
      createReadStream(filePath, { start, end }).pipe(res);
      return;
    }

    res.writeHead(200, {
      'Accept-Ranges': type.startsWith('video/') ? 'bytes' : 'none',
      'Content-Length': fileStat.size,
      'Content-Type': type,
      'Cache-Control': type.startsWith('video/') ? 'public, max-age=3600' : 'no-store',
    });
    createReadStream(filePath).pipe(res);
  } catch {
    if (!extname(pathname)) {
      const fallback = await readFile(join(root, 'open-design.html'));
      res.writeHead(200, { 'Content-Type': contentTypes['.html'], 'Cache-Control': 'no-store' });
      res.end(fallback);
      return;
    }
    send(res, 404, JSON.stringify({ ok: false, error: 'not_found' }));
  }
}

createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
  if (req.method === 'OPTIONS') {
    res.writeHead(204, { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type' });
    res.end();
    return;
  }
  if (req.method === 'POST' && disabledLegacyContentRoutes.has(url.pathname)) {
    send(res, 410, JSON.stringify({
      ok: false,
      error: 'legacy_content_stage_disabled',
      message: '内容生成已统一走 Python 唯一入口；旧 n8n 内容生成入口已禁用。',
    }));
    return;
  }
  if (req.method === 'POST' && postRoutes[url.pathname]) {
    await proxyPost(req, res, url.pathname);
    return;
  }
  if (req.method === 'POST' && url.pathname === '/api/upload-images') {
    try {
      const payload = JSON.parse((await readRequestBody(req)).toString('utf8') || '[]');
      const images = await persistUploadedImages(payload);
      send(res, 200, JSON.stringify({ ok: true, images }));
    } catch (error) {
      send(res, 400, JSON.stringify({ ok: false, error: 'invalid_image_upload', message: error.message }));
    }
    return;
  }
  if (req.method === 'POST' && url.pathname === '/api/video/callback') {
    try {
      const body = await readRequestBody(req);
      const payload = JSON.parse(body.toString('utf8') || '{}');
      const taskId = safeTaskId(payload.video_task_id || payload.task_id);
      const current = await readVideoTask(taskId);
      const normalizedBody = normalizeVideoResponse(body);
      const normalized = JSON.parse(Buffer.from(normalizedBody).toString('utf8') || '{}');
      const videoUrl = findVideoUrl(normalized);
      const status = videoUrl ? 'completed' : (normalized.status || 'error');
      await writeVideoTask(taskId, { ...normalized, status, ok: status === 'completed' });
      if (videoUrl) {
        await saveLatestVideo(Buffer.from(JSON.stringify(current.request || {})), normalizedBody);
      }
      send(res, 200, JSON.stringify({ ok: true, video_task_id: taskId, status }));
    } catch (error) {
      send(res, 400, JSON.stringify({ ok: false, error: 'invalid_video_callback', message: error.message }));
    }
    return;
  }
  if (req.method === 'POST' && pythonRoutes[url.pathname]) {
    await proxyPython(req, res, url.pathname);
    return;
  }
  if (req.method === 'POST' && url.pathname === '/api/extract-product-document') {
    await extractProductDocument(req, res);
    return;
  }
  if (req.method === 'GET' && url.pathname === '/api/health') {
    try {
      const [n8n, python] = await Promise.allSettled([
        fetch(`${n8nBaseUrl}/healthz`, { signal: AbortSignal.timeout(3000) }),
        fetch(`${pythonBaseUrl}/health`, { signal: AbortSignal.timeout(3000) }),
      ]);
      const n8nOk = n8n.status === 'fulfilled' && n8n.value.ok;
      const pythonOk = python.status === 'fulfilled' && python.value.ok;
      send(res, n8nOk && pythonOk ? 200 : 503, JSON.stringify({
        ok: n8nOk && pythonOk,
        frontend: 'ok',
        n8n: n8nOk ? 'ok' : 'unreachable',
        python: pythonOk ? 'ok' : 'unreachable',
      }));
    } catch (error) {
      send(res, 503, JSON.stringify({
        ok: false,
        frontend: 'ok',
        n8n: 'unreachable',
        message: error.message,
      }));
    }
    return;
  }
  if (req.method === 'GET' && url.pathname === '/api/video/latest') {
    try {
      const latest = await readFile(latestVideoPath, 'utf8');
      send(res, 200, latest);
    } catch {
      send(res, 404, JSON.stringify({ ok: false, error: 'no_video_result' }));
    }
    return;
  }
  if (req.method === 'GET' && url.pathname === '/api/video/status') {
    try {
      const task = await readVideoTask(url.searchParams.get('task_id'));
      send(res, 200, JSON.stringify(task));
    } catch {
      send(res, 404, JSON.stringify({ ok: false, status: 'not_found', error: 'video_task_not_found' }));
    }
    return;
  }
  if (req.method === 'GET' && url.pathname === '/api/knowledge/filters') {
    await proxyPythonGet(res, `/knowledge/filters${url.search}`);
    return;
  }
  if (req.method === 'GET' && url.pathname === '/api/knowledge/status') {
    await proxyPythonGet(res, `/knowledge/status${url.search}`);
    return;
  }
  if (req.method === 'GET') {
    await serveStatic(req, res, url.pathname);
    return;
  }
  send(res, 405, JSON.stringify({ ok: false, error: 'method_not_allowed' }));
}).listen(port, '127.0.0.1', () => {
  console.log(`AI广告视频工厂前端：http://localhost:${port}`);
  console.log(`前端代码目录：${root}`);
  console.log(`Python 服务代理：${pythonBaseUrl}`);
  console.log(`n8n Webhook 代理：${n8nBaseUrl}/${webhookPrefix}`);
});

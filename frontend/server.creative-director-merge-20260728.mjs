import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url)).replace(/[\\/]$/, '');
const port = Number(process.env.PORT || 4173);
const n8nBaseUrl = String(process.env.N8N_BASE_URL || 'http://localhost:5678').replace(/\/+$/, '');
const webhookPrefix = String(process.env.N8N_WEBHOOK_PREFIX || 'webhook').replace(/^\/+|\/+$/g, '');

const workflowRoutes = {
  '/api/workflow/stage-1/url': 'ai-ad-product-url-v2',
  '/api/workflow/stage-1/tvc': 'ai-ad-product-tvc',
  '/api/workflow/stage-2/optimize': 'ai-ad-hook-optimize',
  '/api/workflow/stage-2': 'ai-ad-hook-to-script-v2',
  '/api/workflow/stage-3': 'ai-ad-script-to-video-task-v2',
  '/api/workflow/stage-4': 'ai-ad-video-task-v2',
};

const postRoutes = {
  ...workflowRoutes,
  '/api/assets/image': process.env.N8N_ASSET_UPLOAD_WORKFLOW || 'ai-ad-asset-upload',
};

const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
};

function send(res, status, body, type = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  res.end(body);
}

async function proxyPost(req, res, pathname) {
  const workflowPath = postRoutes[pathname];
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = Buffer.concat(chunks);
  const headers = {};
  if (req.headers['content-type']) headers['content-type'] = req.headers['content-type'];
  const target = `${n8nBaseUrl}/${webhookPrefix}/${workflowPath}`;

  try {
    const upstream = await fetch(target, { method: 'POST', headers, body });
    const responseBody = await upstream.arrayBuffer();
    const responseType = upstream.headers.get('content-type') || 'application/json; charset=utf-8';
    res.writeHead(upstream.status, { 'Content-Type': responseType, 'Cache-Control': 'no-store' });
    res.end(Buffer.from(responseBody));
  } catch (error) {
    send(res, 502, JSON.stringify({
      ok: false,
      error: 'n8n_unreachable',
      message: `无法连接 n8n：${error.message}`,
      target,
    }));
  }
}

async function serveStatic(req, res, pathname) {
  const requested = pathname === '/' ? '/index.html' : pathname;
  const filePath = normalize(join(root, requested));
  if (!filePath.startsWith(root + sep) && filePath !== join(root, 'index.html')) {
    send(res, 403, JSON.stringify({ ok: false, error: 'forbidden' }));
    return;
  }

  try {
    const fileStat = await stat(filePath);
    if (!fileStat.isFile()) throw new Error('not a file');
    const type = contentTypes[extname(filePath)] || 'application/octet-stream';
    const content = await readFile(filePath);
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' });
    res.end(content);
  } catch {
    if (!extname(pathname)) {
      const fallback = await readFile(join(root, 'index.html'));
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
  if (req.method === 'POST' && postRoutes[url.pathname]) {
    await proxyPost(req, res, url.pathname);
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
  console.log(`n8n Webhook 代理：${n8nBaseUrl}/${webhookPrefix}`);
});

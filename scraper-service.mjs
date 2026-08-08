/**
 * 全平台商品爬虫服务 (Node.js Playwright)
 * 基于已验证稳定的旧版 server.mjs 爬虫代码
 * 监听 localhost:9876
 */
import { createServer } from 'node:http';
import { chromium } from 'playwright';

const PORT = 9876;
let _browser = null;

async function getBrowser() {
  if (_browser) return _browser;
  _browser = await chromium.launch({
    headless: true,
    channel: 'chrome',
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
    ],
  });
  console.log('[scraper] Browser started');
  return _browser;
}

async function scrape(targetUrl) {
  const browser = await getBrowser();
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
  });
  const page = await context.newPage();

  // Block fonts/media for speed
  await page.route('**/*', (route) => {
    const t = route.request().resourceType();
    if (t === 'font' || t === 'media') route.abort();
    else route.continue();
  });

  try {
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 25000 });
    await page.waitForTimeout(3000);

    const url = page.url();
    const title = await page.title();

    // Check for anti-bot pages
    if (url.includes('risk_handler') || url.includes('captcha') || url.includes('verify')) {
      return {
        ok: false,
        blocked: true,
        block_reason: `反爬拦截: ${url.slice(0, 120)}`,
        url, title: '', description: '', text: '', image: '',
      };
    }

    // Extract product info
    const result = await page.evaluate(() => ({
      title: document.title || '',
      body: (document.body?.innerText || '').slice(0, 30000),
      metaDesc: document.querySelector('meta[name="description"]')?.getAttribute('content') || '',
      ogImage: document.querySelector('meta[property="og:image"]')?.getAttribute('content') || '',
    }));

    // Also extract images
    const images = await page.evaluate(() => {
      const results = [];
      const seen = new Set();
      const og = document.querySelector('meta[property="og:image"]');
      if (og) { const u = og.getAttribute('content'); if (u) { results.push(u); seen.add(u); } }
      document.querySelectorAll('img').forEach(img => {
        let src = img.src || img.getAttribute('data-src') || '';
        if (src && src.startsWith('http') && /\.(jpg|jpeg|png|webp)\b/i.test(src) && !seen.has(src)) {
          results.push(src);
          seen.add(src);
        }
      });
      return results.slice(0, 9);
    });

    return {
      ok: true,
      url,
      title: result.title,
      description: result.metaDesc,
      text: result.body,
      image: images[0] || result.ogImage || '',
      images,
    };
  } catch (e) {
    return {
      ok: false,
      error: e.message,
      url: targetUrl,
      title: '', description: '', text: '', image: '',
    };
  } finally {
    await context.close();
  }
}

// ---- HTTP Server ----
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200);
    res.end(JSON.stringify({ ok: true, status: 'running' }));
    return;
  }

  if (req.method === 'POST' && req.url === '/scrape') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        const { url } = JSON.parse(body);
        if (!url) {
          res.writeHead(400);
          res.end(JSON.stringify({ ok: false, error: 'missing url' }));
          return;
        }
        console.log(`[scraper] 🔍 ${url.slice(0, 80)}`);
        const result = await scrape(url);
        console.log(`[scraper] ${result.ok ? '✅' : '❌'} ${result.title?.slice(0, 50) || result.error || 'blocked'}`);
        res.writeHead(200);
        res.end(JSON.stringify(result));
      } catch (e) {
        res.writeHead(400);
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    });
    return;
  }

  res.writeHead(404);
  res.end(JSON.stringify({ ok: false, error: 'not found' }));
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[scraper] 全平台爬虫服务已启动: http://127.0.0.1:${PORT}`);
  console.log('[scraper] POST /scrape  {"url": "..."}  → 商品信息');
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  if (_browser) await _browser.close();
  process.exit(0);
});

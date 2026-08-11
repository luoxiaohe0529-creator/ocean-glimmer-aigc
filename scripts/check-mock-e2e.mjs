import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const demoPath = join(process.cwd(), 'docs/demo/index.html');

async function main() {
  const demoHtml = await readFile(demoPath, 'utf8');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const apiRequests = [];

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url());
    if (requestUrl.pathname.startsWith('/api/')) {
      apiRequests.push(route.request().url());
      await route.abort();
      return;
    }
    await route.abort('blockedbyclient');
  });

  try {
    await page.setContent(demoHtml, { waitUntil: 'domcontentloaded' });

    await assertVisible(page, 'text=Brief 到成片的完整可复现流程');
    await assertVisible(page, 'text=华为 nova 轻旗舰手机');

    await page.getByRole('button', { name: '查看 Hook 方案' }).click();
    await assertVisible(page, 'text=12 条 Hook 中选择一条继续制作');
    await page.locator('[data-hook="1"]').click();
    await page.getByRole('button', { name: '确认 Hook，生成脚本' }).click();

    await assertVisible(page, 'text=完整视频脚本');
    assert.equal(await page.locator('#selectedHookLabel').textContent(), '把夏天拍得更清透');
    await assertVisible(page, 'text=0-3s：镜头贴近手机背板和人物眼神');
    await page.getByRole('button', { name: '拆成分镜' }).click();

    await assertVisible(page, 'text=导演分镜与视频提示词');
    assert.equal(await page.locator('.shot').count(), 4, 'Mock storyboard should contain 4 shots');
    await page.getByRole('button', { name: '生成并回写成片' }).click();

    await assertVisible(page, 'text=成片回写');
    const video = page.locator('video[controls]');
    assert.equal(await video.count(), 1, 'Mock result should expose one playable video element');
    const source = await page.locator('video source').getAttribute('src');
    assert.match(source || '', /^https:\/\/github\.com\/user-attachments\/assets\//);
    assert.deepEqual(apiRequests, [], 'Read-only mock demo must not call API routes');
  } finally {
    await browser.close();
  }

  console.log('Mock E2E passed: Brief -> Hook -> Script -> Storyboard -> Video without API calls.');
}

async function assertVisible(page, selector) {
  const locator = page.locator(selector).first();
  await locator.waitFor({ state: 'visible', timeout: 5000 });
  assert.equal(await locator.isVisible(), true, `${selector} should be visible`);
}

await main();

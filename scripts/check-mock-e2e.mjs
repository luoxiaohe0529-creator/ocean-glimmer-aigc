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

    assert.equal(
      await page.evaluate(() => window.__OCEAN_GLIMMER_STATIC_DEMO__ === true),
      true,
      'Public demo should install the static mock guard',
    );

    await assertVisible(page, 'text=大海浮光 AIGC 工作台');
    await assertVisible(page, 'text=只读 Mock · 不调用 API');
    await assertVisible(page, 'text=广告策划');
    await assertVisible(page, 'text=渐变色时尚手机创意案例');
    await assertVisible(page, 'text=12 条 Hook');

    await page.locator('.step[data-stage="1"]').click();
    await assertVisible(page, 'text=完整脚本与导演分镜');
    await assertVisible(page, 'text=粉蓝渐变手机在夏日蓝色水光中掠过');
    assert.equal(await page.locator('.storyboard-shot').count(), 4, 'Director output should contain 4 storyboard shots');

    await page.locator('.step[data-stage="3"]').click();
    await assertVisible(page, 'text=视频生成台');
    const productionVideo = page.locator('.video-output-card video[controls]');
    assert.equal(await productionVideo.count(), 1, 'Cinematography stage should expose one playable video element');
    assert.match(await productionVideo.first().getAttribute('src') || '', /^https:\/\/github\.com\/user-attachments\/assets\//);

    await page.locator('.step[data-stage="4"]').click();
    await assertVisible(page, 'text=自动化后期工作台');
    const postVideo = page.locator('.editing-screen video[controls]');
    assert.equal(await postVideo.count(), 1, 'Post-production stage should expose one preview video element');
    assert.match(await postVideo.first().getAttribute('src') || '', /^https:\/\/github\.com\/user-attachments\/assets\//);

    assert.deepEqual(apiRequests, [], 'Read-only mock demo must not call API routes');
  } finally {
    await browser.close();
  }

  console.log('Mock E2E passed: four-agent workbench renders planning, directing, cinematography and post-production without API calls.');
}

async function assertVisible(page, selector) {
  const locator = page.locator(selector).first();
  await locator.waitFor({ state: 'visible', timeout: 5000 });
  assert.equal(await locator.isVisible(), true, `${selector} should be visible`);
}

await main();

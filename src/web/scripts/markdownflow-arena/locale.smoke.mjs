import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { chromium } from '@playwright/test';
import { normalizeArtifact } from './contract.mjs';

const directory = path.dirname(fileURLToPath(import.meta.url));
const bundle = await build({
  entryPoints: [path.join(directory, 'client.jsx')],
  bundle: true,
  outdir: '/virtual-arena-locale-smoke',
  write: false,
  format: 'iife',
  define: { 'process.env.NODE_ENV': '"production"' },
  loader: { '.woff2': 'dataurl', '.woff': 'dataurl', '.ttf': 'dataurl' },
  logLevel: 'silent',
  minify: true,
  alias: {
    react: path.join(directory, '../../node_modules/react'),
    'react-dom': path.join(directory, '../../node_modules/react-dom'),
  },
});
const files = new Map(
  bundle.outputFiles.map(file => [path.basename(file.path), file.contents]),
);
const server = createServer((request, response) => {
  const filename = request.url.slice(1);
  if (request.method !== 'GET' || (filename && !files.has(filename))) {
    response.writeHead(404).end();
    return;
  }
  response.setHeader(
    'Content-Type',
    !filename
      ? 'text/html'
      : filename.endsWith('.css')
        ? 'text/css'
        : 'text/javascript',
  );
  response.end(
    filename
      ? files.get(filename)
      : '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/client.css"></head><body><div id="root"></div><script src="/client.js"></script></body></html>',
  );
});
let browser;
try {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({
    headless: true,
    chromiumSandbox: true,
    ...(process.env.ARENA_BROWSER_PATH
      ? { executablePath: process.env.ARENA_BROWSER_PATH }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 720 },
    timezoneId: 'UTC',
    serviceWorkers: 'block',
  });
  await page.route('**/*', route =>
    new URL(route.request().url()).origin === origin
      ? route.continue()
      : route.abort(),
  );
  await page.goto(origin);
  await page.waitForFunction(() => typeof window.renderArena === 'function');
  const locales = ['ar-SA', 'en-US', 'fr-FR', 'th-TH', 'zh-CN'];
  for (const mode of ['reading', 'slides']) {
    for (const locale of locales) {
      const direction = locale === 'ar-SA' ? 'rtl' : 'ltr';
      const content = `<article id="locale-fixture" style="padding:32px"><h1>${locale}</h1><p>Locale fixture</p></article>`;
      const artifact = normalizeArtifact({
        content,
        metadata: { locale },
        ...(mode === 'slides'
          ? {
              elements: [
                {
                  content,
                  element_type: 'html',
                  is_marker: true,
                  is_new: true,
                  is_renderable: true,
                },
              ],
            }
          : {}),
      });
      await page.evaluate(value => window.renderArena(value), artifact);
      await page.waitForFunction(
        ({ locale, direction }) => {
          const root = document.getElementById('capture');
          return root?.lang === locale && root?.dir === direction;
        },
        { locale, direction },
      );
      assert.deepEqual(
        await page.evaluate(() => ({
          locale: document.documentElement.lang,
          direction: document.documentElement.dir,
          computedDirection: getComputedStyle(
            document.getElementById('capture'),
          ).direction,
        })),
        { locale, direction, computedDirection: direction },
      );
      await page
        .locator(`#capture [lang="${locale}"][dir="${direction}"]`)
        .first()
        .waitFor({ state: 'visible' });
      const frame = page.frameLocator('#capture iframe').first();
      await frame.locator('#locale-fixture h1').getByText(locale).waitFor();
      assert.deepEqual(
        await frame.locator('#locale-fixture').evaluate(element => ({
          locale: element.closest('[lang]')?.lang,
          direction: element.closest('[dir]')?.dir,
          computedDirection: getComputedStyle(element).direction,
        })),
        { locale, direction, computedDirection: direction },
      );
    }
  }
  process.stdout.write(
    JSON.stringify({ status: 'complete', locales, component_cases: 10 }) + '\n',
  );
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}

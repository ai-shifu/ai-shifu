import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = path.dirname(fileURLToPath(import.meta.url));
const browserArgs = process.env.ARENA_BROWSER_PATH
  ? ['--browser-path', process.env.ARENA_BROWSER_PATH]
  : [];
const output = await mkdtemp(path.join(tmpdir(), 'arena-render-smoke-'));
const svg =
  '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="160"><rect width="400" height="160" fill="#eef2ff"/><circle cx="80" cy="80" r="48" fill="#4f46e5"/></svg>';
const fixtures = {
  reading:
    '# 学习是一段旅程\n\n' +
    Array.from(
      { length: 55 },
      (_, index) =>
        `## 第 ${index + 1} 步\n\n认真观察，再用自己的语言解释刚刚学到的知识。\n\n`,
    ).join(''),
  diagram:
    '# 从想法到验证\n\n```mermaid\nflowchart LR\nA[观察] --> B[提问] --> C[验证]\n```\n\n$$ E = mc^2 $$\n\n' +
    svg,
  html: '<section style="background:#eff6ff;padding:64px;color:#172554"><h1>把学习变成可见的成果</h1><p>先思考，再实践。</p><div id="dynamic"></div><script>document.getElementById("dynamic").textContent="脚本渲染已完成";</script></section>',
};
const artifacts = Object.fromEntries(
  Object.entries(fixtures).map(([key, content]) => [key, { content }]),
);
artifacts.slides = {
  content: '# Page one\n\n# Page two',
  elements: [
    {
      type: 'text',
      content: '# 第一页\n\n理解问题',
      is_marker: true,
      is_new: true,
      is_renderable: true,
    },
    {
      type: 'html',
      content:
        '<div style="width:1280px;height:720px;padding:80px;background:#172554;color:white"><h1>第二页</h1><p>验证假设</p></div>',
      is_marker: true,
      is_new: true,
      is_renderable: true,
    },
  ],
};
artifacts['scrolling-slides'] = {
  content: 'Scrollable slide followed by another slide',
  elements: [
    {
      type: 'html',
      content:
        '<div style="width:100%;min-height:100vh;overflow-y:auto"><div style="height:720px;background:#ff0000">Scrollable slide starts here</div><div style="height:373px;background:#0000ff">Scrollable slide ends here</div></div>',
      is_marker: true,
      is_new: true,
      is_renderable: true,
    },
    {
      type: 'html',
      content:
        '<div style="height:720px;background:#00ff00">Next slide remains a separate page</div>',
      is_marker: true,
      is_new: true,
      is_renderable: true,
    },
  ],
};
artifacts['emoji-linebox'] = {
  content:
    '<figure style="margin:0;height:128px;width:276px;padding:16px;overflow:hidden;display:flex;align-items:center;justify-content:center"><span style="font-size:86.4px;line-height:129.6px">🐕</span></figure>',
};
artifacts['scrolling-text-slides'] = {
  ...artifacts['scrolling-slides'],
  elements: artifacts['scrolling-slides'].elements.map(element => ({
    ...element,
    type: 'text',
  })),
};
for (const [name, artifact] of Object.entries(artifacts)) {
  const input = path.join(output, `${name}.json`);
  await writeFile(input, JSON.stringify(artifact));
  const child = spawnSync(
    process.execPath,
    [
      path.join(directory, 'render.mjs'),
      '--input',
      input,
      '--output',
      path.join(output, name),
      ...browserArgs,
    ],
    { encoding: 'utf8', timeout: 120000 },
  );
  assert.equal(child.status, 0, `${name}: ${child.stdout} ${child.stderr}`);
  const result = JSON.parse(child.stdout.trim());
  assert.equal(result.status, 'complete');
  assert.ok(
    result.pages.length >= (name === 'reading' ? 3 : name === 'slides' ? 2 : 1),
  );
  assert.equal((await readFile(result.pdf)).subarray(0, 5).toString(), '%PDF-');
  if (name.startsWith('scrolling-')) {
    assert.equal(result.pages.length, 3);
    const { default: sharp } = await import('sharp');
    const pixel = async (page, x, y) => [
      ...(await sharp(page)
        .extract({ left: x, top: y, width: 1, height: 1 })
        .removeAlpha()
        .raw()
        .toBuffer()),
    ];
    assert.deepEqual(await pixel(result.pages[0], 1000, 700), [255, 0, 0]);
    assert.deepEqual(await pixel(result.pages[1], 1000, 10), [0, 0, 255]);
    assert.deepEqual(await pixel(result.pages[1], 1000, 360), [0, 0, 255]);
    assert.deepEqual(await pixel(result.pages[1], 1000, 400), [255, 255, 255]);
    assert.deepEqual(await pixel(result.pages[2], 1000, 700), [0, 255, 0]);
  }
}
const blockedInput = path.join(output, 'blocked.json');
await writeFile(
  blockedInput,
  JSON.stringify({ content: '![Blocked](http://127.0.0.1:9876/private.png)' }),
);
const blocked = spawnSync(
  process.execPath,
  [
    path.join(directory, 'render.mjs'),
    '--input',
    blockedInput,
    '--output',
    path.join(output, 'blocked'),
    ...browserArgs,
  ],
  { encoding: 'utf8', timeout: 60000 },
);
assert.equal(blocked.status, 1);
assert.equal(
  JSON.parse(blocked.stdout.trim()).error_code,
  'blocked_external_resource',
);
for (const [name, content] of Object.entries({
  'inner-scroll':
    '<div style="height:180px;overflow:auto"><div style="height:1000px">Start<p style="margin-top:800px">Hidden tail</p></div></div>',
  'iframe-limit':
    '<section style="height:30000px">Start<p style="position:absolute;top:29500px">Hidden tail</p></section>',
  'emoji-clipped':
    '<figure style="margin:0;height:40px;width:276px;overflow:hidden;display:flex;align-items:center;justify-content:center"><span style="font-size:86.4px;line-height:129.6px">🐕</span></figure>',
})) {
  const input = path.join(output, `${name}.json`);
  await writeFile(input, JSON.stringify({ content }));
  const child = spawnSync(
    process.execPath,
    [
      path.join(directory, 'render.mjs'),
      '--input',
      input,
      '--output',
      path.join(output, name),
      ...browserArgs,
    ],
    { encoding: 'utf8', timeout: 60000 },
  );
  assert.equal(child.status, 1, `${name}: ${child.stdout}`);
  assert.equal(JSON.parse(child.stdout.trim()).error_code, 'content_clipped');
}
process.stdout.write(`${JSON.stringify({ status: 'complete', output })}\n`);

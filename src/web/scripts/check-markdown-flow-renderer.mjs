#!/usr/bin/env node

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const manifestPath = fileURLToPath(new URL('../package.json', import.meta.url));
const appRoot = path.dirname(manifestPath);
const require = createRequire(manifestPath);
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const lock = JSON.parse(
  readFileSync(path.join(appRoot, 'package-lock.json'), 'utf8'),
);
const rendererPath = require.resolve('markdown-flow-ui/renderer');
const installed = JSON.parse(
  readFileSync(
    path.join(path.dirname(rendererPath), '../package.json'),
    'utf8',
  ),
);
assert.equal(installed.version, manifest.dependencies['markdown-flow-ui']);
assert.equal(
  installed.version,
  lock.packages[''].dependencies['markdown-flow-ui'],
);
assert.equal(
  installed.version,
  lock.packages['node_modules/markdown-flow-ui'].version,
);

// Use the existing test environment's declared JSDOM dependency, without mocks
// or source aliases for the renderer and its React peer dependency.
const environmentRequire = createRequire(
  require.resolve('jest-environment-jsdom/package.json'),
);
const { JSDOM } = environmentRequire('jsdom');
const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
});
for (const key of [
  'window',
  'document',
  'navigator',
  'HTMLElement',
  'Element',
  'Node',
  'HTMLIFrameElement',
  'HTMLAnchorElement',
  'HTMLImageElement',
  'MutationObserver',
  'DOMParser',
  'getComputedStyle',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.requestAnimationFrame = dom.window.requestAnimationFrame.bind(
  dom.window,
);
globalThis.cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(
  dom.window,
);
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
window.matchMedia = () => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {},
});
class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = window.ResizeObserver = ResizeObserver;

const React = require('react');
const { createRoot } = require('react-dom/client');
const { ContentRender } = require('markdown-flow-ui/renderer');
const roots = [];
const fixture = () => {
  const host = document.createElement('div');
  document.body.append(host);
  const root = createRoot(host);
  roots.push(root);
  return {
    host,
    async render(content) {
      await React.act(async () => {
        root.render(
          React.createElement(ContentRender, {
            content,
            enableTypewriter: true,
            typewriterPacing: 'content-aware',
            // Assertions run before any prose timer can advance.
            typingSpeed: 60000,
            disableSandboxLoadingOverlay: true,
          }),
        );
      });
      // Drain the initial iframe load and committed effects, without advancing
      // the deliberately long prose timer or waiting for streamed content.
      await React.act(async () => new Promise(setImmediate));
    },
  };
};
const assertProseWaiting = host =>
  assert.equal(
    host.querySelector('.content-render')?.textContent?.trim(),
    '',
    'prose remains paced',
  );

try {
  const card = fixture();
  await card.render('Pending prose\n<div class="card">Received');
  const iframe = card.host.querySelector('iframe');
  assert.ok(iframe, 'HTML is present before prose types');
  assert.equal(
    iframe.contentDocument.querySelector('.card')?.textContent,
    'Received',
    'unfinished HTML reaches the real iframe',
  );
  assertProseWaiting(card.host);
  await card.render(
    'Pending prose\n<div class="card">Received and appended</div>\nAfter',
  );
  assert.equal(
    card.host.querySelector('iframe'),
    iframe,
    'HTML iframe identity remains stable',
  );
  assert.equal(
    iframe.contentDocument.querySelector('.card')?.textContent,
    'Received and appended',
    'HTML updates without a typewriter tick',
  );
  assertProseWaiting(card.host);

  // figure and aside are block roots recognized by the backend HTML detector.
  const figure = fixture();
  await figure.render('Pending prose\n<figure class="figure">Received');
  const figureFrame = figure.host.querySelector('iframe');
  assert.ok(figureFrame, 'backend figure root is immediate');
  assert.equal(
    figureFrame.contentDocument.querySelector('.figure')?.textContent,
    'Received',
  );
  await figure.render(
    'Pending prose\n<figure class="figure">Received and appended</figure>\nAfter',
  );
  assert.equal(figure.host.querySelector('iframe'), figureFrame);
  assert.equal(
    figureFrame.contentDocument.querySelector('.figure')?.textContent,
    'Received and appended',
  );
  assertProseWaiting(figure.host);

  const aside = fixture();
  await aside.render('Pending prose\n<aside class="aside">Received');
  const nativeAside = aside.host.querySelector('.aside');
  assert.ok(nativeAside, 'native backend aside root is immediate');
  assert.equal(nativeAside.textContent, 'Received');
  await aside.render(
    'Pending prose\n<aside class="aside">Received and appended</aside>\nAfter',
  );
  assert.equal(aside.host.querySelector('.aside'), nativeAside);
  assert.equal(nativeAside.textContent, 'Received and appended');
  assert.equal(
    aside.host.querySelector('.markdown-renderer p')?.textContent ?? '',
    '',
    'native HTML does not flush preceding prose',
  );

  const literal = fixture();
  await literal.render(
    'Pending prose\n\n~~~html\n<figure>Literal example</figure>\n~~~',
  );
  assert.equal(
    literal.host.querySelector('iframe, figure'),
    null,
    'fenced HTML examples remain inert',
  );
  assertProseWaiting(literal.host);

  const video = fixture();
  const videoSource = '<iframe title="Lesson video" data-tag="video"></iframe>';
  const received = `${videoSource}\n\nPending prose\n\n- Later bullet\n\n~~~js\nlet value=1;\n~~~`;
  await video.render(received);
  const nativeVideo = video.host.querySelector('iframe[data-tag="video"]');
  assert.ok(nativeVideo, 'native video is present before prose types');
  const videoWindow = nativeVideo.contentWindow;
  const videoParent = nativeVideo.parentNode;
  videoWindow.rendererSentinel = 'playing';
  let loads = 0;
  nativeVideo.addEventListener('load', () => loads++);
  await video.render(
    `${received}\n\nAppended prose.\n\n<div id="following">Received card</div>`,
  );
  assert.equal(
    video.host.querySelector('iframe[data-tag="video"]'),
    nativeVideo,
  );
  assert.equal(nativeVideo.parentNode, videoParent);
  assert.equal(nativeVideo.contentWindow, videoWindow);
  assert.equal(videoWindow.rendererSentinel, 'playing');
  assert.equal(loads, 0, 'native video has no extra load');
  assert.equal(
    video.host
      .querySelector('iframe.content-render-iframe')
      ?.contentDocument.querySelector('#following')?.textContent,
    'Received card',
  );
  assert.equal(
    video.host.querySelector('ul'),
    null,
    'untyped list bullets stay hidden',
  );
  assert.equal(
    video.host.querySelector('.copy-button'),
    null,
    'untyped code toolbar stays hidden',
  );
  assertProseWaiting(video.host);

  console.log(
    `Installed MarkdownFlow renderer passed: ${installed.version}, React ${React.version}, progressive HTML, backend roots, code boundaries and stable video.`,
  );
} finally {
  await React.act(async () => {
    for (const root of roots) root.unmount();
    // IframeSandbox defers its nested React root cleanup to the next timer turn.
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  dom.window.close();
}

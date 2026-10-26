/** @jest-environment-options {"runScripts":"outside-only"} */

import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { deserialize, serialize } from 'node:v8';
import { ContentRender } from 'markdown-flow-ui/renderer';

// Inspect real sandbox DOM without executing its unrelated vendor scripts.
const rendererProps = {
  enableTypewriter: true,
  typewriterPacing: 'content-aware' as const,
  typingSpeed: 50,
  disableSandboxLoadingOverlay: true,
};

const expectProseWaiting = (container: HTMLElement) => {
  expect(container.querySelector('.content-render')?.textContent?.trim()).toBe(
    '',
  );
};

const advanceTyping = async (ticks: number) => {
  for (let tick = 0; tick < ticks; tick += 1) {
    // Commit each prose update before scheduling the next animation tick.
    await act(async () => {
      await jest.advanceTimersByTimeAsync(rendererProps.typingSpeed);
    });
  }
};

describe('installed MarkdownFlow renderer', () => {
  const originalStructuredClone = globalThis.structuredClone;

  beforeAll(() => {
    // Jest 29's JSDOM omits this browser API used to copy the Markdown AST.
    globalThis.structuredClone ??= value => deserialize(serialize(value));
  });

  afterAll(() => {
    globalThis.structuredClone = originalStructuredClone;
  });

  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(async () => {
    await act(async () => {
      cleanup();
      // IframeSandbox defers its nested React root cleanup to the next timer turn.
      await jest.advanceTimersByTimeAsync(0);
    });
    jest.useRealTimers();
  });

  it('uses the exact renderer version recorded in the manifest and lockfile', () => {
    const appRoot = path.resolve(__dirname, '../..');
    const manifest = JSON.parse(
      readFileSync(path.join(appRoot, 'package.json'), 'utf8'),
    );
    const lock = JSON.parse(
      readFileSync(path.join(appRoot, 'package-lock.json'), 'utf8'),
    );
    const installed = JSON.parse(
      readFileSync(
        path.join(
          path.dirname(require.resolve('markdown-flow-ui/renderer')),
          '../package.json',
        ),
        'utf8',
      ),
    );

    expect(installed.version).toBe(manifest.dependencies['markdown-flow-ui']);
    expect(installed.version).toBe(
      lock.packages[''].dependencies['markdown-flow-ui'],
    );
    expect(installed.version).toBe(
      lock.packages['node_modules/markdown-flow-ui'].version,
    );
  });

  it.each([
    ['div', 'fixed'],
    ['div', 'content-aware'],
    ['figure', 'fixed'],
    ['figure', 'content-aware'],
  ] as const)(
    'reveals unfinished %s HTML after preceding prose with %s pacing',
    async (tag, typewriterPacing) => {
      const view = render(
        <ContentRender
          {...rendererProps}
          typewriterPacing={typewriterPacing}
          content={`甲乙丙丁\n<${tag} class="received-html">Received`}
        />,
      );

      expect(view.container.querySelector('iframe')).toBeNull();
      expectProseWaiting(view.container);

      await act(async () => {
        await jest.advanceTimersByTimeAsync(50);
      });
      const partialProse =
        view.container.querySelector('.content-render')?.textContent;
      expect(partialProse?.trim()).not.toBe('');
      expect(partialProse?.trim()).not.toBe('甲乙丙丁');
      expect(view.container.querySelector('iframe')).toBeNull();

      view.rerender(
        <ContentRender
          {...rendererProps}
          typewriterPacing={typewriterPacing}
          content={`甲乙丙丁\n<${tag} class="received-html">Received and appended`}
        />,
      );
      expect(view.container.querySelector('iframe')).toBeNull();
      expect(view.container.querySelector('.content-render')?.textContent).toBe(
        partialProse,
      );

      await advanceTyping(5);
      const iframe = view.container.querySelector('iframe');
      expect(iframe).not.toBeNull();
      expect(
        view.container.querySelector('.content-render')?.textContent?.trim(),
      ).toBe('甲乙丙丁');
      expect(
        iframe?.contentDocument?.querySelector('.received-html')?.textContent,
      ).toBe('Received and appended');

      view.rerender(
        <ContentRender
          {...rendererProps}
          typewriterPacing={typewriterPacing}
          content={`甲乙丙丁\n<${tag} class="received-html">Received and appended immediately</${tag}>\nAfter`}
        />,
      );

      expect(view.container.querySelector('iframe')).toBe(iframe);
      expect(
        iframe?.contentDocument?.querySelector('.received-html')?.textContent,
      ).toBe('Received and appended immediately');
      expect(
        view.container.querySelector('.content-render')?.textContent?.trim(),
      ).toBe('甲乙丙丁');
    },
  );

  it('reveals native HTML after preceding prose and updates it without typing', async () => {
    const view = render(
      <ContentRender
        {...rendererProps}
        content={'甲乙丙丁\n<aside class="received-html">Received'}
      />,
    );
    expect(view.container.querySelector('.received-html')).toBeNull();
    expectProseWaiting(view.container);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(50);
    });
    expect(view.container.querySelector('.received-html')).toBeNull();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(50);
    });
    const aside = view.container.querySelector('.received-html');

    expect(aside).not.toBeNull();
    expect(aside).toHaveTextContent('Received');

    view.rerender(
      <ContentRender
        {...rendererProps}
        content={
          '甲乙丙丁\n<aside class="received-html">Received and appended</aside>\nAfter'
        }
      />,
    );

    expect(view.container.querySelector('.received-html')).toBe(aside);
    expect(aside).toHaveTextContent('Received and appended');
    expect(
      view.container.querySelector('.markdown-renderer p')?.textContent ?? '',
    ).toBe('甲乙丙丁');
  });

  it('renders HTML-only snapshots immediately without waiting for closure', () => {
    const view = render(
      <ContentRender
        {...rendererProps}
        content={'<div class="received-html">Received'}
      />,
    );
    const iframe = view.container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(
      iframe?.contentDocument?.querySelector('.received-html')?.textContent,
    ).toBe('Received');

    view.rerender(
      <ContentRender
        {...rendererProps}
        content={'<div class="received-html">Received and appended'}
      />,
    );
    expect(view.container.querySelector('iframe')).toBe(iframe);
    expect(
      iframe?.contentDocument?.querySelector('.received-html')?.textContent,
    ).toBe('Received and appended');
  });

  it('waits for preceding prose before mounting a native video', async () => {
    const view = render(
      <ContentRender
        {...rendererProps}
        content={
          '甲乙丙丁\n<iframe title="Lesson video" data-tag="video"></iframe>'
        }
      />,
    );
    expect(view.container.querySelector('iframe')).toBeNull();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(50);
    });
    expect(view.container.querySelector('iframe')).toBeNull();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(50);
    });
    expect(
      view.container.querySelector('iframe[data-tag="video"]'),
    ).not.toBeNull();
    expect(
      view.container.querySelector('.content-render')?.textContent?.trim(),
    ).toBe('甲乙丙丁');
  });

  it('keeps HTML inside a fenced code example out of the immediate HTML path', () => {
    const view = render(
      <ContentRender
        {...rendererProps}
        content={
          'Pending prose\n\n~~~html\n<figure>Literal example</figure>\n~~~'
        }
      />,
    );

    expect(view.container.querySelector('iframe, figure')).toBeNull();
    expectProseWaiting(view.container);
  });

  it('preserves video state through appends and prose typing without exposing future structures', async () => {
    const received =
      '<iframe title="Lesson video" data-tag="video"></iframe>\n\nPending prose\n\n- Later bullet\n\n~~~js\nlet value=1;\n~~~';
    const view = render(
      <ContentRender
        {...rendererProps}
        content={received}
      />,
    );
    // Drain the initial iframe load without advancing the prose clock.
    await act(async () => {
      await jest.advanceTimersByTimeAsync(0);
    });
    const iframe = view.container.querySelector<HTMLIFrameElement>(
      'iframe[data-tag="video"]',
    );
    expect(iframe).not.toBeNull();
    const videoWindow = iframe!.contentWindow!;
    const videoParent = iframe!.parentNode;
    const sentinel = document.createElement('span');
    sentinel.textContent = 'playing';
    videoWindow.document.body.append(sentinel);
    const onLoad = jest.fn();
    iframe!.addEventListener('load', onLoad);

    view.rerender(
      <ContentRender
        {...rendererProps}
        content={`${received}\n\nAppended prose.\n\n<div id="following">Received card</div>`}
      />,
    );

    expect(
      view.container.querySelector('iframe.content-render-iframe'),
    ).toBeNull();
    expect(view.container.querySelector('ul')).toBeNull();
    expect(view.container.querySelector('.copy-button')).toBeNull();
    expectProseWaiting(view.container);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(50);
    });

    expect(
      view.container.querySelector('.content-render')?.textContent?.trim(),
    ).not.toBe('');
    expect(view.container.querySelector('iframe[data-tag="video"]')).toBe(
      iframe,
    );
    expect(iframe!.parentNode).toBe(videoParent);
    expect(iframe!.contentWindow).toBe(videoWindow);
    expect(videoWindow.document.body.contains(sentinel)).toBe(true);
    expect(onLoad).not.toHaveBeenCalled();
    expect(view.container.querySelector('ul')).toBeNull();
    expect(view.container.querySelector('.copy-button')).toBeNull();

    await advanceTyping(100);

    expect(
      view.container
        .querySelector<HTMLIFrameElement>('iframe.content-render-iframe')
        ?.contentDocument?.querySelector('#following')?.textContent,
    ).toBe('Received card');
    expect(view.container.querySelector('iframe[data-tag="video"]')).toBe(
      iframe,
    );
    expect(iframe!.parentNode).toBe(videoParent);
    expect(iframe!.contentWindow).toBe(videoWindow);
    expect(videoWindow.document.body.contains(sentinel)).toBe(true);
    expect(onLoad).not.toHaveBeenCalled();
  });
});

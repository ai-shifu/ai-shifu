import { execFileSync } from 'node:child_process';
import path from 'node:path';

describe('installed MarkdownFlow editor integration', () => {
  it.each(['esm', 'cjs'])(
    'loads the %s editor with course authoring props and editable variable syntax',
    format => {
      const appRoot = path.resolve(__dirname, '../..');
      // A native process exercises package exports without Jest's editor or i18n mocks.
      const output = execFileSync(
        process.execPath,
        [
          '-e',
          String.raw`
          const assert = require('node:assert/strict');
          const { createRequire } = require('node:module');
          const React = require('react');
          const { JSDOM } = createRequire(require.resolve('jest-environment-jsdom'))('jsdom');
          const dom = new JSDOM('<!doctype html><html><body></body></html>', {
            pretendToBeVisual: true,
          });
          for (const key of [
            'document', 'window', 'navigator', 'Node', 'Element', 'HTMLElement',
            'MutationObserver', 'getComputedStyle',
          ]) {
            Object.defineProperty(globalThis, key, {
              configurable: true,
              writable: true,
              value: key === 'window' ? dom.window : dom.window[key],
            });
          }
          globalThis.requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
          globalThis.cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(dom.window);
          // JSDOM omits Range geometry used when CodeMirror measures edited selections.
          const emptyRect = dom.window.document.createElement('span').getBoundingClientRect();
          dom.window.Range.prototype.getClientRects ??= () => [];
          dom.window.Range.prototype.getBoundingClientRect ??= () => emptyRect;

          (async () => {
            const { act, cleanup, render, waitFor } = require('@testing-library/react');
            try {
              const { MarkdownFlowEditor } = process.argv[1] === 'esm'
                ? await import('markdown-flow-ui/editor')
                : require('markdown-flow-ui/editor');
              const updates = [];
              let editorApi;
              const props = {
                content: '# Course\n\nHello {{ learner }}\n\n?[%{{ choice }}A|B]',
                editMode: 'quickEdit',
                locale: 'en-US',
                lang: '',
                disabled: false,
                uploadProps: { action: '/api/shifu/upfile' },
                onChange: value => updates.push(value),
                onReady: api => { editorApi = api; },
              };
              const { container, getByRole, rerender } = render(
                React.createElement(MarkdownFlowEditor, props),
              );
              const editorText = () => container.querySelector('.cm-content')?.textContent;
              assert.ok(container.querySelector('.cm-editor'));
              assert.ok(editorText()?.includes('{{ learner }}'));
              assert.ok(editorText()?.includes('?[%{{ choice }}A|B]'));
              assert.equal(getByRole('button', { name: 'Insert image' }).disabled, false);
              assert.equal(getByRole('button', { name: 'Insert video' }).disabled, false);

              rerender(React.createElement(MarkdownFlowEditor, {
                ...props,
                content: 'Updated {{ learner }}\n\n?[%{{ choice }}Yes|No]',
              }));
              assert.ok(editorText()?.includes('Updated {{ learner }}'));
              assert.ok(editorText()?.includes('?[%{{ choice }}Yes|No]'));
              await waitFor(() => assert.equal(
                editorApi?.getContent(),
                'Updated {{ learner }}\n\n?[%{{ choice }}Yes|No]',
              ));
              updates.length = 0;
              await act(async () => {
                editorApi.insertTextAtCursor(' {{ edited }}');
              });
              await waitFor(() => {
                assert.ok(updates.length > 0);
                assert.equal(updates.at(-1), editorApi.getContent());
                assert.ok(updates.at(-1).includes('{{ edited }}'));
              });
              assert.ok(editorText()?.includes('{{ edited }}'));
              console.log('Installed editor preserves course authoring integration');
            } finally {
              cleanup();
              dom.window.close();
            }
          })().catch(error => { console.error(error); process.exitCode = 1; });
        `,
          format,
        ],
        { cwd: appRoot, encoding: 'utf8', timeout: 20_000 },
      );
      expect(output).toContain(
        'Installed editor preserves course authoring integration',
      );
    },
    25_000,
  );
});

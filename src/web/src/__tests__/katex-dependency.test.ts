import { execFileSync } from 'node:child_process';
import path from 'node:path';

describe('installed math renderer security', () => {
  it('rejects inherited trust while preserving supported math in every dependency path', () => {
    const appRoot = path.resolve(__dirname, '../..');
    // Native imports exercise both published formats without Jest ESM transforms.
    // Keep prototype-pollution probes out of the Jest worker's own global object.
    const output = execFileSync(
      process.execPath,
      [
        '-e',
        String.raw`
      const assert = require('node:assert/strict');
      const { createRequire } = require('node:module');
      const path = require('node:path');
      const { pathToFileURL } = require('node:url');

      const verify = (katex, label) => {
        assert.equal(katex.version, '0.18.2', label);
        const expression = '\\href{javascript:alert(1)}{Click}';
        const graphics = '\\includegraphics{https://attacker.invalid/pixel}';
        const options = { throwOnError: false, strict: 'ignore' };
        const assertUntrusted = settings => {
          assert.doesNotMatch(
            katex.renderToString(expression, settings),
            /<a\b[^>]*\bhref=["']javascript:/i,
            label,
          );
          assert.doesNotMatch(katex.renderToString(graphics, settings), /<img\b/i, label);
        };

        assertUntrusted(options);
        assertUntrusted(Object.assign(Object.create({ trust: true }), options));
        const previousTrust = Object.getOwnPropertyDescriptor(Object.prototype, 'trust');
        try {
          Object.defineProperty(Object.prototype, 'trust', {
            configurable: true,
            writable: true,
            value: true,
          });
          assertUntrusted(options);
        } finally {
          if (previousTrust) Object.defineProperty(Object.prototype, 'trust', previousTrust);
          else delete Object.prototype.trust;
        }

        const math = katex.renderToString('c=\\pm\\sqrt{a^2+b^2}', {
          displayMode: true,
          throwOnError: true,
        });
        assert.match(math, /class="katex-display"/, label);
        assert.match(math, /<math\b/, label);
        assert.match(math, /class="katex-html"/, label);
        assert.match(
          katex.renderToString('\\href{https://example.com/}{Safe}', {
            trust: true,
            throwOnError: true,
          }),
          /href="https:\/\/example.com\/"/,
          label,
        );
      };

      (async () => {
        for (const parent of [
          'markdown-flow-ui/renderer',
          'mermaid',
          'rehype-katex',
          'micromark-extension-math',
        ]) {
          const from = createRequire(require.resolve(parent));
          verify(from('katex'), parent + ' (CommonJS)');
          const packageRoot = path.dirname(from.resolve('katex/package.json'));
          const esm = await import(pathToFileURL(path.join(packageRoot, 'dist/katex.mjs')).href);
          verify(esm.default, parent + ' (ESM)');
        }

        // MarkdownFlow also ships bundled math engines used by its renderer and Mermaid.
        const dist = path.dirname(require.resolve('markdown-flow-ui/renderer'));
        const bundledRoot = path.join(dist, 'node_modules/katex/dist');
        verify(require(path.join(bundledRoot, 'katex.cjs')).default, 'bundled CommonJS');
        const bundled = await import(pathToFileURL(path.join(bundledRoot, 'katex.es.js')).href);
        verify(bundled.default, 'bundled ESM');
        console.log('All math renderer paths reject inherited trust and preserve valid rendering');
      })().catch(error => { console.error(error); process.exitCode = 1; });
    `,
      ],
      { cwd: appRoot, encoding: 'utf8', timeout: 20_000 },
    );
    expect(output).toContain(
      'All math renderer paths reject inherited trust and preserve valid rendering',
    );
  });
});

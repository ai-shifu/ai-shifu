import { execFileSync } from 'node:child_process';
import path from 'node:path';

describe('installed MarkdownFlow Mermaid resolution', () => {
  it('routes every packaged renderer import to the patched dependency in both bundlers', async () => {
    const appRoot = path.resolve(__dirname, '../..');
    // Next's build configuration and resolver need a native Node context.
    const output = execFileSync(
      process.execPath,
      [
        '-e',
        String.raw`
      const assert = require('node:assert/strict');
        const { readFileSync, readdirSync } = require('node:fs');
      const path = require('node:path');
      (async () => {
        const config = await require('next/dist/server/config').default('phase-production-build', process.cwd());
        const compiled = require('next/dist/compiled/webpack/webpack');
        compiled.init();
        const webpackConfig = config.webpack(
          { module: { rules: [] }, resolve: { alias: {} } },
          { webpack: compiled.webpack, defaultLoaders: { babel: {} } },
        );
        const compiler = compiled.webpack({ mode: 'none' });
        const resolver = compiler.resolverFactory.get('normal', {
          alias: webpackConfig.resolve.alias,
          extensions: ['.js', '.mjs', '.cjs'],
          conditionNames: ['import', 'default'],
        });
        const directory = path.join(path.dirname(require.resolve('markdown-flow-ui/renderer')), 'components/ContentRender/plugins');
        try {
          for (const extension of ['es.js', 'cjs']) {
            const source = readFileSync(path.join(directory, 'MermaidChart.' + extension), 'utf8');
            const requests = Array.from(
              source.matchAll(/(?:from\s+|require\()["']([^"']*mermaid[^"']*)["']/g),
              match => match[1],
            );
            assert(requests.length > 0, 'No packaged Mermaid import found');
            for (const request of requests) {
              assert.equal(config.turbopack.resolveAlias[request], 'mermaid');
              const resolved = await new Promise((resolve, reject) => {
                resolver.resolve({}, directory, request, {}, (error, result) => error ? reject(error) : resolve(result));
              });
              assert.equal(resolved, require.resolve('mermaid'));
            }
          }
          const mermaidDirectory = path.dirname(require.resolve('mermaid'));
          const chunksDirectory = path.join(mermaidDirectory, 'chunks/mermaid.core');
          const chunks = readdirSync(chunksDirectory).filter(file => file.endsWith('.mjs'));
          const yamlChunks = chunks.filter(file => readFileSync(path.join(chunksDirectory, file), 'utf8').includes('js-yaml/dist/js-yaml.mjs:'));
          assert.equal(yamlChunks.length, 1, 'Recheck the packaged YAML copies');
          let yamlImports = 0;
          for (const file of [require.resolve('mermaid'), ...chunks.map(file => path.join(chunksDirectory, file))]) {
            const source = readFileSync(file, 'utf8');
            const requests = Array.from(source.matchAll(/(?:from\s+|import\s+)["']([^"']+)["']/g), match => match[1]);
            for (const request of requests.filter(request => request.endsWith(yamlChunks[0]))) {
              yamlImports += 1;
              assert.equal(config.turbopack.resolveAlias[request], 'js-yaml');
              const resolved = await new Promise((resolve, reject) => {
                resolver.resolve({}, path.dirname(file), request, {}, (error, result) => error ? reject(error) : resolve(result));
              });
              assert.equal(resolved, path.join(path.dirname(require.resolve('js-yaml')), 'dist/js-yaml.mjs'));
            }
          }
          assert(yamlImports > 0, 'No packaged YAML imports found');
        } finally {
          await new Promise(resolve => compiler.close(resolve));
        }
        console.log('Patched Mermaid resolves for both distributions and bundlers');
      })().catch(error => { console.error(error); process.exitCode = 1; });
    `,
      ],
      { cwd: appRoot, encoding: 'utf8', timeout: 20_000 },
    );
    expect(output).toContain('Patched Mermaid resolves for both distributions');
  });
});

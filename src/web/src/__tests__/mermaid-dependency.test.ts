import { execFileSync } from 'node:child_process';
import path from 'node:path';

describe('installed MarkdownFlow Mermaid resolution', () => {
  it('uses packaged parsers and safe YAML in both module formats', () => {
    const appRoot = path.resolve(__dirname, '../..');
    // Native imports avoid Jest's ESM transforms and exercise the installed graph.
    const output = execFileSync(
      process.execPath,
      [
        '-e',
        String.raw`
      const assert = require('node:assert/strict');
      const { readFileSync, realpathSync } = require('node:fs');
      const { createRequire } = require('node:module');
      const path = require('node:path');
      const { pathToFileURL } = require('node:url');

      const requests = source => Array.from(
        source.matchAll(/(?:\bfrom\s*|\brequire\s*\(\s*|\bimport\s*(?:\(\s*)?)["']([^"']+)["']/g),
        match => match[1],
      );
      const embeddedYamlParser = entry => {
        const directory = path.dirname(entry);
        const visited = new Set();
        const parsers = [];
        const pending = [entry];
        while (pending.length) {
          const file = pending.pop();
          if (visited.has(file)) continue;
          visited.add(file);
          const source = readFileSync(file, 'utf8');
          if (source.includes('maxTotalMergeKeys') && source.includes('tag:yaml.org,2002:omap')) {
            parsers.push(file);
          }
          for (const request of requests(source)) {
            assert(!/^js-yaml(?:\/|$)/.test(request), 'Unexpected external YAML parser in ' + file);
            if (!request.startsWith('.')) continue;
            const target = path.resolve(path.dirname(file), request);
            if (target.startsWith(directory + path.sep)) pending.push(target);
          }
        }
        assert.equal(parsers.length, 1, 'Expected one reachable guarded YAML parser');
        return parsers[0];
      };

      (async () => {
        const dist = path.dirname(require.resolve('markdown-flow-ui/renderer'));
        const manifest = JSON.parse(readFileSync(path.join(dist, '../package.json'), 'utf8'));
        assert.equal(manifest.dependencies.mermaid, '12.3.0');
        assert.equal(manifest.dependencies['js-yaml'], undefined);

        const config = await require('next/dist/server/config').default('phase-production-build', process.cwd());
        const compiled = require('next/dist/compiled/webpack/webpack');
        compiled.init();
        const webpackConfig = config.webpack(
          { module: { rules: [] }, resolve: { alias: {} } },
          { webpack: compiled.webpack, defaultLoaders: { babel: {} } },
        );
        const compiler = compiled.webpack({ mode: 'none' });
        const { JSDOM } = createRequire(require.resolve('jest-environment-jsdom'))('jsdom');
        const dom = new JSDOM('<!doctype html><html><body></body></html>');
        globalThis.window = dom.window;
        globalThis.document = dom.window.document;
        try {
          for (const extension of ['es.js', 'cjs']) {
            const condition = extension === 'es.js' ? 'import' : 'require';
            const resolver = compiler.resolverFactory.get('normal', {
              ...webpackConfig.resolve,
              extensions: ['.js', '.mjs', '.cjs', '.json'],
              conditionNames: [condition, 'default'],
            });
            const resolveRequest = (importer, request) => new Promise((resolve, reject) => {
              resolver.resolve({}, path.dirname(importer), request, {}, (error, result) => error ? reject(error) : resolve(result));
            });
            const chart = path.join(dist, 'components/ContentRender/plugins/MermaidChart.' + extension);
            const imports = requests(readFileSync(chart, 'utf8')).filter(request => /(?:^|\/)mermaid(?:\/|$)/.test(request));
            assert.equal(imports.length, 1, 'Expected the renderer to import its packaged engine');
            const entry = createRequire(chart).resolve(imports[0]);
            assert.equal(entry, path.join(dist, 'node_modules/mermaid/dist/mermaid.core.' + extension));
            assert.equal(realpathSync(await resolveRequest(chart, imports[0])), realpathSync(entry));
            assert.match(readFileSync(entry, 'utf8'), /["']12\.3\.0["']/);

            // Exercise Mermaid's reachable bundled parser rather than the application's js-yaml.
            const yamlModule = await import(pathToFileURL(embeddedYamlParser(entry)).href);
            const yaml = extension === 'cjs' ? yamlModule.default : yamlModule;
            assert.equal(typeof yaml.load, 'function');
            assert.deepEqual(yaml.load('base: &base {a: 1}\nvalue: {<<: *base, b: true}'), {
              base: { a: 1 }, value: { a: 1, b: true },
            });
            assert.deepEqual(yaml.load('!!omap [{first: 1}, {second: 2}]'), [{ first: 1 }, { second: 2 }]);
            assert.throws(() => yaml.load('!!omap [{duplicate: 1}, {duplicate: 2}]'), /omap/);
            assert.throws(() => yaml.load('value: {<<: [{}, {}, {}, {}]}', { maxTotalMergeKeys: 3 }), /maxTotalMergeKeys/);
            // Empty merge sources must also consume the default aggregate budget.
            const emptySources = 'sources: &sources [' + Array(100).fill('{}').join(', ') + ']\ntargets:\n';
            const mergeTarget = '  - <<: *sources\n';
            assert.equal(yaml.load(emptySources + mergeTarget.repeat(100)).targets.length, 100);
            assert.throws(() => yaml.load(emptySources + mergeTarget.repeat(101)), /maxTotalMergeKeys/);

            const module = await import(pathToFileURL(entry).href);
            const mermaid = extension === 'cjs' ? module.default.default : module.default;
            mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });
            const nested = '['.repeat(110) + '0' + ']'.repeat(110);
            const controls = [
              '---\ntitle: Valid frontmatter\n---\nflowchart TD; A-->B',
              'flowchart TD\nA@{ shape: rect, label: "Valid metadata" } --> B',
              'sequenceDiagram\nparticipant A@{ "type": "boundary" }\nA->>B: Hello',
              'kanban\n  todo[Todo]\n    task[Task]@{ priority: High }',
              'agentflow-beta TB\nA["Task"]@{ shape: task, description: "Valid metadata" }',
            ];
            const probes = [
              '---\ntitle: ' + nested + '\n---\nflowchart TD; A-->B',
              'flowchart TD\nA@{ label: ' + nested + ' }',
              'sequenceDiagram\nparticipant A@{ type: ' + nested + ' }',
              'kanban\n  todo[Todo]@{ priority: ' + nested + ' }',
              'agentflow-beta TB\nA["Task"]@{ shape: task, description: ' + nested + ' }',
              // Agentflow retries multiline metadata after removing trailing commas.
              'agentflow-beta TB\nA["Task"]@{\nshape: task,\ndescription: ' + nested + ',\n}',
            ];
            for (const source of controls) assert.ok(await mermaid.parse(source), source);
            for (const source of probes) await assert.rejects(mermaid.parse(source), /maxDepth/);
          }
        } finally {
          dom.window.close();
          await new Promise((resolve, reject) => compiler.close(error => error ? reject(error) : resolve()));
        }
        console.log('Packaged Mermaid and YAML resolve safely in both formats');
      })().catch(error => { console.error(error); process.exitCode = 1; });
    `,
      ],
      { cwd: appRoot, encoding: 'utf8', timeout: 20_000 },
    );
    expect(output).toContain(
      'Packaged Mermaid and YAML resolve safely in both formats',
    );
  });
});

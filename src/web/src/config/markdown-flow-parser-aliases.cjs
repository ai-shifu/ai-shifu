/* eslint-disable @typescript-eslint/no-require-imports -- Next and Jest load this shared configuration synchronously. */
const { createRequire } = require('node:module');
const path = require('node:path');

function createMarkdownFlowParserAliases(projectRoot) {
  const requireFromApp = createRequire(path.join(projectRoot, 'package.json'));
  const uiDist = path.dirname(requireFromApp.resolve('markdown-flow-ui'));
  const bridge = path.join(
    projectRoot,
    'src/lib/markdown-flow-parser-bridge.cjs',
  );
  const bridgeRequest = `./${path.relative(projectRoot, bridge).split(path.sep).join('/')}`;

  // markdown-flow-ui 0.3.3 preserves these two vendored parser imports.
  // Keep all consumers on the installed parser until the UI ships its upgrade.
  const entries = ['index.es.js', 'index.cjs'].map(file => {
    const request = `../node_modules/remark-flow/dist/${file}`;
    return [request, path.resolve(uiDist, '_virtual', request)];
  });

  return {
    webpack: Object.fromEntries(entries.map(([, file]) => [file, bridge])),
    turbopack: Object.fromEntries(
      entries.map(([request]) => [request, bridgeRequest]),
    ),
  };
}

module.exports = { createMarkdownFlowParserAliases };

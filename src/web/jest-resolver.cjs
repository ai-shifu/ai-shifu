/* eslint-disable @typescript-eslint/no-require-imports -- Jest's custom resolver uses CommonJS. */
const {
  createMarkdownFlowParserAliases,
} = require('./src/config/markdown-flow-parser-aliases.cjs');

const aliases = createMarkdownFlowParserAliases(__dirname).webpack;

module.exports = (request, options) => {
  const resolved = options.defaultResolver(request, options);
  return aliases[resolved] || resolved;
};

// The UI's preserved CommonJS wrapper expects a factory, not parser exports.
// Resolve from the app so its pinned remark-flow replaces the UI 0.3.3 vendor.
// eslint-disable-next-line @typescript-eslint/no-require-imports -- Preserve the UI's synchronous CommonJS factory contract.
exports.__require = () => require('remark-flow');

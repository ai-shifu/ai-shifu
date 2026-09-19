# Cook Web Domain: types

This module owns shared TypeScript declarations, ambient module definitions,
and cross-domain frontend interfaces.

Entry files in this directory: `shifu.ts`, `store.ts`, `sse.d.ts`,
`markdown-flow-ui.d.ts`, `i18n-keys.d.ts`.

## Do

- Treat shared type exports as compatibility surfaces consumed across routes,
  stores, hooks, and components.
- Keep ambient declarations and module augmentation narrow so upstream package
  exports are not accidentally shadowed.
- Prefer updating source types together with their consumers instead of
  papering over mismatches with broad `any` casts.

## Avoid

- Do not replace an upstream module declaration wholesale when a small
  augmentation would be safer.
- Do not leave stale declaration files after refactors that move or rename
  shared types.
- Do not solve runtime-shape drift only in type files without fixing the
  owning implementation.

## Tests

`cd src/web && npm run type-check` checks declarations against their
consumers.

## Related Skills

- `src/web/skills/module-augmentation-guardrails/SKILL.md`

# Cook Web Domain: types

This module owns shared TypeScript declarations, ambient module definitions,
and cross-domain frontend interfaces.

Entry files in this directory: `shifu.ts`, `store.ts`, `sse.d.ts`,
`markdown-flow-ui.d.ts`, `i18n-keys.d.ts`.

Shared compatibility, i18n, privacy and verification rules are inherited from
the root and `src/web/AGENTS.md`; the constraints below are local.

## Do

- Keep ambient declarations and module augmentation narrow so upstream package
  exports are not accidentally shadowed.

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

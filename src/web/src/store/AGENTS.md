# Cook Web Domain: store

This module owns shared frontend stores, store providers, and app-level state
containers used by auth, i18n loading, and shifu flows.

Entry files in this directory: `useUserStore.ts`, `useShifu.tsx`,
`useI18nLoadingStore.ts`, `userProvider.tsx`.

## Do

- Preserve course, environment, system, and layout state semantics across
  learner and teacher consumers; use direct module imports inside store
  implementations to avoid barrel cycles.
- Keep store state shape and exported actions stable because many components
  depend on these slices implicitly.
- Preserve the boundary between store state and side-effect helpers so
  persistent logic stays testable.
- Treat auth token handling and global providers as integration points shared
  across the whole frontend.

## Avoid

- Do not add page-specific derived state here when a local hook or component
  can own it safely.
- Do not rename store fields without updating all selectors and hooks in the
  same task.
- Do not duplicate token or session storage behavior outside the existing
  user-store path.

## Tests

`cd src/web && npm run test -- src/store/`

## Related Skills

- `src/web/skills/hook-contract-refactor-safety/SKILL.md`
- `src/web/skills/chat-layout-width-detection/SKILL.md`

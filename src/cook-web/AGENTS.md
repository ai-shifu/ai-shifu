# Cook Web AI Collaboration Rules

This file routes frontend work to the right source documents and keeps the
hard frontend constraints close to `src/cook-web/`.

## Scope

- Apply this file to `src/cook-web/`, including app routes, components,
  shared libraries, stores, and frontend tests.
- Use `../../ARCHITECTURE.md` for the repository map and
  `../../docs/engineering-baseline.md` for the frontend engineering handbook.
- More specific rules still live in `src/cook-web/src/**/AGENTS.md`.

## Do

- Inspect the route, component, hook, store, and shared lib path before
  changing frontend behavior.
- Keep request transport on `src/cook-web/src/lib/request.ts` and
  `src/cook-web/src/lib/api.ts`, and preserve the unified business-code
  handling path.
- Treat route-entry files (`page.tsx`, `layout.tsx`, `route.ts`) as the
  visible route boundary and move reusable logic into components, hooks,
  stores, or shared libs.
- Keep browser-harness changes aligned with the Playwright smoke suite and the
  local Docker dev stack.
- Treat legacy `c-*` directories as maintained compatibility surfaces until a
  planned migration removes them.

## Avoid

- Do not add ad-hoc component fetch logic or a second request abstraction.
- Do not hardcode user-facing strings or auth/request header construction in
  UI components.
- Do not treat legacy `c-*` paths as dead code that can be broken casually.
- Do not add new complex-work checklists outside ExecPlans.

## Commands

- `cd src/cook-web && npm run dev`
- `cd src/cook-web && npm run type-check`
- `cd src/cook-web && npm run lint`
- `cd src/cook-web && npm run test:e2e`

## Tests

- Run focused Jest tests for the touched domain first.
- Run `npm run type-check` and `npm run lint` when shared route, hook, store,
  or request behavior changes.
- Run `npm run test:e2e` when browser harness code or smoke selectors change.

## Related Skills

- `src/cook-web/SKILL.md`
- `src/cook-web/skills/README.md`

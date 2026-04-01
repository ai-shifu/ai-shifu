# Cook Web AI Collaboration Rules

This file owns frontend-wide AI execution rules for the Next.js Cook Web app,
shared request utilities, state containers, and the legacy `c-*`
compatibility surface.

## Scope

- Apply this file to `src/cook-web/`, including app routes, components,
  shared libraries, stores, tests, and the local frontend skill index.

- More specific rules belong in `src/cook-web/src/<domain>/AGENTS.md`. Keep
  this file focused on patterns shared across multiple frontend domains.

- Frontend engineering conventions live in the
  [engineering baseline](../../docs/engineering-baseline.md), especially:
  [Architecture](../../docs/engineering-baseline.md#architecture),
  [API Contract Baseline](../../docs/engineering-baseline.md#api-contract-baseline),
  [Testing Expectations](../../docs/engineering-baseline.md#testing-expectations),
  [Internationalization Rules](../../docs/engineering-baseline.md#internationalization-rules),
  and [File And Directory Naming Conventions](../../docs/engineering-baseline.md#file-and-directory-naming-conventions).

- Legacy `c-*` directories remain active compatibility surfaces. Treat them as
  maintained code, not dead code, until a deliberate migration removes them.

## Do

- Inspect the current route, component, hook, store, and shared-lib path
  before changing frontend behavior so new code aligns with the existing
  implementation.

- Prefer extending the current request stack, shared utilities, stores, hooks,
  and compatibility layers instead of creating a second way to do the same
  thing.

- Use the shared request stack in `src/cook-web/src/lib/request.ts` and
  `src/cook-web/src/lib/api.ts` instead of adding ad-hoc `fetch` logic in
  pages or components.

- Keep App Router behavior, business-code handling, i18n routing, naming, and
  request-contract changes aligned with
  [docs/engineering-baseline.md](../../docs/engineering-baseline.md).

- Route all user-facing text through shared i18n JSON namespaces under
  `src/i18n/`, and keep the frontend language surface limited to `en-US` and
  `zh-CN` unless product scope changes.

- Prefer shared utilities when logic appears in two or more places. Move
  stable parsing, routing, and serialization code into `lib/`, `hooks/`, or
  `c-utils/` instead of duplicating it in pages.

## Avoid

- Do not create duplicate frontend helpers, request wrappers, stores, or
  route parsers when an existing implementation can be reused cleanly.

- Do not hardcode user-facing strings, route-parameter parsing, or auth-header
  construction inside UI components.

- Do not bypass the unified business-code handling path or create a second
  request abstraction that diverges from `lib/request.ts`.

- Do not treat legacy `c-*` directories as safe to break. New modern code
  should prefer modern folders, but compatibility behavior still matters.

- Do not add frontend-only translations under `public/locales` when the shared
  JSON source under `src/i18n/` should own the text.

## Commands

- `cd src/cook-web && npm run dev` starts the local frontend dev server.

- `cd src/cook-web && npm run type-check` is the baseline static check for
  shared TypeScript changes.

- `cd src/cook-web && npm run lint` catches lint regressions across modern and
  legacy frontend code.

- `cd src/cook-web && npm run test` runs the Jest suite; narrow by file or
  pattern while iterating on a single domain.

## Tests

- Run focused Jest tests for the touched domain first, then expand to
  `npm run type-check` and `npm run lint` before closing the task.

- When request or route behavior changes, cover both the happy path and the
  business-code or auth-error path.

- When shared types or hook contracts change, update all consumers in the same
  task and rerun targeted tests for the affected areas.

- When only docs or AI instructions change, at minimum run
  `python scripts/check_ai_collab_docs.py` and note that runtime code was not
  exercised.

## Related Skills

- `src/cook-web/SKILL.md` is the frontend skill index and boundary map.

- Use the existing focused skills under `src/cook-web/skills/` for chat,
  routing, streaming, hook-contract, and audio-specific workflows.

- Keep durable structural rules in `AGENTS.md`; keep multi-step debugging
  workflows in `SKILL.md` so they stay discoverable without bloating
  directory-level docs.

- Create a new focused skill when the same frontend troubleshooting flow is
  repeated across multiple tasks or regressions.

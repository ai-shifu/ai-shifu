# Cook Web AI Collaboration Rules

This file routes frontend work to the right source documents and keeps the
hard frontend constraints close to `src/web/`.

## Scope

- Apply this file to `src/web/`, including app routes, components,
  shared libraries, stores, and frontend tests.
- Use `../../ARCHITECTURE.md` for the repository map and
  `../../docs/engineering-baseline.md` for the frontend engineering handbook.
- More specific rules still live in `src/web/src/**/AGENTS.md`.

## Do

- Inspect the route, component, hook, store, and shared lib path before
  changing frontend behavior.
- Keep request transport on `src/web/src/lib/request.ts` and
  `src/web/src/lib/api.ts`, and preserve the unified business-code
  handling path.
- Treat route-entry files (`page.tsx`, `layout.tsx`, `route.ts`) as the
  visible route boundary and move reusable logic into components, hooks,
  stores, or shared libs.
- Keep browser-harness changes aligned with the Playwright smoke suite and the
  local Docker dev stack.
- Treat legacy `c-*` directories as maintained compatibility surfaces until a
  planned migration removes them.
- Every new user-facing Cook Web capability or interaction path must add or
  extend its Umami event family contract, producer, and focused tests in the
  same change. At minimum, capture a meaningful feature exposure, accepted use,
  or a meaningful outcome; add an exposure event when the metric needs an
  eligible-view denominator, and use attempt plus terminal-result events when
  one signal cannot describe an asynchronous workflow accurately. An existing
  generic SPA pageview does not satisfy this requirement unless route entry is
  itself the documented feature-adoption signal. The feature is incomplete
  without this coverage. Pure visual styling, copy-only, performance-only,
  test-only, and behavior-preserving refactoring changes do not require a new
  event. Any new user-observable action, state transition, or invocation path,
  including one introduced for accessibility, does.
- Follow `../../docs/references/frontend-product-analytics.md` for every new or
  changed Umami event. Send business events through the shared `useTracking`
  and `tracking` path; only the centralized tracking implementation may access
  `window.umami`, identify users, queue calls, or sanitize provider payloads.
- Keep SPA pageview ownership in `UmamiLoader`. Emit business events from a real
  user action or a post-commit effect with stable inputs, never during render;
  define the guest and preview policy plus the per-render, per-open, per-session,
  or other deduplication scope explicitly.
- Give new events stable `snake_case` names, normally
  `<actor>_<object>_<action-or-state>`. Put stable resource identifiers in an
  explicit payload field instead of constructing dynamic event names, and do
  not rename or repurpose a consumed event without a coordinated migration.
- Build payloads from an explicit allowlist of flat scalar fields. Report
  attempts and terminal `success`, `failed`, or `cancelled` outcomes at the
  transition they actually describe, and keep tracking fail-open so the main
  user action never depends on analytics delivery.
- Treat changes to centralized identify and pageview metadata as privacy
  contract changes too. Allow only necessary pseudonymous identity and reviewed
  session enums, and remove queries, fragments, credentials, and sensitive path
  data from any new or changed pageview handling.
- For clickable UI, prefer semantic elements (`button`, `a`, `summary`) or
  shared Radix/shadcn primitives. If a non-semantic element must handle clicks,
  mark the actual clickable target with `data-clickable="true"` and preserve
  disabled states with `disabled`, `aria-disabled="true"`, or `data-disabled`.
  Do not rely on page-local cursor styles or broad `* { cursor: pointer; }`
  rules. Full-screen onboarding/backdrop advance surfaces are the exception:
  keep their large background or card hit areas on the default cursor so the
  whole page does not read as a button.

## Avoid

- Do not add ad-hoc component fetch logic or a second request abstraction.
- Do not hardcode user-facing strings or auth/request header construction in
  UI components.
- Do not call `window.umami` or identify users from feature code, add a second
  pageview path, treat an awaited tracking call as delivery confirmation, or
  use analytics results to drive product state.
- Do not spread form values, API responses, configuration objects, user-authored
  content, complete URLs, queries, referrers, or raw errors into an Umami event
  or identity payload. Size sanitization is not privacy sanitization.
- Do not treat legacy `c-*` paths as dead code that can be broken casually.
- Do not add new complex-work checklists outside ExecPlans.

## Commands

- `cd src/web && npm run dev`
- `cd src/web && npm run type-check`
- `cd src/web && npm run lint`
- `cd src/web && npm run test:e2e`

## Tests

- Run focused Jest tests for the touched domain first.
- For each new or changed Umami event, assert the exact event name and allowlisted
  payload, sensitive-field absence, trigger timing, eligibility and deduplication,
  all relevant terminal outcomes, and continued business behavior when tracking
  throws or is unavailable.
- Run `npm run type-check` and `npm run lint` when shared route, hook, store,
  or request behavior changes.
- Run `npm run test:e2e` when browser harness code or smoke selectors change.

## Related Skills

- `src/web/SKILL.md`
- `src/web/skills/README.md`

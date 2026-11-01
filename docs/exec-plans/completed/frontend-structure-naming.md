# Frontend structure and file naming

## Purpose / Big Picture

Make frontend ownership and file purpose visible in paths by applying the
existing engineering naming conventions consistently. This is a mechanical
organization refactor: routes, API payloads, storage keys, analytics contracts,
styles and user interactions retain their existing behavior.

## Progress

- [x] 2026-10-31 CST: Refreshed origin/main, created
  `sunner/frontend-structure-naming`, and audited frontend ownership and naming.
- [x] 2026-10-31 CST: Normalize 432 source paths and update all consumers.
- [x] 2026-10-31 CST: Align current documentation, tooling paths and boundary
  baseline with the moved files.
- [x] 2026-10-31 CST: Validate imports, frontend tests, types, lint, production
  build and repository guardrails; prepare the verified branch for PR delivery.

## Surprises & Discoveries

- The handbook already specifies kebab-case directories and regular TS files,
  PascalCase React components, and component-matching CSS modules. Existing
  files inconsistently follow those conventions.
- The learner route has compatibility re-exports for shared components. Keep
  those contracts during path changes rather than combining implementations.
- Stylesheet and source-file tests, documentation links and the architecture
  baseline contain paths outside normal import declarations.
- macOS preserves directory casing in the Git index during a plain add. Explicit
  temporary Git moves were required; all 965 indexed source paths now match the
  filesystem and intended casing exactly.
- The installed default Python lacked the pinned Markdown parser; an isolated
  temporary tool environment supplied markdown-it-py 4.0.0. Validation used the
  project's Node.js 22.23.4 runtime.
- Default Playwright could not launch its missing pinned Chromium. The two
  independent browser regressions passed using installed Chrome and a temporary
  configuration against this branch's production frontend. The full authenticated
  runtime smoke suite requires the unavailable local backend stack.

## Decision Log

- Keep the established `api`, `components`, `hooks`, `lib`, `store`, `types`,
  `constants`, `config` and `assets` boundaries, including `lib/shifu`.
- Keep Next.js route segments and reserved entry filenames unchanged. Rename
  non-route learner component folders to descriptive kebab-case names.
- Normalize regular helpers, hooks, stores, constants and matching tests to
  kebab-case. Preserve code identifier conventions separately from filenames.
- Expand opaque names such as `bz`, `studyV2`, `m`, `NewChatComp`, and misspelled
  `constans` / `pollyfill` by inspecting their actual responsibilities.
- Preserve public route URLs, request/wire names, analytics names, localization
  namespaces and persisted keys. Do not introduce new feature behavior.
- Update live documentation and tooling references. Completed plans and dated
  history retain historical paths unless an executable check requires a fix.

## Outcomes & Retrospective

The frontend now consistently names responsibility-based directories, regular
modules, hooks and stores, React components, companion styles and tests. Opaque
learning API, feedback, mobile component and lesson-conversation names have
descriptive replacements. Source-layout documentation and executable consumers
point at the new paths.

Validation passed: 279 Jest suites / 3,593 tests, TypeScript, ESLint, production
build, two Chrome browser regressions, four backend deployment-contract tests,
architecture fixtures and live boundary checks, repository harness and the full
lefthook pre-commit gate. The backend contract tests used `--noconftest` because
the unrelated global fixture dependencies are absent from the temporary Python
environment. All 46 Next.js route/layout/error entry paths are unchanged.

Independent checks resolved 4,098 module references with exact casing, confirmed
AST-equivalent behavior apart from approved path and identifier renames, and
confirmed byte-identical contents for all 92 stylesheet and other non-code files.
The architecture baseline retains its existing 120 backend entries and zero
frontend violations. Full authenticated runtime smoke coverage remains an
environment-dependent check, not a claimed pass. No merge to main is authorized.

## Context and Orientation

`src/web/src/app` owns Next.js route composition. Shared components live under
`src/web/src/components`; learner-only composition lives alongside
`app/c/[[...id]]`. Shared transport remains in `lib/request.ts` and `lib/api.ts`.
The naming contract lives in `docs/engineering-baseline.md`, not in a new
parallel convention document. Root and subtree `AGENTS.md` files own constraints.

## Plan of Work

Inventory paths and build an explicit old-to-new mapping. Apply directory and
filename normalization together so imports, dynamic imports, re-exports, Jest
mocks and file-reading tests resolve at the new paths. Expand only selected
opaque component and hook identifiers. Update current knowledge references and
the path-based architecture baseline without increasing its accepted debt.
Validate the complete frontend because shared modules have broad consumers.

## Concrete Steps

1. Inspect implementation, call sites, styles and adjacent tests for each
   semantic rename; generate the mechanical casing map.
2. Move files and rewrite references using resolved original paths, including
   relative imports between files moved into different folders.
3. Add a concise source-directory map and clarify naming examples in the
   handbook; refresh generated knowledge indexes.
4. Run frontend checks and repository guardrails, inspect rename-aware diffs,
   and commit and open a non-draft PR after required tooling checks pass.

## Validation and Acceptance

The frontend passes its Jest suite, TypeScript check, ESLint and production
build. The route manifest retains existing application URLs. Source imports
resolve with exact filesystem casing. The repository harness and architecture
boundary checks pass with only path-equivalent baseline migrations. No
dependency, product copy, API, storage or analytics contract changes are needed.

## Idempotence and Recovery

Use an explicit collision-checked mapping and perform renames through temporary
paths for case-only moves on macOS. Run reference updates against the original
source snapshots once. Git retains the complete pre-refactor tree; avoid reset
or checkout commands that could discard unrelated user work.

## Interfaces and Dependencies

No new dependency or interface is introduced. React exports may receive
descriptive internal names with every in-repository consumer updated together.
The installed frontend dependencies are reused, and lockfiles remain unchanged.

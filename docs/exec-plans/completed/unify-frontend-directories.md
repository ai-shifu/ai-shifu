# Unify Frontend Source Directories

## Purpose / Big Picture

Remove the historical `c-` source-directory split from Cook Web. Learner,
teacher, login, preview, and analytics code already share these implementations;
their location should describe their responsibility. Preserve all runtime,
request, state, route, styling, asset, and analytics contracts.

## Progress

- [x] 2026-09-05 UTC: Audited all nine source directories, their consumers,
  destination rules, generated instructions, and validation entry points.
- [x] 2026-09-05 UTC: Migrated 123 source, test, style, and asset files,
  including the merged store barrel, and updated all frontend references.
- [x] 2026-09-05 UTC: Updated architecture guidance, generated mirrors, and
  knowledge indexes; moved surviving domain invariants to their new owners.
- [x] 2026-09-05 UTC: Passed focused and full frontend tests, types, lint,
  production build, repo harness, architecture fixtures, and full pre-commit.
- [x] 2026-09-05 UTC: Reviewed and prepared the focused migration for ready PR
  delivery on `sunner/unify-frontend-directories`.

## Surprises & Discoveries

- All nine directories have production consumers outside their own subtree.
- The two store `index.ts` files are the only destination file collision.
  Merging their exports also merges Jest mock identities and can expose import
  cycles, so these changes need explicit verification.
- This worktree starts without frontend dependencies. The shell Node version
  differs from the pinned Node 22.16.0, and Ruff must be 0.16.5. Install isolated
  task tooling before validation; preserve existing environment files.
- Moving ContentBlock into components exposed its import of a route-local
  re-export facade. Importing the same functions directly from
  `lib/customButtonAfterContent.ts` fixes that boundary without changing code
  behavior or widening the committed baseline.
- Nineteen tests mocked both old store barrels. Their factories now share one
  module identity and were consolidated without dropping mocked exports. The
  course-preview layout test explicitly retains the real learner stores while
  continuing to isolate authentication. UserProvider imports its sibling stores
  directly to avoid introducing a barrel cycle.
- Two backend TTS module headers referenced frontend helpers that had already
  been deleted before this migration. Removed those obsolete notes rather than
  publishing new nonexistent paths; backend runtime code is unchanged.

## Decision Log

- 2026-09-05: Move `c-api`, `c-assets`, `c-components`, `c-constants`,
  `c-store`, and `c-types` into `api`, `assets`, `components`, `constants`,
  `store`, and `types` respectively. Keep component subgroups and filenames to
  minimize behavior-independent changes.
- 2026-09-05: Move `c-common/hooks` into `hooks`, tracking transport into
  `lib/tracking.ts`, `c-utils` into `lib`, and `c-service` into `lib/shifu`.
  Preserve existing implementations instead of rewriting service contracts.
- 2026-09-05: Remove obsolete directory guidance and merge its still-relevant
  invariants and skill routing into destination metadata. Regenerate mirrors.
- 2026-09-05: Keep `/c` routes, storage keys, analytics events, API payloads,
  exports, and component behavior stable. This refactor adds no user action and
  does not require a new analytics event.

## Outcomes & Retrospective

All nine historical source directories are removed. Shared modules now live in
the responsibility-based directories described below. Runtime behavior and
external contracts remain unchanged; the internal store barrel is unified.

Verification under Node 22.16.0 and Ruff 0.16.5:

- Focused Jest: 19 suites, 110 tests passed.
- Full Jest: 214 suites, 1,966 tests passed after reconciling store mocks.
- TypeScript type-check and the Next.js production build passed.
- All 42 migrated image/SVG assets are byte-identical to the starting commit.
- Compared 546 production TypeScript files against the starting commit;
  differences beyond path and formatting changes are the reviewed store exports,
  direct UserProvider imports, and ContentBlock's direct shared-helper import.
- Repo harness, architecture fixtures, and boundary checks passed. The existing
  133 backend boundary entries remain unchanged; no frontend violations remain.
- Dev-tool verification and `lefthook run pre-commit --all-files` passed,
  including lint, translation contracts, Ruff, and generated-document checks.

The seeded backend/browser smoke stack was not started for this migration;
browser integration coverage remains the existing unit suites and production
build rather than a live authenticated end-to-end run.

## Context and Orientation

The frontend is `src/web`. Its Next.js route boundary is `src/web/src/app`.
`lib/request.ts` and `lib/api.ts` own the shared request path. Domain instruction
files are generated from `scripts/generate_ai_collab_docs.py`; root architecture
and frontend guidance are maintained source documents. The boundary checker
tracks existing debt in `docs/generated/architecture-boundary-baseline.json`.

## Plan of Work

Perform a path migration on a task branch, including import/export specifiers,
relative imports, Jest mocks, asset/style paths, and maintained documentation.
Reconcile store exports without changing store instances or contracts. Inspect
any newly reported architectural dependency instead of expanding the baseline
blindly. Update the generator metadata and canonical rules, then regenerate
instruction and knowledge outputs. Run focused checks before broader coverage.

## Concrete Steps

1. Move source files according to the Decision Log and rewrite references.
2. Resolve export/mock collisions and check the source graph for stale paths.
3. Update architecture guidance and generated domain metadata.
4. Run `python3 scripts/generate_ai_collab_docs.py` and
   `python3 scripts/build_repo_knowledge_index.py`.
5. In `src/web`, run focused Jest tests, `npm run type-check`, `npm run lint`,
   `npm run test:ci`, and `npm run build` under Node 22.16.0.
6. Run repo harness and architecture fixture checks, then
   `python3 scripts/check_dev_tools.py` and
   `lefthook run pre-commit --all-files` before committing.
7. Push the task branch, create a focused ready PR, and inspect its live state.

## Validation and Acceptance

No `src/web/src/c-*` directories or old runtime imports remain. Login and user
state, course state/streaming, lesson preview, modal behavior, and analytics
ordering retain existing regression coverage. Types, lint, full Jest coverage,
and a production build pass. Asset references compile and source moves preserve
their bytes. Repo harness and architecture fixtures pass with no new unmanaged
dependency. Record any unavailable integration checks with their actual cause.

## Idempotence and Recovery

The task branch isolates this migration. File moves must not overwrite existing
destination files; merge only reviewed collisions. Generators can be rerun and
must produce deterministic output. Restore individual tracked files from the
pre-migration commit if a rewrite exceeds scope. Never overwrite local `.env`
files or commit credentials, build outputs, or task tooling.

## Interfaces and Dependencies

No package versions or external interfaces change. The app remains private;
its internal TypeScript paths migrate atomically with every in-repo consumer.
The `/c` URL namespace is independent of the removed source-directory prefix.

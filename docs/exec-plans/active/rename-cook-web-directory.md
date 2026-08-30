# Rename The Cook Web Directory

This ExecPlan is a living document and must stay aligned with `PLANS.md`.

## Purpose / Big Picture

Move the Next.js frontend from `src/cook-web/` to the shorter, clearer
`src/web/` path without changing product behavior or breaking repository
automation. After the migration, contributors, coding agents, CI jobs, release
workflows, Docker builds, local environments, generators, checkers, and
documentation must all resolve the frontend through `src/web/`, and stale
`src/cook-web` path assumptions must fail fast instead of silently skipping
work.

The product and deployed container are still named Cook Web. Stable deployment
contracts such as the `ai-shifu-cook-web` image/service names and
`AI_SHIFU_COOK_WEB_IMAGE_NAME` remain unchanged unless a separate deployment
migration explicitly replaces them.

## Progress

- [x] 2026-08-30 11:42 CST: Confirmed the worktree is clean, fetched the latest
  `origin/main`, verified `HEAD` matches it, and created
  `sunner/rename-cook-web-to-web` in the current worktree.
- [x] 2026-08-30 11:42 CST: Started a full tracked-reference audit across
  frontend sources, CI, Docker, scripts, generated guidance, and documentation.
- [x] 2026-08-30 12:13 CST: Renamed the frontend directory and updated every
  live repository path contract, including the external deploy-config build
  entry point.
- [x] 2026-08-30 12:13 CST: Regenerated the collaboration and repository
  knowledge artifacts and proved a second generator run was byte-for-byte
  deterministic.
- [x] 2026-08-30 12:13 CST: Completed static, frontend, workflow, browser, and
  runtime-path validation. Docker/Compose path closure was checked statically;
  this host has no Docker-compatible CLI or daemon for a local image build.
- [x] 2026-08-30 12:13 CST: Completed the final stale-path and diff audit,
  including independent review of migration compatibility and allowlists.
- [x] 2026-08-30 13:24 CST: Verified the pull-request runtime harness with real
  Compose rendering, image builds, stack startup, endpoint readiness, and a
  Playwright smoke test; updated the path harness to tolerate ignored artifacts
  left by existing checkouts while continuing to reject tracked legacy paths.
- [x] 2026-08-30 13:35 CST: Made Codex worktree setup resolve frontend `.env`
  and `node_modules` independently, then added durable Darwin/Linux fixtures
  for current, pre-migration, upgraded, and mixed-asset source checkouts.

## Surprises & Discoveries

- Observation: the supplied worktree began at a detached `HEAD`, but that
  commit exactly matched the freshly fetched `origin/main`.
  Evidence: both resolved to `df8ee2f4af72d3df536ae10abcadb9c54dcfb53d`.
- Observation: `src/cook-web` was embedded in generated collaboration guidance,
  path-filtered workflows, Docker build contexts, local environment setup,
  repository checkers, and long-lived documentation, so a filesystem-only move
  would cause silent CI skips and broken contributor commands.
  Evidence: the initial tracked scan found 121 files containing the exact path.
- Observation: Git can leave ignored `.env`, `node_modules`, or build output in
  `src/cook-web` after applying the tracked rename to an existing checkout.
  Evidence: the repository harness passes with an ignored legacy
  `node_modules` directory present and still rejects tracked legacy paths.
- Observation: GitHub CodeQL identifies alerts by path, so the directory rename
  surfaced four existing high-severity alerts as new even though the relevant
  blobs are unchanged.
  Evidence: the four branch alerts exactly match open default-branch alerts by
  rule, message, location, and source blob; the PR documents this relocation.

## Decision Log

- Decision: treat this as a path-contract migration, not a Cook Web product or
  container rename.
  Rationale: the requested change is the repository directory name. Renaming
  deployed images, Compose services, Nginx upstreams, secrets, or registry
  variables would create an unrelated rollout and compatibility break.
  Date/Author: 2026-08-30 / Codex
- Decision: update historical and active documentation paths mechanically when
  they point into the repository.
  Rationale: old plan history remains semantically accurate with the new path,
  while clickable commands and continuation instructions stay executable.
  Date/Author: 2026-08-30 / Codex
- Decision: rename internal technical labels and generated rule filenames when
  they encode the old directory identity, while retaining explicit Cook Web
  branding and stable deployment identifiers.
  Rationale: contributor-facing automation should match `src/web` clearly,
  but externally consumed names require backwards compatibility.
  Date/Author: 2026-08-30 / Codex

## Outcomes & Retrospective

The Next.js application now lives solely under `src/web/`. GitHub Actions path
filters, cache inputs, working directories, release metadata, Docker build
contexts, local helpers, Codex actions, generators, checkers, skills, and
documentation all resolve that path. The deployment-facing Cook Web image,
service, cache-scope, and environment-variable names remain unchanged.

The first release after this migration can still compare its MarkdownFlow UI
pin against a pre-migration tag: `prepare-release.yml` tries the new lockfile
path first and then the exact historical path. Codex worktree setup accepts
current, pre-migration, and upgraded source checkouts while always targeting
`src/web`. It resolves `.env` and `node_modules` independently, so ignored
assets left at the legacy path are still copied or reused after Git moves the
tracked frontend. Ten durable Darwin/Linux fixtures cover current, legacy,
upgraded, and mixed-asset layouts. The private npm package name remains
`cook-web` so old and new lockfiles stay byte-identical and existing
`node_modules` can be reused safely.

The repository harness now rejects a missing `src/web`, any reintroduced
tracked legacy path or filename, and every unapproved old-path occurrence. It
intentionally tolerates ignored legacy artifacts left by existing checkouts.
The two required compatibility surfaces are checked by exact line and
occurrence count, so deleting a needed fallback or hiding a new stale path in
the same file both fail validation.

Verification passed for the full pre-commit hook suite, repository harness,
architecture fixtures and baseline, YAML/JSON syntax, embedded release Python,
translation usage, generator determinism, frontend formatting, linting, type
checking, all 185 Jest suites (1,667 tests), the optimized production build,
and the runnable browser-only Playwright case through the standard
`npm run test:e2e` entry. This host has no Docker-compatible CLI or daemon, so
the local Docker checks used static path closure. The pull-request runtime
harness subsequently passed real Compose rendering, cached image builds, full
stack startup, endpoint readiness, and the browser smoke flow against
`src/web`.

## Context and Orientation

Before this migration, `src/cook-web/` owned the Next.js application, Jest and
Playwright tests, package manifests, Dockerfiles, local frontend guidance, and
focused skills. Repository-level consumers include `.github/workflows/`, `docker/`,
`.codex/environments/`, `.cursor/`, `scripts/`, `lefthook.yml`, instruction
generators, generated knowledge indexes, and developer documentation.

The primary structural sources of truth are `ARCHITECTURE.md`, `AGENTS.md`,
`SKILL.md`, `docs/engineering-baseline.md`, and the frontend-local guidance moved
from `src/cook-web/` to `src/web/`. Generated `CLAUDE.md`, Cursor rules, GitHub
instructions, and repository inventories must be regenerated through their
own generators rather than hand-maintained independently.

## Plan of Work

1. Inventory exact-path references, lower-case technical labels, generated
   outputs, file names, and stable deployment identifiers.
2. Move the directory with Git history preservation and update all live
   repository paths from `src/cook-web` to `src/web`.
3. Rename internal path-oriented labels and files where the old directory name
   would be misleading, while preserving Cook Web branding and external
   container/image/environment contracts.
4. Update generators and checkers first, then regenerate their declared
   outputs and refresh the knowledge index.
5. Validate path filters, caches, working directories, package commands,
   Docker build contexts, Compose rendering, generated-file determinism, and
   frontend behavior.
6. Prove the old directory path is absent from tracked content and file names,
   review the full diff, and document any intentionally preserved
   `cook-web` deployment identifiers.

## Concrete Steps

- Run `git mv src/cook-web src/web`.
- Replace live repository references to `src/cook-web` with `src/web`.
- Update `.github` path filters, cache dependency paths, working directories,
  release metadata paths, and summary text that describes repository files.
- Update Docker build contexts, `COPY` paths, mounted source paths, and helper
  commands while preserving `ai-shifu-cook-web` service/image compatibility.
- Update environment setup, Cursor launchers, hooks, scripts, checkers, and
  generated guidance ownership maps.
- Regenerate AI collaboration docs and repository knowledge indexes.
- Run the acceptance commands below and record their observable results.

## Validation and Acceptance

The migration is accepted only when all of the following are true:

- `src/web/` exists and no tracked file remains under `src/cook-web/`; ignored
  local artifacts left by an existing checkout do not invalidate the commit.
- No tracked file or tracked filename contains a stale `src/cook-web` path
  outside the explicitly documented source-checkout compatibility fallback,
  historical release-tag fallback, and this migration record.
- GitHub workflow path filters, cache inputs, working directories, release bump
  paths, and runtime artifact paths all use `src/web`.
- Repository generators run successfully and a second run is deterministic.
- `python scripts/check_dev_tools.py` reports the expected frontend tooling.
- `python scripts/check_repo_harness.py` passes.
- `python scripts/check_architecture_boundaries.py --run-fixture-tests` passes.
- Frontend formatting/lint, type checking, Jest, and production build commands
  pass from `src/web`.
- Relevant workflow-script tests and translation checks pass.
- Every touched Compose file renders with `docker compose ... config`, and the
  runtime-harness build path can resolve the relocated frontend sources.
- `git diff --check` passes and the final diff contains no unrelated behavior
  changes.

## Idempotence and Recovery

The path replacement and generators must be safe to rerun. If a generator
reintroduces `src/cook-web`, fix its source template and regenerate instead of
editing only the output. If a runtime validation fails because local services
or secrets are unavailable, preserve the repository changes, capture the exact
failure, and distinguish an environment blocker from a path regression.

The rename is recoverable through Git because it is performed as a tracked
move on a dedicated branch. Local ignored frontend assets such as `.env`,
`node_modules`, and `.next` must remain local and must never be committed.

## Interfaces and Dependencies

- `src/web/` becomes the sole repository path for the Next.js frontend.
- GitHub Actions path filters and `working-directory` values consume
  `src/web/` directly.
- Repository Python/Node scripts consume the new path when scanning frontend
  sources or generating artifacts.
- Docker build files consume `src/web/` as their build context or `COPY`
  source, but keep the existing Cook Web image and service contracts.
- AI collaboration and skill routers point to `src/web/AGENTS.md`,
  `src/web/SKILL.md`, and their descendants.

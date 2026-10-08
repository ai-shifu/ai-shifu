# Reuse production images in PR runtime checks

## Purpose / Big Picture

Build each AMD64 production image once per PR and exercise that exact local
image in both the production smoke check and the browser runtime harness.
Remove duplicate AMD64 packaging jobs. Run additional native ARM64 checks only
for affected services when packaging inputs change. Main, release, candidate
publication and ordinary manual packaging validation keep both architectures.

## Progress

- [x] 2026-10-08 10:35 UTC: User approved unifying runtime and production images.
- [x] 2026-10-08 10:37 UTC: Fetched main and created the task branch from
  `ece51c75d`; inspected workflow, Compose, image smoke and browser contracts.
- [x] 2026-10-08 10:41 UTC: Switched runtime Web to the production Dockerfile;
  added production smoke using the same loaded images before Compose startup.
- [x] 2026-10-08 10:48 UTC: Focused image/runtime/selection regressions, pinned
  Ruff, actionlint, Compose rendering and architecture boundaries pass.
- [x] 2026-10-08 10:51 UTC: All 105 focused regressions, tool doctor, repository
  harness and all-files lefthook gate pass; independent review found no blocker.
- [x] 2026-10-08 10:58 UTC: Corrected the first CI's Bake override failure and
  executed the exact workflow flags with Buildx v0.37.2 locally; both targets
  resolve to the production Dockerfiles, AMD64 and local Docker image exports.
- [ ] Open a ready PR and verify native image, Compose and browser checks in CI.

## Surprises & Discoveries

- API runtime already built the production Dockerfile, but overrides its command
  to seed MySQL and start one worker. The default production command can be
  smoke-tested against the same loaded image before starting the browser stack.
- Web runtime used a separate single-stage image, unlike the production Alpine,
  dependency-pruned, non-root image. The existing nginx routes expect port 5000;
  setting the production image's `PORT` preserves the harness network contract.
- A global Markdown exclusion and omitted shared i18n trigger could skip changes
  to production image content. Production Markdown and i18n belong in runtime
  coverage; non-production repository docs remain outside source filters.
- Local macOS has no Docker daemon. Native Linux image and browser acceptance
  must be verified through the PR workflow, not inferred from YAML tests.
- The first runtime CI run rejected the Bake CLI override `platforms` before
  building any image. Buildx v0.37.2 requires the singular CLI key `platform`,
  although its printed JSON field is plural. Correct the override and validate
  it with the same Buildx version before retrying CI.

## Decision Log

- Keep both production AMD64 services in the integration harness because the
  browser flow depends on the API and Web stack. Use one bake/load operation,
  then production smoke and `compose up --no-build --pull never` on that runner.
- Reuse the existing production-image smoke script to cover default startup,
  native modules, translations, assets and non-root Web execution.
- Preserve Compose service names and shared dev nginx configuration. Delete the
  obsolete runtime-only Web Dockerfile instead of maintaining two build paths.
- Select extra ARM64 services from the PR's three-dot diff. Ordinary source and
  shared translation changes use runtime validation; dependency/Dockerfile inputs
  select their service, and shared packaging machinery selects both services.
- Add an architecture input to the reusable build workflow, defaulting to both
  native architectures. Only PR validation overrides it to ARM64. Publishing
  callers retain their existing image tags, permissions and complete manifests.

## Outcomes & Retrospective

Implementation and local validation are complete. Focused static tests cannot
establish final production startup, registry availability or browser success;
record the final CI run and any failures before treating external acceptance as
complete. No registry publication or deployment is part of this change.

## Context and Orientation

`.github/workflows/runtime-harness.yml` builds the Compose services from
`docker/docker-compose.runtime-harness.yml`, runs the final-image smoke helper,
then the existing Playwright integration flow. `docker-build-check.yml` owns
extra architecture validation and manual candidate publication.
`build-docker-image.yml` is shared with latest and release publishers.
`scripts/select_docker_checks.py` owns the changed-file selection contract.

The durable policy lives in
[Docker image publication](../../references/docker-image-publication.md) and
[the engineering baseline](../../engineering-baseline.md#cicd-and-release-workflow).

## Plan of Work

Coordinate the runtime Compose and workflow changes, then narrow packaging PR
triggers and select the affected services. Add regression coverage for production
content, deletions, PR diff semantics, fork permissions and publication defaults.
Update the canonical CI policy and generated knowledge inventory. Validate local
gates and use actual PR CI for native Docker and Playwright acceptance.

## Concrete Steps

1. Build/load production API and Web AMD64 images using the Compose bake targets.
2. Smoke-test those tags with `scripts/check_docker_image.py`, recording config
   digests in the existing runtime artifacts directory.
3. Start the integration stack without rebuilding or pulling application images.
4. Select PR ARM64 checks with a dependency-free script; retain manual defaults.
5. Run the focused script tests, actionlint, Compose rendering, architecture and
   repository harness checks, tool doctor and all-files lefthook gate.
6. Commit with the required `Changed:` / `Benefit:` body, push the task branch,
   open a ready PR and read back its workflow results.

## Validation and Acceptance

- Ordinary source, shared i18n and production Markdown trigger runtime checks
  without additional packaging builds; test-only changes stay excluded.
- A service's Dockerfile or runtime dependencies select its ARM64 validation;
  shared packaging machinery selects both. Deleted/renamed inputs and PR merge
  bases are handled, and missing Git history fails rather than skips validation.
- Production smoke tags equal Compose application tags. Browser startup cannot
  silently rebuild or replace them. The Web port and i18n root match nginx and
  the final production filesystem.
- Fork PRs receive no registry secrets or package-write permission. Manual
  validation and latest/release/candidate publication retain both architectures.
- Actual CI must build and smoke both production AMD64 images, start the Compose
  stack and pass `npm run test:e2e -- --project=runtime-harness-smoke`. This
  workflow change must also exercise the selected ARM64 validation jobs.

## Idempotence and Recovery

The selector only reads Git and appends stable machine outputs. Re-running a
workflow builds the same commit with normal layer caches. Existing always-run
Compose cleanup and diagnostic artifacts remain in place. Revert this focused
PR to restore the previous harness and packaging checks; no migration or
deployment is involved.

## Interfaces and Dependencies

The selector emits `run` and `matrix` outputs for the reusable workflow's service
matrix. The reusable image builder gains `architectures`, a JSON array defaulting
to AMD64 and ARM64. Runtime keeps the existing Compose service identities,
Playwright project and timeline schema. No application API, analytics or release
tag contract changes.

---
title: Display the running frontend version
status: active
owner_surface: web
last_reviewed: 2026-10-09
---

# Display the running frontend version

## Purpose / Big Picture

Show the loaded frontend release and source revision at the bottom of the
shared teacher and learner user menu, for example `Version v2.3.3 · a1b2c3d`.
The text is selectable and works in the existing desktop and mobile menus.

## Progress

- [x] 2026-10-10 06:48 CST: Confirmed the approved UI, metadata and analytics contracts; refreshed main and created `sunner/show-running-version`.
- [x] 2026-10-10 06:50 CST: Verified public builds and production Drone use different Dockerfiles; both copy frontend source before the Next build.
- [x] 2026-10-10 06:56 CST: Implemented metadata resolution, build preparation, shared menu and eight translations; 49 focused frontend and 43 packaging/metadata regressions pass.
- [x] 2026-10-10 06:58 CST: Production Next build, 93 frontend regressions, 43 packaging/metadata regressions, full lint, translation and architecture checks pass. Independent review reports no actionable issue.
- [x] 2026-10-10 07:02 CST: Complete repository harness and all-file pre-commit gate pass. Compiled Next config and browser chunks contain the checked-out SHA. Standalone type-check reports only two unchanged main-baseline errors in the operator user-page tests (TS2683 and TS2790).
- [x] 2026-10-10 07:05 CST: Addressed PR #3077 review discussion r4235254200 by including source-marker generation in the installation manual and Web Docker smoke instructions; the shared build guide already describes the same contract.
- [x] 2026-10-10 06:56 CST: Extended Drone preparation for all six environments; readback confirms one marker command with original steps and build/deploy configurations preserved.
- [x] 2026-10-10 07:26 CST: Simulation PR #3079 deployed commit `6002c0108bbdcb9a989470b0b193b1aacca85923` as `sim-6002c01` (build 488); API and Web rollouts completed. The browser menu shows the same SHA on desktop and at 390x844, including Chinese text, selectable 12px styling and no footer overflow.
- [x] 2026-10-10 07:27 CST: Refreshed main and rebased the feature branch for the repository's up-to-date merge rule. Both original commit patches are unchanged; the production PR's first complete CI run passed all applicable checks.
- [ ] Merge through a focused PR and verify domestic and overseas production pages against the deployed source revision.

## Surprises & Discoveries

Production Drone replaces the repository Web Dockerfile with the deployment
repository's Dockerfile and uses `src/web` as its context. That Dockerfile
copies the complete context before `npm run build`. A generated source marker
therefore supports both build paths without changing the deployment Dockerfile.

## Decision Log

- 2026-10-10: Use package metadata for the release and the first seven SHA
  characters for the source revision. These describe the browser's loaded
  frontend bundle; no backend version endpoint or latest-release lookup.
- 2026-10-10: Resolve local Git HEAD first, then a validated `.app-build-sha`
  marker, then an empty revision. Generate the ignored marker anew before
  Docker builds. Keep it included in both Docker contexts.
- 2026-10-10: Record only menu exposure with a surface enum through the shared
  tracker. The canonical contract is in the product-analytics reference.

## Outcomes & Retrospective

Implementation and simulation acceptance are complete. The shared menu in the
simulation browser renders `Version v2.3.3 · 6002c01` on desktop and
`版本 v2.3.3 · 6002c01` at 390x844, matching the deployed source. Production
acceptance remains open until both regional pages match their deployed image.

## Context and Orientation

Teacher and learner routes share `MainMenuModal`. Next configuration owns
build-time constants; `environment.ts` is the browser-safe configuration
interface. GitHub's reusable native-image workflow and runtime Bake workflow
build public images. CICD projects 1, 2, 3, 4, 15 and 17 build main, dev, dev01,
dev02, devus and sim using independent Dockerfiles.

## Plan of Work

Bundle the package version and source SHA, expose them through environment
configuration, and add a passive translated menu footer. Generate a marker
after checkout in both GitHub build entry points and append its generation to
existing Drone preparation without replacing unrelated commands. Validate
the menu and metadata before simulation and production readback.

## Concrete Steps

Run focused menu, environment, build-metadata and tracking tests; run packaging
regressions, translation validation, type checking and lint. Generate knowledge
indexes after staging documentation, validate the repository harness, run the
development-tool doctor and all-file lefthook gate. Push the task branch and
open a ready PR. Validate the simulation build before merging through the PR.

## Validation and Acceptance

- Version text remains visible for guests and authenticated users on both
  surfaces, in desktop/mobile layouts and all supported locales.
- A missing SHA omits the separator. Invalid metadata never becomes displayed
  arbitrary text. Local HEAD takes precedence over a stale marker.
- The marker records the checked-out source, even when an event SHA differs;
  Docker builds contain no Git directory and still bundle the correct value.
- Menu exposure follows the canonical trigger, eligibility, deduplication,
  payload allowlist and fail-open behavior.
- Simulation and both production regions render the source revision actually
  deployed, verified in the browser after deployment readiness.

## Idempotence and Recovery

Overwrite the marker from HEAD on every build; never commit it. Append the
Drone preparation command only if absent and retain all existing project
fields. Read back each updated project. A rollback uses the preceding image;
its bundled version continues to describe that image.

## Interfaces and Dependencies

`NEXT_PUBLIC_APP_VERSION` and `NEXT_PUBLIC_APP_BUILD_SHA` are compiled public
constants consumed as `environment.appVersion` and `environment.appBuildSha`.
They contain only the package version and a validated source revision. No
request, database, dependency, image-name or release-number contract changes.
See [frontend configuration](../../../src/web/src/config/ENVIRONMENT_CONFIG.md),
[image publication](../../references/docker-image-publication.md) and
[product analytics](../../references/frontend-product-analytics.md).

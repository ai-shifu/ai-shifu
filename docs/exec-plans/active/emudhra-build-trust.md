---
title: Repair independent Docker trust stores
status: active
owner_surface: cross-surface
last_reviewed: 2026-10-21
canonical: true
---

# Repair independent Docker trust stores

## Purpose / Big Picture

Future API and Web images must reject the affected eMudhra chains through each
independent TLS trust path while preserving normal HTTPS and application startup.
This change covers this repository's Dockerfiles and dependency pins. The external
domestic build repository has a separate repair; no image publication or deployment
is authorized by this plan.

## Progress

- [x] 2026-10-21 UTC: Inspect Docker stages, package pins, workflow consumers,
  and current final-image smoke tests.
- [x] 2026-10-21 UTC: Upgrade Node and independent OS/Python/pip trust stores;
  regenerate the lockfile with the pinned Node release's npm.
- [x] 2026-10-21 UTC: Add final-runtime trust probes and real-certificate injection
  regression tests; focused tests pass.
- [x] 2026-10-21 UTC: Pass 127 packaging regressions, focused trust tests, Ruff,
  frontend manifest formatting and the strict developer-tool check.
- [ ] 2026-10-21 UTC: Verify complete final production images on native AMD64 and
  ARM64 PR validation, including existing default startup and native-module smoke.

## Surprises & Discoveries

Image tags alone do not update every trust store. The fixed Node image still
ships an older Alpine CA package, and pip vendors a separate certifi bundle.
Docker COPY merges site-packages, so the runner must remove old pip metadata
before receiving the upgraded package and its console scripts.

## Decision Log

- Preserve Python 3.11 image digests and full/slim variants; update CA packages
  in both stages with release-specific Debian minimums.
- Bootstrap pip/certifi from official hash-verified wheels before index access.
- Share one Node 22.23.4 Alpine 3.23 trust stage across builder and runner;
  preserve native build tools, offline pruning, non-root runtime and npm start.
- Test actual runtime CA contents with an ISRG Root X1 positive control and
  exact affected-root fingerprints; keep unaffected emSign roots accepted.

## Outcomes & Retrospective

Implementation and focused offline regressions are present. Complete final-image
acceptance remains a PR build requirement; no publication or rollout is claimed.

## Context and Orientation

[Production base images](../../references/docker-base-images.md) owns the current
image/trust contract. `scripts/check_docker_image.py` runs against final images
in the existing build and runtime workflows, before publication or startup smoke.

## Plan of Work

Update dependency/runtime pins together, enforce safe packages at build time,
then extend existing smoke checks to inspect Python system/certifi/pip and Node
bundled/default/system roots. Keep the current packaging validation workflow.

## Concrete Steps

Use Node 22.23.4's bundled npm to regenerate `src/web/package-lock.json` with
`npm install --package-lock-only --ignore-scripts`. Run the packaging pytest
suite, Ruff, the repository harness, and existing commit hooks. Let native PR
jobs build and smoke the final images without registry publication.

## Validation and Acceptance

Every trust store must include ISRG Root X1 and omit the affected root fingerprints.
Injecting the public affected root into any tested store must fail. API package
installation must retain certifi 2026.10.19 and pip's fixed vendored bundle; final
pip metadata and all console entrypoints must agree on 26.2.2. Existing startup,
FFmpeg, Sharp, SWC, runtime config and shared-i18n checks must continue to pass.

## Idempotence and Recovery

Package-manager upgrades and certificate-store refreshes are repeatable. Missing
fixed packages or an old application certifi pin stop the build. Revert this
focused PR to recover prior build definitions; this work changes no running system.

## Interfaces and Dependencies

No new application dependencies or environment variables are introduced. Builds
need patched Debian/Alpine repositories and hash-matching official PyPI wheels.
The public test PEMs contain certificate data only, with no private keys.

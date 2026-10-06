---
title: Reuse production Web Docker dependencies
status: active
owner_surface: web
last_reviewed: 2026-10-06
canonical: true
---

# Reuse production Web Docker dependencies

## Purpose / Big Picture

Reduce dependency-download failures in production Web image builds. Install the
locked dependencies once on the target architecture, build Next.js with its
normal development toolchain, and prune development dependencies without network
access before copying production dependencies into the final image. Preserve
Node 22.16.0 on Alpine, npm lifecycle scripts during the initial locked
installation, and the `npm start` runtime contract. Native module probes replace
the mutable Sharp installation fallback.

## Progress

- [x] 2026-10-06 UTC: Inspect Docker stages, the package lockfile, Next configuration,
  runtime i18n route, and repository rules.
- [x] 2026-10-06 UTC: Choose offline pruning over changing to the standalone server.
- [x] 2026-10-06 22:15 UTC: Implement production dependency reuse and native-module probes.
- [x] 2026-10-06 22:22 UTC: Verify cold-cache install and offline prune on Node 22.16.0/npm 10.9.2; preserve the lockfile and pass native probes.
- [x] 2026-10-06 22:23 UTC: Pass the strict development-tool doctor, repository harness, formatting, and all-files lefthook checks.
- [x] 2026-10-06 22:35 UTC: Rebase onto the native packaging checks and create ready stacked PR #3018.
- [x] 2026-10-06 22:37 UTC: Remove the mutable Sharp fallback and compare installation/pruning with the original copied lockfile.
- [x] 2026-10-06 22:49 UTC: Pass native Linux AMD64/ARM64 Web dependency probes and API/Web production runner smoke checks for head 596a26e16 in packaging run 37542040314.
- [x] 2026-10-06 23:00 UTC: Rebase only the two dependency commits onto main after the Docker stability foundation merged; preserve its Markdown packaging triggers.
- [ ] 2026-10-06 23:00 UTC: Complete the final main-based PR head CI and live review checks before merge.

## Surprises & Discoveries

The Next configuration enables standalone output, but the Docker image uses
`npm start` with the complete `.next` directory. Changing the runtime entrypoint
would add tracing and asset-layout risks unrelated to dependency network errors.
The builder already configures finite npm fetch retries and timeouts; the runner
performs a second clean production installation without those settings. The
local machine has no Docker CLI, so native Linux acceptance must run in CI.
Real npm 10.9.2 validation found that prune recalculates React peer metadata and
needs the cache created by the initial installation. Clearing that cache before
pruning causes ENOTCACHED; default prune also rewrites lockfile development flags.
Use `--save=false` and delay cache cleanup until after the offline prune.
The existing `npm install sharp` fallback could mutate the lock before a prune
snapshot; comparing only against that snapshot would miss the drift. Sharp
0.35.4 declares locked native optional packages, including both Linux musl
architectures, and has no install lifecycle script. Use the initial locked
installation and actual native probes; do not resolve a new Sharp version.

## Decision Log

- 2026-10-06: Derive a production-dependencies stage from the completed builder
  and prune with `--omit=dev --offline --ignore-scripts --no-audit --no-fund --save=false`.
  Initial `npm ci` still executes package lifecycle scripts. The pruning stage
  must preserve the lockfile byte for byte and never fetch or rerun scripts.
  Keep the original npm installation cache until pruning finishes, then remove
  it before copying only node_modules to the runner.
- 2026-10-06: Snapshot the source lock before npm ci and compare against that
  same snapshot after initial installation and pruning. Remove npm rebuild and
  the mutable npm install Sharp fallback; native probe failure stops the build.
- 2026-10-06: Keep the same base image, architecture, runtime startup command,
  translations, public files, and Next output layout. Native modules are copied
  only between stages within one target-platform build.
- 2026-10-06: Probe actual Sharp image conversion, native SWC transformation,
  retained production roots, removed development-only roots, and locale JSON
  after pruning. Copy the probe into the runner for use by CI or diagnostics.

## Outcomes & Retrospective

The Dockerfile now installs dependencies once and copies the offline-pruned
production tree into the runner. Fresh-cache Node 22.16.0/npm 10.9.2 installation
followed by offline pruning passed with unreachable HTTP/HTTPS proxies; the
lockfile remained byte-identical and production root versions matched the lock.
The probe passed actual Sharp resize/PNG decode, native SWC transformation and
execution, and all eight locale JSON reads. Negative checks confirmed that a
retained Jest directory or missing native SWC binary fails the probe.

Strict tooling, the repository harness, and all-files lefthook passed.
[Packaging run 37542040314](https://github.com/ai-shifu/ai-shifu/actions/runs/37542040314)
passed both native Linux musl Web builds and dependency probes, plus all four
API/Web AMD64/ARM64 final runner smoke checks for head 596a26e16. The main-based
rebased head must repeat CI acceptance before merge; local Darwin results alone
cannot establish Linux native behavior or container startup. This change does not
claim to fix npm network failures during the initial installation or the
separately investigated QEMU illegal-instruction failure.

## Context and Orientation

`src/web/Dockerfile` installs dependencies, builds Next.js, and currently installs
production dependencies again in the runner. `src/web/package-lock.json` owns
resolved versions and platform-specific optional dependencies.
`src/web/next.config.ts` enables standalone output without changing the current
runtime contract. `src/web/src/app/api/i18n/route.ts` loads shared JSON files from
`I18N_ROOT`; the final image must keep `/app/i18n`.

## Plan of Work

Add the derived pruning stage after the existing builder. Copy its node_modules
into the runner and remove the runner installation. Add a dependency and locale
probe under `src/web/scripts/` and run it after pruning. Document image builds
and smoke commands in the Web README. Do not change release orchestration,
Node versions, npm package versions, lockfile resolution, or app behavior.

## Concrete Steps

From the repository root, build the image with
`docker build --platform linux/amd64 -f src/web/Dockerfile -t ai-shifu-web:deps .`.
Repeat on native ARM64 with `--platform linux/arm64`. On each final image run
`docker run --rm --network none --entrypoint node ai-shifu-web:deps scripts/check-production-dependencies.mjs`.
Start the default command and check `/api/config`,
`/api/i18n?lng=en-US&ns=common.core`, and a built `/_next/static` asset. The
independent Docker stability workflow provides native-platform smoke execution.

For local dependency checks, use Node 22.16.0 and npm bundled with that release;
run `npm ci` before pruning in an isolated manifest-only directory. Snapshot the
lockfile, start the initial installation with a fresh npm cache, reuse that cache
for the offline prune with an unreachable proxy, compare the lockfile, and
run the probe with `I18N_ROOT` pointing to shared repository translations. A
local Darwin result confirms dependency pruning behavior only, not Linux musl
binaries or final container startup.

## Validation and Acceptance

Acceptance requires both native Linux architectures to build and start the final
runner with the default command as the unprivileged node user. The probe must
execute native Sharp and native SWC, resolve all production dependency roots,
reject development-only roots, and read every declared locale's common JSON.
The lockfile must match the source copy after both installation and pruning. Pruning must also succeed
using only the cache created by the first cold-cache installation, with network
access disabled by BuildKit's `RUN --network=none`. Runtime configuration,
translation responses, and static assets must remain available. Repository
harness, formatting, and all-files lefthook checks must pass before commit.

## Idempotence and Recovery

Rebuilds are safe: every production dependency stage starts from the builder's
locked dependency tree. Failure during offline pruning or the probe stops the
build before the final image is produced. Reverting the Dockerfile restores the
previous runner installation; no database, secrets, or deployed tags change.

## Interfaces and Dependencies

The runtime interface stays `npm start`, port 3000 by default, and
`I18N_ROOT=/app/i18n`. The probe resolves dependencies from the current working
directory's package.json, so CI can also bind-mount it outside `/app` and invoke
it with `/app` as the working directory. It requires only built-in Node modules
plus the production dependencies already declared by the application.

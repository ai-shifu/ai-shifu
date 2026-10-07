# Main Docker build failures: evidence and repair strategy

## Purpose / Big Picture

Make main and release Docker packaging reliable for API/Web on AMD64 and
ARM64, and distinguish compilation failures from registry publication failures.
This document records the 2026-10-07 investigation and proposed acceptance work.
The requested analysis is complete. The user approved implementing this
strategy on 2026-10-07; the current implementation record is the existing
[PR #3015](https://github.com/ai-shifu/ai-shifu/pull/3015) and its
`docker-build-stability.md` plan instead of creating another native-build
implementation. That plan owns implementation progress and acceptance.

## Progress

- [x] 2026-10-06 22:00 UTC: Verified main at
  `d88ab7e0e5d58c2663339551eba2dbdc54ea8672` and inspected production Dockerfiles,
  latest/release workflows, and the runtime harness.
- [x] 2026-10-06 22:00 UTC: Retrieved all 255 final-failure records exposed by
  the latest-image workflow API, from November 2025 through October 2026.
- [x] 2026-10-06 22:00 UTC: Read all 21 final-failure logs for runs created
  since 2026-09-01 UTC, plus failed attempt 1 of a successful October rerun.
- [x] 2026-10-06 22:00 UTC: Reviewed 36 July/August historical samples and
  verified the registry compatibility repair in PR #2667.
- [x] 2026-10-06 22:00 UTC: Read PR #3015, its live checks, and native build logs;
  designed prioritized repairs and observable acceptance criteria.
- [x] 2026-10-06 22:01 UTC: Verified this report's required ExecPlan sections
  and whitespace; the repository harness passed. The new report is uncommitted
  and will enter generated knowledge indexes when integrated into the existing
  implementation plan.
- [x] 2026-10-06 22:30 UTC: User approved implementation. Continued #3015 and
  integrated this evidence into its native-build stability plan.
- [ ] Follow-up implementation: finish native-build acceptance through #3015.
- [ ] Follow-up implementation: address dependency-network resilience and
  complete-production-image smoke coverage in focused changes.
- [ ] Follow-up implementation: address latest publication ordering and
  release-descriptor consistency in a separate focused change.

## Surprises & Discoveries

### Coverage and counting

The API exposes 255 latest-workflow runs whose final conclusion is failure.
Monthly counts use the run creation date in UTC; July has 15, August 134,
September 20, and October 1. These metadata counts are not error-class counts.
Older logs may have expired, and successful reruns disappear from the final
failure query. This is not an exhaustive classification of every historical
attempt.

For runs created since September 1 UTC, there are 224 latest-workflow runs:
197 success, 21 failure, 5 cancelled, and 1 in progress at inspection. The 21
final failures were all read: 17 ARM64 SIGILL, 3 npm network errors, and 1 Aliyun
OAuth TLS timeout. Run 37401758132 additionally failed with SIGILL on attempt 1
before succeeding on attempt 2. Run 35355457934's first attempt was cancelled,
not a further build failure. The recent 100-run subset has 93 success, 6 failure,
and 1 in progress; do not infer a long-term failure rate from that subset.

The July/August sample contains 36 runs: 33 readable failed logs, 2 expired
logs (HTTP 410), and 1 successful control. Of the failed samples, 21 contain
Aliyun OCI rejection and 13 contain SIGILL; one contains both. The sample also
includes release builds. Counts overlap and are not population estimates.

### Confirmed error classes

| Error class | Evidence | Cause and present status |
| --- | --- | --- |
| Web ARM64 SIGILL / exit 132 | [October 6 failure](https://github.com/ai-shifu/ai-shifu/actions/runs/37401073103), [September 23 failure](https://github.com/ai-shifu/ai-shifu/actions/runs/35846733590), [July 11 failure](https://github.com/ai-shifu/ai-shifu/actions/runs/29170223973) | QEMU reports target signal 4 in `linux/arm64 builder 4/7` after APK succeeds. The combined Node/npm RUN prevents identifying the exact crashing command. Repeated across unrelated commits; still present in main's build design. |
| npm network failure | [September 13](https://github.com/ai-shifu/ai-shifu/actions/runs/34756880722), [September 16](https://github.com/ai-shifu/ai-shifu/actions/runs/35044488675), [September 21](https://github.com/ai-shifu/ai-shifu/actions/runs/35563287947) | ETIMEDOUT during builder dependency download; ECONNRESET in the runner's second production `npm ci`. Distinct from SIGILL. Builder retry configuration is not inherited by the independent runner stage. |
| Aliyun OAuth TLS timeout | [September 22](https://github.com/ai-shifu/ai-shifu/actions/runs/35674825107) | API built, then push could not fetch the OAuth token because of a TLS handshake timeout. This log does not demonstrate invalid credentials. |
| Aliyun OCI attestation rejection | [August 13 main](https://github.com/ai-shifu/ai-shifu/actions/runs/31679804814), [v2.2.11 release](https://github.com/ai-shifu/ai-shifu/actions/runs/31764938354), [v2.2.12 release](https://github.com/ai-shifu/ai-shifu/actions/runs/32454270690) | Registry rejects `application/vnd.oci.empty.v1+json` after image build. Repaired by [PR #2667](https://github.com/ai-shifu/ai-shifu/pull/2667), merged August 26, which disables provenance/SBOM attestations in both workflows. |

The OCI failure has an independent environmental trigger. The August 7
[successful release](https://github.com/ai-shifu/ai-shifu/actions/runs/31161987620)
used BuildKit 0.31.2; August 13 failing builds used 0.32.2, both fetched through
the floating `moby/buildkit:buildx-stable-1` tag.
[BuildKit 0.32.0](https://github.com/moby/buildkit/releases/tag/v0.32.0)
changed attestations to OCI artifact descriptors by default, and the
[attestation format](https://github.com/moby/buildkit/blob/master/docs/attestations/attestation-storage.md)
uses the rejected empty JSON descriptor. The version transition, upstream
change, matching media type, and successful post-fix
[run 32938234710](https://github.com/ai-shifu/ai-shifu/actions/runs/32938234710)
strongly support this compatibility explanation. Keep the current compatible
settings; do not treat this repaired incident as current SIGILL.

### SIGILL evidence boundaries

The October 6 failure used Node `22.16.0-alpine`, QEMU 10.2.3 and BuildKit
0.33.1. APK completed before the crash. No command-level marker establishes
whether `npm config`, `npm ci`, an installation script, Sharp rebuild, or
another process crashed. The lockfile contains ARM64 musl Sharp/libvips
optional packages, so missing Sharp packages are not established either.

The same application commit in
[run 37401758132 attempt 1](https://github.com/ai-shifu/ai-shifu/actions/runs/37401758132/attempts/1)
failed and
[attempt 2](https://github.com/ai-shifu/ai-shifu/actions/runs/37401758132/attempts/2)
succeeded. Attempt 2 executed the ARM64 dependency stage (about 14 minutes)
and Next build (about 25 minutes); it was not merely an entirely cached
success. This supports intermittent execution/environmental failure rather
than a deterministic dependency incompatibility, without proving a QEMU bug.
SIGILL predates the recent dependency updates by months.

API and Web share the implicit GHA scope `buildkit` in main. Docker documents
that different image builds overwrite this cache scope. This can reduce cache
reuse and force slow cold builds. It does not prove cross-architecture
contamination or explain SIGILL.

## Decision Log

- Prefer native ARM64 execution over simultaneous Node, libc, dependency, and
  cache changes. Preserve application inputs initially and compare outcomes.
  [Docker](https://docs.docker.com/build/building/multi-platform/) recommends
  native nodes for complicated builds; [GitHub](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
  provides `ubuntu-24.04-arm` for this public repository.
- Reuse #3015, which already supplies native platform jobs and diagnostics.
  Successful build-only CI is evidence for packaging, not registry acceptance.
- Keep SIGILL, npm download, TLS transport, and OCI compatibility as separate
  failure classes with separate remedies.
- Separate service/platform cache scopes, using the
  [documented cache contract](https://docs.docker.com/build/cache/backends/gha/).
  Share latest/release cache only for the same service, architecture and inputs.
- Do not retry complete builds indiscriminately. Limit retries to identified
  transport failures with a bounded attempt count and backoff; fail immediately
  for SIGILL, dependency resolution, tests, authorization denial, and unsupported
  manifest types.
- Avoid a cross-service/cross-registry atomicity claim. Docker registries do not
  provide a transaction spanning all tags. Deploy from a verified build
  descriptor containing immutable API/Web digests; treat `latest` as an alias.

## Outcomes & Retrospective

Diagnosis and design are complete. Main still uses the old QEMU workflow.
#3015 is open and draft at `a2ab9a0958d244b58608a1688467e5232d646d4f`.
Its [packaging run](https://github.com/ai-shifu/ai-shifu/actions/runs/37423039312)
completed on its first attempt for all four API/Web × AMD64/ARM64 combinations.
Logs have no `CACHED` steps and execute actual dependency installs and builds.
Native ARM64 Web installation took about 1.5 minutes and Next build about
1.7 minutes; this one-run comparison is encouraging, not a performance SLA.
All registry logins and manifest publication were skipped, as intended.
The separately verified [runtime smoke](https://github.com/ai-shifu/ai-shifu/actions/runs/37423039004)
passed, but uses the harness Dockerfile, not the production Web runner.

Main run 37536833840 subsequently completed successfully for both services. A latest tag or green Web job alone does not prove the
entire packaging workflow succeeded or that intermittent failure is repaired.

## Context and Orientation

Main's `.github/workflows/build-latest.yml` and `build-on-release.yml` run on
x64 `ubuntu-latest`, configure QEMU, and build both platforms in one Buildx
step per service. Each service directly publishes its own tags to Docker Hub
and Aliyun. `src/web/Dockerfile` contains a large combined builder dependency
RUN and a second runner production installation. `next.config.ts` already
enables standalone output, but the Dockerfile still starts with `npm start`.

#3015 introduces `.github/workflows/build-docker-image.yml`, shared metadata,
native architecture jobs, per-service/platform caches, digest artifacts and
`scripts/merge_docker_manifests.py`. Its scope is packaging stability. The
following existing risks remain outside its implemented scope:

- Build-only output is `type=cacheonly`; there is no production-image container
  startup/HTTP smoke.
- PR packaging path filters omit application code, package locks,
  requirements and shared i18n. The production image can change without
  triggering that check.
- Non-main `workflow_dispatch` still has no guard against writing `latest`.
- API/Web publish independently, and workflow runs have no publication
  concurrency/ordering guard.
- Digest-only publication and final manifest writes have not been validated
  against both registries. `imagetools create --dry-run` cannot prove final
  registry write compatibility.

## Plan of Work

1. **P1, native packaging:** continue #3015 acceptance. Confirm both cold and
   warm builds, preserve #2667 compatibility flags, and exercise candidate
   digest/index publication to both registries using isolated tags. Carry
   successful platform digests across failed-job-only reruns of the same run;
   fail closed if required artifacts expire. Keep runtime versions unchanged.
2. **P1, production verification:** export/load each local single-platform
   production image for smoke tests before publication. Trigger relevant
   production checks for application, lockfile, requirements, shared i18n,
   Dockerfile, dockerignore, and workflow changes. Reuse the existing browser
   harness for business paths while adding tests of the actual production
   runner, including its non-root startup and static/i18n resources.
3. **P2, network resilience:** initially apply bounded npm settings to every
   installation stage. In a separate image change, remove runner redownload
   by copying correctly pruned same-platform production dependencies or using
   existing standalone output. Validate Sharp/SWC and dynamic file tracing;
   do not copy AMD64 native modules into ARM64. Test whether the unversioned
   Sharp fallback is necessary before replacing it with a frozen-lock install
   and a real Sharp load/image-processing probe.
4. **P2, publication ordering:** restrict latest promotion to main. Give all
   services/architectures a shared success barrier and serialize promotions.
   Reject stale runs before promotion; produce a descriptor containing source
   SHA, per-service manifests, per-platform digests and registry readbacks.
   Deploy from that descriptor. Record and recover partial tag updates rather
   than presenting them as successful all-service publication.
5. **P2, repeatability:** pin the tested BuildKit version and base-image
   digests, with an explicit update process. This addresses proven historical
   build-environment drift without assuming floating tags caused current SIGILL.

## Concrete Steps

For deeper SIGILL diagnosis, use one source SHA and pin the historical Node
index digest
`sha256:41e4389f3d988d2ed55392df4db1420ad048ae53324a8e2b7c6d19508288107e`.
For a QEMU control, pin binfmt digest
`sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0`
and record BuildKit/QEMU versions. Compare AMD64 native, ARM64 QEMU and ARM64
native with cold caches. Split/log Node startup, npm startup, APK, npm config,
`npm ci --foreground-scripts`, Sharp probing and Next build. Repeated cold
builds are needed to investigate an intermittent error. If native ARM64 also
fails, try same-Node Debian as a controlled libc comparison; if only QEMU
fails, investigate emulator versions/instruction behavior. Disabling install
scripts is a diagnostic control, not a verified production remedy.

Before continuing implementation, update #3015 against main and read its
current review threads. Keep packaging, network/download and promotion-policy
changes focused. Run focused manifest regression tests and actionlint, then
the required repository harness and architecture checks. Preserve release
tag semantics and check Compose consumers as required by `.github/AGENTS.md`
and `docker/AGENTS.md`. Use the existing task branch -> tests -> commit -> PR
workflow. The approved implementation includes isolated candidate publication;
application deployment remains separate.

## Validation and Acceptance

- Both services build and start on native AMD64 and ARM64 with cold and warm
  caches; record exact SHA, image/tool digests, platform and terminal outcomes.
- Manifest lists contain exactly the two supported platform images. Verify
  revision and digests by reading from both registries, then pull/run each
  native image. Test a candidate tag before any `latest` change.
- Verify Web HTTP entry, static assets, runtime config/i18n and Sharp; verify
  API startup/imports, Gunicorn/Celery/Flask and FFmpeg in the final image.
- Build-only PR checks execute no registry login, digest push or tag writes.
- A failed architecture prevents that service's publication; global promotion
  additionally waits for every required service. Expired/missing digest
  artifacts fail closed. Test failed-job-only reruns and partial registry writes.
- Non-main dispatch cannot write latest. An older run/rerun cannot overwrite
  an accepted newer release descriptor. Test ordering at promotion boundaries.
- Simulated transient npm/TLS errors exercise bounded retries; permanent
  resolution, authorization, OCI or SIGILL errors remain failures.
- Dependency, shared i18n and production-Dockerfile changes trigger the relevant
  packaging checks. Existing Playwright and repository checks remain green.

## Idempotence and Recovery

Keep candidate SHA/digest outputs immutable. Retry publication from verified
digests without rebuilding application inputs when possible. Record previous
alias targets and each completed write. A partial registry/alias promotion
must leave the accepted release descriptor unchanged and expose a failed
status; restore aliases or resume the same verified promotion explicitly.
Preserve compatible provenance/SBOM settings. Revert a packaging change through
its PR if required; application/dependency rollback is not justified by the
existing SIGILL evidence alone.

## Interfaces and Dependencies

Continue existing Docker actions, registry secrets/vars, GitHub artifact
handoff, Buildx and the Python manifest helper introduced by #3015. Use native
runner labels and [Docker's matrix/digest merge pattern](https://docs.docker.com/build/ci/github-actions/multi-platform/).
Keep existing image names, supported platforms and release tags. Standalone
startup, a global promotion barrier and release descriptors are separate
contracts that need their own consumer and compatibility validation before
changing deployment behavior.

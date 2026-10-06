# Docker build stability with native platform runners

## Purpose / Big Picture

Make API/Web packaging reliable on AMD64 and ARM64, execute the final production
images before publication, and verify that registry content matches the tested
images. Remove QEMU from this path, separate cache writers, and fix the tested
BuildKit version. Preserve image names, release tags, compatible provenance/SBOM
settings, and application behavior.

The user approved implementing the repair strategy on 2026-10-07, superseding
this plan's earlier draft-only scope. Continue PR #3015. Dependency reuse and
global publication ordering remain separate focused PRs. Deployment is not part
of this repair.

## Progress

- [x] 2026-10-06 UTC: Inspected main fc75185aa and created an isolated worktree;
  copied ignored local environment files without starting services.
- [x] 2026-10-06 UTC: Verified ARM64 QEMU SIGILL/exit 132 in attempt 1 of
  run 37401758132; the exact crashing subprocess remains unconfirmed.
- [x] 2026-10-06 UTC: Added native architecture builds, separate cache scopes,
  attempt-aware digest handoff, manifest preflight, and diagnostics.
- [x] 2026-10-06 UTC: Nine manifest tests, metadata checks, pinned Ruff,
  actionlint, YAML and the repository harness passed.
- [x] 2026-10-06 UTC: PR #3015's original build-only run 37423039312 passed
  actual uncached builds for all four service/platform combinations.
- [x] 2026-10-06 22:30 UTC: User approved the full repair strategy. Refreshed
  main and verified that #3015 has no outstanding review threads.
- [x] 2026-10-06 22:30 UTC: Added production-image startup/HTTP/native-module
  smoke checks, tested-content verification, relevant application path filters,
  BuildKit v0.33.1 pin, and an isolated candidate-publication dispatch.
- [x] 2026-10-06 22:30 UTC: Local fixture API starts and returns a healthy
  JSON envelope without production services or credentials; 19 script tests pass.
- [ ] External acceptance: run the updated production smoke on native Linux
  AMD64 and ARM64, then repeat using warm caches.
- [ ] External acceptance: publish isolated candidates to each configured
  registry and verify both platform manifests and tested content.
- [ ] External acceptance: validate partial reruns together with the separate
  global-publication change before completing the repair.

## Surprises & Discoveries

- API/Web shared implicit GHA scope `buildkit`, allowing cache replacement by
  another image. This hazard does not establish the SIGILL cause.
- APK completed before the combined Node/npm stage failed. Attempt 2 succeeded;
  no low-level QEMU or dependency root-cause claim is made.
- SunMac has no Docker CLI/daemon, so Linux image acceptance requires CI.
- Failed-job-only reruns retain successful digests from earlier attempts of the
  same run. Expired/missing artifacts must fail closed.
- Flask health returns a JSON body without the test client's JSON content-type
  recognition. Smoke parses the response bytes and validates the business
  envelope rather than treating HTTP 200 alone as healthy.
- Docker's load and registry exporters can produce different manifest digests.
  Compare the immutable config digest, which also identifies the filesystem
  diff IDs, before allowing publication artifacts to become available.

## Decision Log

- Build AMD64 on `ubuntu-24.04` and ARM64 on `ubuntu-24.04-arm`; assert host
  architecture. Keep npm lifecycle scripts and runtime versions.
- Use `ai-shifu-<service>-<arch>` cache scopes. Pin the observed successful
  BuildKit version `moby/buildkit:v0.33.1`; preserve `provenance: false` and
  `sbom: false` for Aliyun compatibility.
- Follow Docker's test-before-push pattern: load a final single-platform image,
  run smoke, then export the same builder's cached layers by digest. Read each
  registry's config digest and require equality with the tested local image.
- API smoke starts the default Gunicorn command with fake credentials, a local
  SQLite URI, disabled Redis, and memory-only Celery settings. It checks native
  Python imports, FFmpeg/Celery binaries and the health envelope. Web smoke
  requires non-root startup, Sharp/SWC, runtime API config, shared translations,
  public assets, rendered login HTML and a compiled static asset.
- PR checks receive no registry secrets. Explicit candidate dispatch requires
  configured registry credentials and uses only run/attempt-specific tags.
- Keep the network/download repair and global latest barrier in independent
  PRs; their acceptance uses the native production-image checks introduced here.

## Outcomes & Retrospective

The original native builds passed. Production-image smoke and tested-content
verification are implemented with focused local regression coverage. Updated
Linux smoke, warm-cache runs and actual registry acceptance remain open; a green
build-only run does not establish registry compatibility or deployment success.

## Context and Orientation

Latest/release callers invoke `.github/workflows/build-docker-image.yml` per
service. `.github/actions/docker-image-metadata/action.yml` resolves registry
credentials inside each job. `scripts/check_docker_image.py` runs the final image
and compares its config to the digest exported to each registry.
`scripts/merge_docker_manifests.py` checks both platform digests, preflights
all destinations, publishes, and verifies final tags. PR and isolated candidate
checks use `.github/workflows/docker-build-check.yml`.

The [investigation](docker-build-failure-analysis.md) records log coverage and
cause boundaries. Evidence includes the
[failed QEMU attempt](https://github.com/ai-shifu/ai-shifu/actions/runs/37401758132/attempts/1),
[successful rerun](https://github.com/ai-shifu/ai-shifu/actions/runs/37401758132/attempts/2),
[native packaging check](https://github.com/ai-shifu/ai-shifu/actions/runs/37423039312),
[native runner guidance](https://docs.docker.com/build/ci/github-actions/multi-platform/),
[cache scope behavior](https://docs.docker.com/build/cache/backends/gha/), and
[test-before-push guidance](https://docs.docker.com/build/ci/github-actions/test-before-push/).

## Plan of Work

Complete #3015 with production-image smoke, fixed build inputs and broader path
filters. Validate actual native images through CI. Keep Web production dependency
reuse and serialized all-service publication as focused dependent PRs, then use
isolated candidate tags for real registry acceptance before latest promotion.

## Concrete Steps

Run both script test modules, pinned Ruff, actionlint on packaging workflows,
YAML, strict development-tool checks, the repository harness and architecture
checks. Stage plans before regenerating knowledge indexes. Run the all-files
lefthook gate before committing. Update #3015's title/description and mark it
ready. Record the exact tested head SHA and terminal native-job outcomes.

## Validation and Acceptance

Both production services must start and serve validated responses on native
Linux AMD64 and ARM64. A missing translation, unhealthy HTTP-200 envelope,
wrong architecture, native-module failure or differing pushed config fails the
job before successful digest handoff. Build-only PR jobs cannot log in or push.
Cold/warm runs and actual candidate writes must be observed; manifests must
contain exactly the two supported platforms. Combine this with publication
ordering tests and failed-job-only reruns before declaring the full repair done.

## Idempotence and Recovery

Artifact names include service, architecture and attempt; merge chooses the
highest successful attempt per platform in the same run. Architecture jobs move
no final tags. Container cleanup runs after successful or failed HTTP smoke.
A registry failure can leave digest-only candidates, but no successful handoff.
If final tag writes partially fail, registries may temporarily differ; use the
separate publication descriptor/status contract to inspect and resume safely.
Revert a packaging change through a PR if needed.

## Interfaces and Dependencies

Use existing Docker actions and registry secrets/vars, GitHub artifacts, Python
standard-library smoke/manifest helpers, and existing pytest. Native ARM runners
must remain available. No application API or deployment contract changes are
required by this foundational PR.

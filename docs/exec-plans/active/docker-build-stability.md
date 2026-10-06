# Docker build stability with native platform runners

## Purpose / Big Picture

Improve latest/release API and web packaging by removing QEMU from the build
path and separating competing cache writers. Preserve triggers, image names,
tag rules, registry configuration, dependency checks, and application behavior.
This task delivers an independent draft PR after explicit approval. It does not
publish images, deploy, or merge.

## Progress

- [x] 2026-10-06 UTC: Inspected current main fc75185aa and created an isolated
  worktree; copied ignored local environment files without starting services.
- [x] 2026-10-06 UTC: Verified attempt 1 of run 37401758132 logged ARM64 QEMU
  illegal instruction / exit 132 in the combined npm layer.
- [x] 2026-10-06 UTC: Implemented native builds, separate caches, digest handoff,
  manifest preflight, and runtime diagnostics.
- [x] 2026-10-06 UTC: Passed nine manifest regression tests, eight registry/push
  mode checks, pinned Ruff, actionlint, YAML checks, and the repository harness.
- [x] 2026-10-06 UTC: User approved an independent draft PR and no-push CI
  validation. Added packaging-only PR checks using native runners and no registry
  secrets; publishing remains disabled in these checks.
- [ ] External acceptance: finish native Linux build-only PR checks.
- [ ] External acceptance: warm-cache runs, registry manifests, and partial
  publication reruns. Image publication remains outside this task's authorization.

## Surprises & Discoveries

- API/web shared implicit GHA scope `buildkit`, allowing cache replacement by
  another image. This configuration hazard does not establish the SIGILL cause.
- APK completed before the combined Node/npm stage failed. The exact crashing
  command is unconfirmed; attempt 2 succeeded. No low-level root cause is claimed.
- SunMac has no Docker CLI/daemon, so local validation cannot prove Linux
  image builds or registry compatibility.
- OneDrive repeatedly changed executable bits in the new worktree. Moved this
  isolated worktree to `/tmp/ai-shifu-docker-stability-20261006` and restored modes
  from Git; the source checkout stayed unchanged.
- Failed-job-only reruns require retaining successful digests from earlier
  attempts of the same run. Expired/missing artifacts must fail closed.

## Decision Log

- Build amd64 on `ubuntu-24.04` and arm64 on `ubuntu-24.04-arm`; assert the host
  architecture before building. No QEMU setup or whole-build retries. Building
  web solely on BUILDPLATFORM could produce native dependencies for the wrong
  target architecture.
- Use `ai-shifu-<service>-<arch>` cache scopes. Latest and release reuse the same
  service/platform layers; cache errors remain visible.
- Publish untagged digest images per architecture, then move tags only after
  both jobs succeed and all registry destinations pass manifest preflight.
- Latest can fall back to build-only when credentials are missing; release
  publication fails closed without a configured registry. Resolve
  metadata/credentials within each job using a shared composite action;
  avoid secret-derived cross-job outputs, which GitHub may suppress.
- Keep existing npm network settings and sharp fallback. Split RUN stages and
  log Node/npm/architecture without changing versions or disabling npm ci.

## Outcomes & Retrospective

Implementation is ready for an independent draft PR. No measured success-rate or
proven low-level root-cause claim is made before external CI acceptance.

## Context and Orientation

Latest/release callers invoke `.github/workflows/build-docker-image.yml` per
service. `.github/actions/docker-image-metadata/action.yml` resolves configured
registries in each job. `scripts/merge_docker_manifests.py` checks both platform
digests, preflights every destination, publishes, and verifies each final tag.
`src/web/Dockerfile` still executes the same dependency/sharp/Next build steps.

Evidence: [failed job](https://github.com/ai-shifu/ai-shifu/actions/runs/37401758132/job/112070289609),
[successful rerun](https://github.com/ai-shifu/ai-shifu/actions/runs/37401758132/attempts/2),
[native runner guidance](https://docs.docker.com/build/ci/github-actions/multi-platform/),
[cache scope behavior](https://docs.docker.com/build/cache/backends/gha/),
and [digest publication](https://docs.docker.com/build/exporters/image-registry/).

## Plan of Work

Share native build/publication code between latest/release, test fail-closed
publication and partial reruns, validate YAML/actions/scripts, and document
external acceptance. The separate workflow simplification task owns trigger
changes; this task preserves `on` and release draft/prerelease gating.

## Concrete Steps

Run the focused manifest tests, Ruff, actionlint on all three packaging
workflows, check-yaml on the workflows/composite action, and the repository
harness after staging this plan and regenerating knowledge indexes. Review the
diff against fc75185aa and ensure the source checkout is unchanged.

## Validation and Acceptance

Local coverage must prove missing platforms, bad digests/manifests, and registry
errors prevent successful publication; partial reruns select the newest digest
per platform within this run. Every native job builds exactly one platform with
matching cache import/export scope. External acceptance requires cold and warm
builds, no registry writes in build-only mode, correct two-platform manifests
in both configured registries, and latest/release/partial-rerun validation.

## Idempotence and Recovery

Digest artifact names contain service, architecture, and attempt; the merge
selects each platform's highest attempt. No architecture job moves final tags.
If a later registry/tag write fails, different destinations can temporarily
reference different complete manifests: registries do not share a transaction.
Inspect the error before rerunning publication. Expired digests require
rerunning native builds. Reverting this change restores prior packaging; local
edits have no deployment side effects.

## Interfaces and Dependencies

Keep existing Docker actions and secrets. Use GitHub artifact upload/download
for platform/digest JSON records, Python standard library and Buildx imagetools
for merging, and existing development pytest for tests. ARM native runners must
be available for the public repository. No application contract or persistent
access changes are required.

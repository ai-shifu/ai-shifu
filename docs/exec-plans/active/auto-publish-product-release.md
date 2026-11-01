# Automatic product Release publication

## Purpose / Big Picture

Make the human merge of a version-update PR sufficient to finish a product
Release. The coordinator freezes that exact commit, verifies its version and
merged-PR provenance, stages a draft/tag, waits for verified API and Web images
on both native architectures, then publishes and reads back the Release.
Failures remain recoverable from the original source after main advances.

This work follows the merged skills release design while preserving the product's
image verification and production boundaries. Implementation, tests,
documentation and an unmerged PR are in scope. A real release, remote tag write,
registry publication, merge, auto-merge, deployment or repository settings change
is outside this execution task. The canonical operational contract lives in
[Docker image publication](../../references/docker-image-publication.md#pr-first-release-gates).

## Progress

- [x] 2026-11-01 01:36 UTC: Read repository, script and workflow instructions,
  current release helpers, image verification path and canonical references.
- [x] 2026-11-01 01:36 UTC: Chose pre-publication image verification, exact-source
  recovery and source-specific completion metadata for legacy-event deduplication.
- [x] 2026-11-01 01:36 UTC: Updated canonical release guidance and the engineering
  baseline; linked the superseded manual-Publish execution history.
- [x] 2026-11-01 01:49 UTC: Implemented the coordinator, exact-source helper
  commands, reusable image integration and bump-title handoff; focused helper
  and workflow tests passed. Independent review found and verified the fix for
  draft metadata visibility permissions.
- [x] 2026-11-01 03:25 UTC: Regenerated knowledge indexes; passed 52 release
  regressions, 391 script tests and 229 subtests (8 Docker Compose cases skipped),
  Ruff, actionlint, architecture fixtures, tool doctor and repository-wide
  lefthook checks in a clean staged snapshot.
- [x] 2026-11-01 03:27 UTC: Opened ready [PR #3276](https://github.com/ai-shifu/ai-shifu/pull/3276)
  with local verification evidence; leave it unmerged. Remote CI is pending.
- [ ] 2026-11-01 01:49 UTC: External acceptance: after authorized review/merge and a genuine version
  PR, verify the actual images, public Release and consumer startup separately.

## Surprises & Discoveries

- The current product path creates a draft after merge, but image builds begin
  only after a separate human Publish action. Removing that extra action alone
  would still allow a public Release to precede failed or missing images.
- Draft/release writes can require the existing workflow-capable PAT when the
  frozen target differs from current default-branch workflows. A PAT publication
  emits `release.published`; token event suppression alone cannot prevent a
  duplicate image build.
- A reusable release image call from main would enable the old default-branch
  `latest` tag expression. Formal release calls must emit only their version
  tag, including historical-source recovery.
- The repository now owns one Web npm package. Version preparation still covers
  its manifest/lock root, the vendored engine version and pinned first-party
  Compose images; it must not restore removed frontend package surfaces.

## Decision Log

- Keep manual human PR merge as the publication authorization gate. Never merge
  or enable auto-merge from preparation or implementation tools.
- Reuse the existing native image workflow for API/Web and AMD64/ARM64. Its
  production startup smoke, pushed-content digest and manifest readback checks
  must succeed before the coordinator publishes the Release.
- Preserve the legacy published-release entry point. The publisher adds a
  source-specific image-completion marker only after image dependencies pass;
  the event guard fully validates the Release before using that marker to skip
  duplicate builds. Treat it as coordination metadata, not image attestation.
- Keep runtime code on the trusted workflow revision while passing the original
  verified source SHA explicitly to notes, source/version guards and images.
  Recovery must not silently substitute current main.
- Keep main/latest and production CICD/Drone independent. Do not modify image
  names, registry defaults, architectures, deployment settings or product code.
- Preserve existing notes and refuse public/mismatched candidate mutations.
  A source correction uses a new version/tag through the normal PR path.

## Outcomes & Retrospective

The coordinator and helper changes are implemented. Focused tests cover original
commit recovery, publication readback, prereleases, image failures, completion
metadata, source identity and credential boundaries. Independent review found
that draft metadata needs push-capable credentials; the validation job and its
caller now grant that visibility while native image jobs retain Contents read.
Local verification passed: 52 release regressions; 391 script tests and 229
subtests passed, with 8 Docker Compose cases skipped because the local CLI is
unavailable. Ruff/actionlint, architecture fixtures and required lefthook checks
passed. The working checkout has unrelated untracked runtime logs that trigger
the example identifier scanner, so harness and hooks ran in an exact clean
staged snapshot without altering those logs. [PR #3276](https://github.com/ai-shifu/ai-shifu/pull/3276) is open and unmerged;
remote CI is pending. Live release acceptance remains a separate check.
No live Release, registry push or production deployment was used as a test.
External release acceptance remains separate from local and PR CI results.

## Context and Orientation

`.github/workflows/prepare-release.yml` opens the version PR.
`.github/workflows/draft-release.yml` coordinates the automatic sequence.
`.github/workflows/build-on-release.yml` validates and builds formal release
images through `.github/workflows/build-docker-image.yml`; the latter owns
native build, smoke, digest publication and manifest checks.
`scripts/release_workflow.py` owns source, provenance, tag and Release operations.
`scripts/release_notes.py` retains frozen product and dependency-note generation.

The prior implementation journal is
[PR-first product release workflow](pr-first-release-workflow.md). Its original
manual-Publish gate is superseded by this plan; prior evidence is historical.
`docs/engineering-baseline.md` summarizes the new path, and the canonical Docker
publication reference owns its detailed operational rules.

## Plan of Work

Extend the existing helper with explicit pinned recovery, staged candidate
validation, guarded publication/readback and legacy-event deduplication. Wire the
coordinator so image success is a publication dependency. Retain the normal
main-push skip/error cases and existing manual published-event compatibility.
Align the version PR title/handoff, update regression coverage, then regenerate
knowledge indexes and run the required validation before opening an unmerged PR.

## Concrete Steps

From the repository root, run the smallest relevant real-Git/mocked-HTTP release
tests first, then related Docker routing/metadata and credential tests. Validate
Ruff and Actions syntax for the changed files. Stage the new plan and intended
Markdown changes before `python scripts/build_repo_knowledge_index.py`, then run
`python scripts/check_repo_harness.py` and architecture fixture checks as required.
Run `python scripts/check_dev_tools.py` before committing and the prescribed
lefthook gates. Record all actual test results and the final PR/head without
using live release or production operations as validation.

## Validation and Acceptance

A version PR uses `chore: bump version to vX.Y.Z`; preparation creates no formal
Release or tag. A normal version increase merged by the existing human gate
stages only its exact source. Same-version commits skip, invalid versions or
provenance fail closed, and prereleases cannot enter formal publication.

Image failure keeps the Release unpublished. Both services and required native
platforms must pass the existing smoke/digest/manifest checks before publication.
Published state, tag, source marker and completion metadata are read back before
success is reported. A PAT-triggered legacy event must not repeat a verified
automatic build; an unmarked valid manual publication retains its existing build
path. Explicit recovery accepts the original full SHA/version after main advances,
never current-main substitution. Tests must cover interruptions, mismatches,
repeat execution, prerelease state and both token event paths using mocked remote
writes rather than actual publication.

## Idempotence and Recovery

The original failed run is the preferred retry. Its event commit stays fixed and
successful platform digest artifacts remain usable across run attempts. A new
manual recovery run on main requires the original full `source_commit` and
matching `expected_version`. Expired artifacts require a full rebuild of that
same source, not a new tag at current main.

Missing tag/draft states can be completed; existing tags are never forced.
Matching drafts preserve notes. An owned matching public Release is read-only
and skips rebuilding verified images. Conflicting or unmarked public states,
wrong targets and prereleases fail closed. Partial registry success is retained
for investigation/retry because refs, services, registries and Releases are not
one atomic transaction. Content fixes require a new version and tag.

## Interfaces and Dependencies

Use the existing Python release helper and file-based notes interfaces with full
source SHAs, validated single-line Actions outputs and explicit JSON REST calls.
The coordinator invokes candidate image validation before the native image
builder and publication only after image success. Registry credentials remain in
existing secrets/variables. Draft/release mutation steps may select the existing
scoped PAT; read-only notes/metadata calls retain the repository token. GitHub
permission limitations remain documented in the canonical reference.

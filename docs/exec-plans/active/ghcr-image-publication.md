---
title: Publish repository Docker images to GHCR
status: active
owner_surface: repository
last_reviewed: 2026-10-08
---

# Publish repository Docker images to GHCR

## Purpose / Big Picture

Restore usable main images in GHCR while retaining Docker Hub and Aliyun mirrors.
Use the repository Dockerfiles and the existing native-platform production smoke
and content-verification gates. The durable rules and backfill instructions are
in [Docker image publication](../../references/docker-image-publication.md).

## Progress

- [x] 2026-10-08 08:45 UTC: Verify #3043 manual merge and both regional deployments;
  each sampled new API replica passes 141 isolated checks / 25 hashes, engine 1.0.
- [x] 2026-10-08: Review latest/release/validation workflows. Main has no GHCR
  destination or login; repository Dockerfiles pass all four native builds and
  production startup checks in latest run 37750976640.
- [x] 2026-10-08: Add explicit GHCR selection, automatic-token login, publishing
  caller permissions and main-only latest dispatch. Preserve credential-free PR
  validation and all-registry tested-content/manifest checks.
- [x] 2026-10-08: 29 packaging regressions, Ruff, actionlint, YAML validation,
  developer-tool checks and all repository gates pass. Mixed-case owners in release
  summaries are normalized and covered by executing the actual summary shell.
- [x] 2026-10-08: Publish PR #3046; candidate run 37752346532 passes all four native
  image builds/production smoke, three-registry digest pushes/config verification
  and both manifest publications. Final-head run 37752737804 is executing.
- [ ] Verify candidate manifests and anonymous GHCR access; reply to AI reviews.
- [ ] User manually merges; verify main automatically publishes all three registries.

## Surprises & Discoveries

The reusable workflow previously restricted its token to contents read. Granting
packages write only in callers would not work until that reduction is removed.
First GHCR publication defaults to private; public visibility is a separate
package setting and must be verified rather than inferred from a successful push.
The local gh token lacks read:packages, so listing packages via that token returns
403; do not replace credentials or widen them to bypass this.

GitGuardian classified literal disposable username/password fixture values as a
credential pair. Generate throwaway random values inside the test instead; no
real credential was committed. Use generated usernames and values to avoid
misclassifying disposable fixture identifiers as credentials.

The user's ChatGPT Chrome extension connected during acceptance. The signed-in
package settings show repository Actions Admin access, but Public visibility is
disabled by organization administrators. The organization Packages policy has
Public creation unchecked. Ask for explicit authority before changing that policy,
because it affects all members; preserve the current policy while awaiting the
user's choice. Anonymous GHCR pull authorization currently returns 401.

## Decision Log

- 2026-10-08: Keep one tested build per service/architecture, export its layers to
  GHCR and configured mirrors, then merge native digests in each destination.
- 2026-10-08: Grant package writes only to latest, release and explicit candidate
  publishing jobs. PR validation inherits contents read and cannot publish.
- 2026-10-08: Preserve existing optional mirror credentials, image names, release
  semantics and PUSH_LATEST_IMAGES. Scope latest manual dispatch to main.
- 2026-10-08: Do not change production CICD, application runtime, dependency pins,
  Compose defaults or global cross-service publication ordering in this PR.

## Outcomes & Retrospective

Implementation and local shell/manifest regressions pass. PR #3046 is open.
Existing main builds establish Dockerfile feasibility, not GHCR acceptance.
Candidate publication must prove the new destination before final handoff.

## Context and Orientation

The shared build workflow resolves destinations through the composite metadata
action in each job. Latest, release and candidate callers opt into GHCR.
Native build jobs smoke-test final images and verify the pushed config in every
destination. Manifest jobs consume attempt-aware digest artifacts and preflight
each repository before publishing service tags.

## Plan of Work

Exercise actual metadata shell resolution with no mirror credentials, all three
destinations and disabled publication. Check permissions and PR boundaries.
Run native builds and isolated candidate publication through GitHub Actions,
inspect all destination manifests and compare their platform digests. Check
anonymous GHCR pulls separately from authenticated publication.

## Concrete Steps

Run the three Docker script test modules, Ruff, actionlint, YAML validation,
developer-tool checks and full lefthook gates. Stage new documentation before
regenerating indexes. Push one branch and open a normal PR into main. Dispatch
Docker Packaging Checks with publish-candidates=true on that branch; inspect
build, startup, push, content-verification and manifest steps independently.

## Validation and Acceptance

The repository Dockerfiles build and boot API/Web on native AMD64 and ARM64.
Candidate tags in all three registries contain the same two native digests.
GHCR is usable anonymously after package visibility is public. Main publishes
latest and SHA tags automatically; a manual main dispatch can backfill them.
PR and build-only modes cannot authenticate or push; disabled latest publication
remains disabled for GHCR. No production deployment is triggered by candidate tags.

## Idempotence and Recovery

Candidate tags are isolated by run/attempt. Failed-job reruns select the latest
successful digest per architecture in the same run. Missing artifacts fail closed.
Retrying candidate publication does not change latest/release tags. Roll back
workflow changes through a reviewed PR; main merge remains the user's decision.

## Interfaces and Dependencies

Add a publish-ghcr boolean to the reusable workflow and composite action, default
false for safe validation. Publishing callers opt in and grant packages write.
Use the built-in repository token, existing Docker actions and test-only PyYAML;
no application dependency or secret configuration changes.

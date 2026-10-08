---
title: Publish Web images without the Cook name
status: active
owner_surface: repository
last_reviewed: 2026-10-08
---

# Publish Web images without the Cook name

## Purpose / Big Picture

Publish future public images as `ai-shifu-web` and `ai-shifu-api` in GHCR,
Docker Hub and Aliyun. Keep existing `ai-shifu-cook-web` packages and tags
untouched. The publication contract is in
[Docker image publication](../../references/docker-image-publication.md).

## Progress

- [x] 2026-10-08: Confirm #2945 renamed npm metadata while deliberately retaining
  deployment identifiers. The user now requests the public image rename.
- [x] 2026-10-08: Update latest, release, candidate and validation names, release
  pull commands, latest Compose references and installation documentation.
- [x] 2026-10-08: Migrate the pinned Web name only when Prepare Release Draft
  advances its version; preserve existing historical image references meanwhile.
- [x] 2026-10-08: All 35 packaging regressions and latest Compose resolution pass.
- [ ] Complete repository gates, open a focused PR and verify candidate publication.
- [ ] Verify the new GHCR package's public visibility and anonymous pull access.
- [ ] User manually merges; verify main publishes the new names automatically.

## Surprises & Discoveries

The earlier rename intentionally distinguished the private npm package from the
published image. Changing only the publishing defaults leaves latest Compose
consumers on the old package. Changing the pinned bundle immediately would
advertise a historical Web tag that has never been published under the new name.

## Decision Log

- 2026-10-08: Honor the requested future names in all three registries. Stop
  reading the old Web image-name variable; do not dual-publish or delete old tags.
- 2026-10-08: Use `AI_SHIFU_WEB_IMAGE_NAME` for optional overrides, consistently
  in latest/release/candidate callers and release pull instructions.
- 2026-10-08: Keep Compose service/container names, nginx upstreams, local dev
  image names and production CICD unchanged. Only public publication changes.
- 2026-10-08: Keep the current pinned historical release available. Its next
  version bump migrates to `ai-shifu-web` without touching third-party images.

## Outcomes & Retrospective

The implementation and offline checks pass. Candidate registry acceptance,
public visibility and manual main merge remain outstanding.

## Context and Orientation

Three callers pass one image name into the reusable native-platform workflow;
the metadata action uses that same name for GHCR and both configured mirrors.
The release summary must use those resolved names too. Prepare Release Draft
owns future pinned image-version updates; latest Compose follows main builds.

## Plan of Work

Update all callers and consumer instructions together. Exercise the actual
metadata, release summary and release-version shell with disposable fixtures.
Run the repository gates, then publish a candidate tag without moving latest
or release tags. Verify both architectures and new package public access.

## Concrete Steps

Run the three `scripts/test_*docker*` and manifest suites listed below, render
latest Compose with `--no-env-resolution`, regenerate knowledge indexes, and
run all pre-commit gates. Open the PR from `codex/public-web-image-name` against
main. Manually dispatch Docker Packaging Checks on that branch with
`publish-candidates=true` for the registry acceptance step.

## Validation and Acceptance

- `python -m pytest scripts/test_merge_docker_manifests.py scripts/test_check_docker_image.py scripts/test_docker_image_metadata.py -q`
- `docker compose -f docker/docker-compose.latest.yml config --no-env-resolution`
- `python scripts/check_dev_tools.py`
- `lefthook run pre-commit --all-files`
- Candidate builds must smoke-test both architectures and verify identical
  tested content in all three registries before merging manifests.
- The new GHCR Web candidate must be publicly pullable without credentials.
  Existing old Web tags are never pushed, removed or retagged by this change.

## Idempotence and Recovery

Candidate runs use isolated tags and do not move latest. Repeating the release
version update handles both old and new names. Historical bundles continue to
pull their original images. Main merge is manual; a failed post-merge latest
publication can be rerun on main after fixing its registry permission issue.

## Interfaces and Dependencies

No application dependency, runtime environment, database or deployment change.
Existing registry secrets and native AMD64/ARM64 build, startup and manifest
verification gates remain in force. A newly created GHCR package may require
one-time Public visibility; verify it instead of assuming successful push
means anonymous availability.

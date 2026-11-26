# Independent Docker image publication

## Purpose / Big Picture

Allow GHCR, Docker Hub, and Aliyun to publish the two native AI-Shifu images
independently. In run 43831517895, both AMD64 builds passed production smoke
checks, then waited for Aliyun until the 90-minute job timeout. GHCR and Docker
Hub already had the native images, but the shared gate prevented their final
tags from moving. [GitHub Actions run](https://github.com/ai-shifu/ai-shifu/actions/runs/43831517895)

## Progress

- [x] 2026-11-17 01:34 UTC: Verified the run logs, current callers, and the
  shared registry push and manifest gates.
- [x] 2026-11-17 01:51 UTC: Implemented archive handoff, separate registry
  jobs, and bounded retries. Verified timed-out Aliyun and successful sibling
  publications in script tests and copied an archive with ORAS against a
  local registry API fixture.
- [x] 2026-11-17 01:55 UTC: Passed 289 packaging and release tests,
  actionlint, and the repository-wide lefthook checks.
- [x] 2026-11-17 04:04 UTC: Verified native archive loading in PR CI, sibling
  tag publication during an [injected Aliyun timeout](https://github.com/ai-shifu/ai-shifu/actions/runs/44008687201),
  and a [real Aliyun Web candidate](https://github.com/ai-shifu/ai-shifu/actions/runs/44014186869/job/133808040984)
  using both native archives over HTTP/1.1.
- [x] 2026-11-17 04:14 UTC: Scoped the transport setting to Aliyun archive
  copies and passed regression coverage for all three registry jobs.
- [x] 2026-11-17 05:12 UTC: Compared the failed and successful runner
  allocations and measured [the same layer PUT](https://github.com/ai-shifu/ai-shifu/actions/runs/44020960789)
  on four fresh runners.
- [x] 2026-11-17 05:15 UTC: Injected a timeout in the first Aliyun Web copy
  and verified that the retry runner used the same tested archives.
  All three registries published and returned matching platform digests.
  [Candidate verification](https://github.com/ai-shifu/ai-shifu/actions/runs/44022538284)

## Surprises & Discoveries

- Running multiple exporters in one Buildx solve can overlap uploads. The
  common solve result and manifest preflight would still couple tag publication.
- Registry deadlines need to stop Docker's Buildx plugin along with the parent
  CLI process. GNU timeout gives both processes the same deadline.
- The two missing Web AMD64 layers shared a slow HTTP/2 connection to Aliyun.
  On the same runner, the same archive copied over HTTP/1.1 in about 25 seconds.
- Identical Web archives timed out on one `us-west-2` runner and copied
  successfully on a `centralus` runner. Three direct HTTP/1.1 PUTs sent the
  full 174,048,520-byte `.next` layer in 13.6 to 16.8 seconds. A later
  `us-west-2` probe reached the deadline after HTTP 202 and read about 2.8 MiB
  of the request body in 88.3 seconds. All four used the same registry address.

## Decision Log

- Publish from the same archive used for the native smoke test, using Actions
  artifacts so every registry can start without waiting for another registry.
- Apply timeouts and bounded retries to registry commands. Keep each failed
  registry's job visibly failed, with sibling jobs allowed to finish.
- Set `GODEBUG=http2client=0` for Aliyun's ORAS copy subprocesses. The
  publishing job declares its registry and supports custom Aliyun endpoints.
- Move Aliyun copy retries to one fresh runner using the same tested
  archives. Allocate one copy attempt on the first runner and two on the
  retry runner.

## Outcomes & Retrospective

Hosted candidate runs verified that tags move independently when Aliyun times
out and that HTTP/1.1 completes the Aliyun Web copy within its existing
deadline on a healthy connection. An injected copy failure scheduled a
distinct runner, which published the same tested Web digests.

## Context and Orientation

All latest, release, candidate, and packaging callers use
[build-docker-image.yml](../../../.github/workflows/build-docker-image.yml).
The shared [publication reference](../../references/docker-image-publication.md)
describes the tags, credentials, and verification requirements. Production
CICD/Drone uses a different build and deployment path.

## Plan of Work

Export and load one archive per service and architecture. Match its manifest's
config digest to the tested image before uploading the archive. Run the
configured destinations in a non-fail-fast matrix. Copy both tested manifests
by digest and validate the platform index before writing or accepting its tags.

## Concrete Steps

1. Update the reusable workflow, metadata action, and packaging scripts.
2. Exercise the archive handoff, partial reruns, registry isolation, and
   transient and exhausted retries with the Docker Packaging Checks tests.
3. Validate workflows and repository checks, then submit the branch as a PR.

## Validation and Acceptance

An unavailable Aliyun endpoint must leave that job failed after its bounded
retries while GHCR and Docker Hub can verify and publish their tags. A registry
with a missing or mismatched image must fail before updating its tags. Build-only
PRs still load and smoke-test the native image with read-only permissions.

## Idempotence and Recovery

Upload and retry immutable platform digests from one workflow run. A failed-job
rerun reuses that run's successful build artifacts and retries only the failed
registry jobs. Expired artifacts require rerunning the builds. Roll back through
a PR restoring the previous publishing workflow.

## Interfaces and Dependencies

Native jobs use Buildx and Docker load. Publishing jobs use ORAS to copy
the image archive by digest, and Buildx imagetools to create and check the
registry's platform index. Registry credentials and tag rules remain owned by
the callers and the Docker image metadata action.

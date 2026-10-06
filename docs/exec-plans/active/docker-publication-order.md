# Coordinated Docker Publication and Digest Deployment Inputs

## Purpose / Big Picture

Prevent partial API/web readiness and older workflow runs from moving the latest
channel. Retain existing main/manual/release triggers, registry configuration,
and aliases, while supplying a usable digest descriptor for a consistent API,
worker, scheduler, and web deployment. The canonical operational contract is
[Docker publication](../../references/docker-publication.md).

## Progress

- [x] 2026-10-07 UTC: Inspected the native-build PR, tag callers, manifest helper,
  and actual Compose service names in an isolated managed worktree.
- [x] 2026-10-07 UTC: Implemented coordinated promotion, run/attempt candidates,
  verified index annotations, service artifact carryover, and digest rendering.
- [x] 2026-10-07 UTC: Added 45 focused offline tests and passed pinned Ruff.
- [x] 2026-10-07 UTC: Passed actionlint, YAML, strict development-tool checks,
  architecture boundaries, repository harness, and the complete pre-commit gate.
- [x] 2026-10-07 UTC: Integrated native smoke changes, explicit OCI outputs,
  and isolated candidate index-copy/descriptor acceptance after rebasing onto #3015.
- [x] 2026-10-07 UTC: Added guarded cached native-export retries, exact
  smoke/config metadata checks, retry-time main guards, and terminal main readback;
  all 55 publication plus foundation smoke tests pass.
- [ ] External acceptance: verify cold/warm native smoke builds, actual index
  copies and annotations in both registries, partial recovery, and ordering.

## Surprises & Discoveries

- Main SHA comparison alone cannot order two rebuilt runs of the same SHA.
  Registry index annotations carry run/attempt ordering through latest copies.
- SHA aliases can change on rebuild; immutable deployment input is the actual
  registry digest, not a claim that a source tag never changes.
- Compose runs the API image in three services, so a usable deployment override
  must pin the API server, Celery worker, and Celery scheduler together.
- A manifest command can reach the registry before a transport error. Recovery
  reports unknown writes accurately instead of claiming cross-registry rollback.

## Decision Log

- Use a single latest promotion job after both reusable service jobs complete.
  The build owner adds production-image smoke validation before digest export.
- Serialize latest writers and check live main plus current latest ordering
  before mutation. Superseded runs emit a stale status and skip remaining writes.
- Keep descriptors independent of mutable channel status, and supply an offline
  Compose renderer for all four application services.
- Retry only recognized transport failures, at most twice, with the identical
  command. Preserve authentication and manifest-format failure visibility.

## Outcomes & Retrospective

The local implementation covers the publication contract without registry writes.
External registry and smoke acceptance remains open; local tests cannot establish
real registry annotation support or native-image startup behavior.

## Context and Orientation

Latest and release callers invoke `build-docker-image.yml` for each service. Its
publish job writes complete candidate manifests and emits service artifacts.
`complete-docker-publication.yml` runs after all services, collects both API/web,
and optionally promotes latest. `merge_docker_manifests.py` owns registry command
retry and manifest validation. `push_tested_docker_image.py` owns transport-only cached native exports.
`promote_docker_images.py` owns coordination,
ordering, deployment descriptors, and Compose rendering. There is no application
runtime or analytics contract change.

## Plan of Work

Finish focused tests and workflow checks, update canonical publication guidance,
and integrate with the native-build/smoke changes in the parent task. Keep this
publication work as an independent commit/problem for review. No deployment or
registry publication is performed from this worktree.

## Concrete Steps

Run the focused publication tests, pinned Ruff, YAML validation, actionlint, and
repository harness. Stage new documentation before knowledge-index regeneration.
Run development-tool validation and the repository pre-commit gate before commit.
The parent task coordinates cherry-picking and final CI/registry acceptance.

## Validation and Acceptance

Offline tests require incomplete service sets, wrong sources, mismatched registry
sets, missing annotations, stale source refs, newer same-SHA runs, and permanent
registry failures to prevent latest writes. Partial failure reports preserve
verified and unverified destinations and can be recovered with the same digest
inputs. Compose rendering must pin all four application services and reject a
missing registry. External acceptance must inspect real registry index digests,
annotations and platforms, and prove that all native smoke tests precede latest.

## Idempotence and Recovery

Candidate tags and artifacts include run/attempt identity; a new rerun cannot
replace a previously recorded candidate version. Failed-job reruns select the
newest successful service artifact from the same run. Immutable digest operations
can repeat safely. Registries and services do not share an atomic commit;
partial status identifies what needs readback or retry. Expired native artifacts
require rebuilds. Reverting code has no effect on already published images.

## Interfaces and Dependencies

Use Python 3.11 standard library, Buildx imagetools, and existing GitHub Docker
and artifact actions. The collector consumes service schema version 1 and emits
deployment descriptor version 1 plus separate status. The renderer accepts the
descriptor and registry hostname and writes JSON Compose input. Runtime smoke
implementation and native build/push verification are owned by the parent task.

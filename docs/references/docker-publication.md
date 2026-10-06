# Docker Publication and Deployment Descriptors

## Channel contract

`build-latest.yml` keeps its main-push and manual triggers. A manual run on a
non-main ref builds and smoke-tests without registry publication. The main push
toggle and missing-credential build-only fallback remain in place. No individual
service job can write `latest`: `merge_docker_manifests.py` rejects that tag.

The reusable build workflow must complete both native platforms and their
production-image smoke tests before publishing a service manifest. Service jobs
publish SHA/release aliases and the candidate tag
`build-<run_id>-<run_attempt>-<service>`. The candidate identifies a particular
build attempt. A SHA alias identifies source, but is not an immutable binary:
rebuilding a SHA can resolve different base images or external dependencies.

Only after every API/web build, smoke test, and service-manifest publication
succeeds does `complete-docker-publication.yml` collect both services. Release
publication creates the same deployment descriptor without moving `latest`;
release draft/prerelease gating and release tags remain unchanged.

## Ordering and verification

All latest promotions share a repository-wide concurrency group, with active
publication cancellation disabled. Before the first write and each subsequent
write, promotion resolves the live `main` ref and requires its SHA to equal the
run's source SHA. A superseded run records `stale` and skips remaining writes.

Candidate indexes include `io.ai-shifu.publication.run-id` and
`io.ai-shifu.publication.run-attempt`. Promotion also inspects the current latest
indexes and refuses to replace a newer run or a newer service attempt of the
same run. This covers rebuilds of the same SHA. Old unannotated latest indexes
are accepted for migration; new candidate annotations are verified before they
can become latest. Index copies preserve the registry-reported index digest.

Before moving any latest tag, the collector validates source provenance, the
complete API/web service set, matching registry destinations, and every exact
index/platform digest. Each final tag is then read back and must match its
recorded index digest. Docker Hub and Aliyun are independent registries;
promotion across services and registries is not an atomic transaction.

## Artifact interfaces

Each successfully published service uploads
`docker-publication-<service>-<run_attempt>/service.json`. It contains schema
version 1, service identity, source SHA/run/attempt, and each registry repository's
index digest and exact `linux/amd64` and `linux/arm64` digests. A failed-job rerun
carries forward successful service artifacts from earlier attempts of the same
run, selecting the highest successful attempt per service. Missing, mismatched,
or expired artifacts fail closed.

The completed artifact is named `docker-deployment-<run_id>-<run_attempt>` and
contains:

- `deployment-descriptor.json`: one fixed source identity and the verified API
  and web digest references for each registry, including each service's selected
  build attempt. Deployment consumers use these digest references together.
- `publication-status.json`: a separate channel-operation report. It records
  the SHA-256 of the stored descriptor bytes, overall `verified`, `failed`, or `stale` state, and
  each destination's `pending`, `unverified`, or `verified` state. An unverified
  write may have reached the registry; it does not imply a rollback.

Descriptor and status artifacts are retained for 90 days. Native digest artifacts
retain the existing seven-day lifetime. Download required deployment descriptors
into durable deployment storage before GitHub artifact expiry.

## Digest-pinned Compose deployment

After downloading and selecting a descriptor, generate an override for the
configured registry. The renderer works offline and does not move tags:

```bash
python scripts/promote_docker_images.py render deployment-descriptor.json \
  --registry docker.io --output docker/docker-compose.digests.json
cd docker
docker compose -f docker-compose.latest.yml -f docker-compose.digests.json config
docker compose -f docker-compose.latest.yml -f docker-compose.digests.json up -d
```

Use the Aliyun registry hostname instead of `docker.io` to choose its recorded
references. The JSON output is valid Compose input and pins `ai-shifu-api`,
`ai-shifu-celery-worker`, `ai-shifu-celery-beat`, and `ai-shifu-cook-web` to the
same descriptor. Unrelated infrastructure images retain their base Compose
configuration. Generation fails if either service has no unique image in the
selected registry; it never falls back to `latest`.

## Failure and recovery

Only registry transport errors such as TLS handshake timeout, connection reset,
and temporary name-resolution failure receive up to two retries of the identical
manifest command. Authentication, authorization, certificate trust, media-type,
manifest-validation, and unknown errors fail without retries. Native builds and
smoke tests are not retried by this helper.

Read the per-service status artifact and the complete publication status before
recovery. A partial write retains the descriptor's immutable digest references
and reports the destinations already verified. Rerun failed jobs to reuse
successful artifacts and repeat the idempotent digest-based operations. Ordering
checks still apply; a newer main SHA or successful publication prevents an old
run from restoring `latest`. If native digests expire, rerun the native builds.
For an intentional older-version deployment, render its retained descriptor;
do not use a stale workflow to roll back the shared latest channel.

Docker documents registry inspection and structured index digest output in
[imagetools inspect](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/).

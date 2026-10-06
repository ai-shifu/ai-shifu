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
publication cancellation disabled. Before every write attempt, including each transport retry, promotion resolves the live `main` ref and requires its SHA to equal the
run's source SHA. After the final readback it checks main again before reporting
verified. A superseded run records `stale` and skips remaining writes.

Native registry outputs explicitly use OCI media types so index annotations
do not depend on BuildKit defaults. Candidate indexes include `io.ai-shifu.publication.run-id` and
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

## Isolated registry acceptance

The packaging workflow's manual `publish-candidates` option builds and smoke-tests
both services and enables `verify-registry-smoke`. For every registry and native
platform it pulls the exact exported digest with `docker pull --platform`, reruns
the same production startup/HTTP/native-module smoke, and requires its config
digest to equal the original local smoke record before any native handoff. Pull,
startup, and content failures prevent successful service publication. Regular
latest/release jobs retain config readback without this extra startup pass.
The candidate path then publishes isolated manifests and runs `complete-candidates`.
That job collects the same complete digest descriptor and exercises the identical
index-copy/readback operation using
`candidate-copy-<run_id>-<run_attempt>-<service>` tags in each configured registry.
Its independent `candidate-copy` status exposes verified and unknown partial
writes. It does not mutate latest or require the source to be current main,
so registry compatibility can be tested before merging.

Candidate [run 37542695302](https://github.com/ai-shifu/ai-shifu/actions/runs/37542695302)
passed on publication head `aadcbb330`: all four native images passed the local
smoke, cached export/config gate, and immutable pull/startup smoke in both
registries. Both service indexes preserved their ordering annotations; all four
candidate-copy targets retained their source index digests. The downloaded
descriptor hash matched its verified status, and both registry Compose overrides
rendered successfully. Combined-head acceptance after foundation/network
integration is tracked by the active publication ExecPlan.

Candidate-copy and latest-promotion CLI modes are mutually exclusive. Selecting
candidate copies cannot disable the main/source/order checks of a latest
promotion. A descriptor-only release uses neither copy mode.

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
  write may have reached the registry; it does not imply a rollback. Latest targets
  also record `expected_digest` and `previous_digest`: the previous registry-reported
  digest is saved for every target during preflight, before any write. A missing
  old latest tag records `null` after a successful preflight; an existing tag
  with an invalid digest blocks publication. A pending target with `null` may also
  mean its preflight was never completed. Copy retries and later main changes never replace this snapshot
  with the new digest. Candidate-copy targets leave `previous_digest` as `null`.

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
manifest command. The native image push also uses a guarded cached exporter in
`scripts/push_tested_docker_image.py`. It requires an existing successful
production-smoke record, the same active builder and build inputs, explicit OCI
media types, disabled provenance/SBOM, and positive plain-progress evidence that
every reported RUN reused the tested cache. Only an exporter-owned transport
failure can repeat that identical cached export; dependency downloads, compile
errors, SIGILL, missing cache evidence, and metadata/config mismatches do not
retry. Buildx metadata must identify the smoke-tested config, and each registry's
published config is read back before a native digest artifact is uploaded.

Authentication, authorization, certificate trust, media-type,
manifest-validation, and unknown errors fail without retries. The initial native build and production smoke are not retried by these helpers.
Login actions keep their existing authentication boundary; the cached exporter
handles transient OAuth transport failures during push, not rejected credentials.

Download and retain the failed attempt's per-service and complete status
artifacts before recovery. Match `descriptor_sha256` to the exact downloaded
`deployment-descriptor.json` bytes. The report preserves previous latest digests from successful preflights,
including targets not yet written, and identifies
verified, unverified, and pending targets. An unverified write requires registry
readback before deciding which state exists.

To resume the intended publication, rerun failed jobs in the same workflow run:

```bash
gh run rerun <run-id> --failed
```

This reuses successful service artifacts and repeats digest-based operations.
Main/source/order guards still apply before every write/retry: a newer main SHA
or successful publication prevents the old run from restoring latest. Each new
attempt has its own status artifact; keep the original failed status as the
record of the original previous targets. If native digests expire, rerun native
builds. An intentional older-version application deployment can instead render
its retained descriptor without changing the shared latest tags.

The workflow never rolls aliases back automatically. For an explicitly chosen
operator rollback, first stop concurrent latest publishers, check that live main
still matches the failed status source, and read each affected latest tag. Abort
if its digest differs from that target's `expected_digest` or newer publication
annotations are present. The saved `previous_digest` identifies the exact prior
content; inspect that immutable reference, copy it manually, and read back the
tag to confirm the prior digest:

```bash
docker buildx imagetools inspect --format '{{json .Manifest}}' "$TARGET_TAG"
docker buildx imagetools inspect --format '{{json .Manifest}}' "$REPOSITORY@$PREVIOUS_DIGEST"
docker buildx imagetools create --tag "$TARGET_TAG" "$REPOSITORY@$PREVIOUS_DIGEST"
docker buildx imagetools inspect --format '{{json .Manifest}}' "$TARGET_TAG"
```

Use this sequence only for a target that was written and has a non-null previous
digest, with the writer pause and checks above maintained through the operation.
For a written target, a `null` previous value means the alias did not exist at
preflight. A pending target with `null` may instead be unchecked or rejected by
preflight; do not infer its absence. Neither case is an image to copy or an
instruction to delete a tag. Keep pending targets unchanged and retain the
status and readback evidence. A stale status is not authority to overwrite a
newer publication; use a retained descriptor for the application deployment.

Docker documents registry inspection and structured index digest output in
[imagetools inspect](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/).

Docker describes the cached export inputs and metadata digest fields in
[buildx build](https://docs.docker.com/reference/cli/docker/buildx/build/).

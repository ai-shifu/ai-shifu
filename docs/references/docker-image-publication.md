---
title: Docker image publication
status: canonical
owner_surface: repository
last_reviewed: 2026-11-01
---

# Docker image publication

GitHub Actions builds the public API and Web images from the repository root
using `src/api/Dockerfile` and `src/web/Dockerfile`. This path is independent
of the production CICD/Drone build and its deployment Dockerfiles.

## Frontend source revision

Before building Web, both the reusable native-image workflow and the runtime
harness write the checked-out `git rev-parse HEAD` to
`src/web/.app-build-sha`. Use the checkout's actual HEAD rather than the event's
SHA so release tags and PR merge checkouts retain the correct source identity.
The generated file is Git-ignored and remains included by Docker ignore rules.
The tested and published images use the same prepared source context.

Production CICD replaces the repository Dockerfiles, so its existing
`build_before` preparation must also generate the marker, after checkout and
before the Web image build:

```bash
git -C /drone/src rev-parse HEAD > /drone/src/src/web/.app-build-sha
```

Append that command without replacing plugin, Dockerfile or translation
preparation. The production Web Dockerfile's existing `COPY . .` includes the
marker before Next compiles the public version constants. Manual Docker builds
use the same marker preparation from the repository root. See the
[frontend configuration reference](../../src/web/src/config/ENVIRONMENT_CONFIG.md#frontend-build-identity).

## Destinations and permissions

Publishing callers enable GHCR at
`ghcr.io/<lowercase repository owner>/<image name>` and grant
`contents: read` plus `packages: write`. Both native build and manifest jobs
inherit those permissions and log in with the automatic repository
`GITHUB_TOKEN`; no new PAT secret is required.

Docker Hub remains enabled when `DOCKERHUB_USER` and `DOCKERHUB_TOKEN` are
configured. Aliyun remains enabled when `ALIYUN_USER` and `ALIYUN_TOKEN` are
configured; its registry defaults to `registry.cn-beijing.aliyuncs.com` and
its public-image namespace remains `ai-shifu`. This is distinct from the
production CICD's `agix` namespace. Currently all three destinations are
intended for the AI-Shifu repository. Forks can publish to their own GHCR
namespace without the optional mirror credentials.

The image names default to `ai-shifu-api` and `ai-shifu-web`.
`AI_SHIFU_API_IMAGE_NAME` and `AI_SHIFU_WEB_IMAGE_NAME` repository variables
override those names consistently for latest, release and candidate builds.
The old `AI_SHIFU_COOK_WEB_IMAGE_NAME` variable is no longer read. Existing
`ai-shifu-cook-web` packages and historical tags are retained; new publications
use the Web name without also updating the old package.

Verify GHCR package visibility on first publication, even for public source
repositories. If a package is private, set its visibility to **Public** in
package settings before advertising anonymous pulls. An existing package must also
grant this repository Actions access. A successful authenticated push alone
does not establish anonymous availability. If Public is disabled in package
settings, an organization owner must review **Settings → Packages → Package
creation → Public**. That policy affects all members; obtain explicit authority
before changing it, even when only two packages need to be public. See GitHub's
[Container registry guidance](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Triggers and backfills

| Entry point | Trigger | Tags | Publication |
| --- | --- | --- | --- |
| Build Latest Docker Images | Push to main, or manual Run workflow on main | `latest`, full commit SHA | GHCR and configured mirrors |
| Publish Merged Release | Increasing version merged to main, or explicit pinned-source recovery | Formal `vX.Y.Z` only | Verified images, then formal GitHub Release |
| `build-on-release.yml` | Reusable pre-publication call, or legacy published-release event | Formal `vX.Y.Z` only | GHCR and configured mirrors |
| Critical Path Runtime Checks | Runtime-affecting pull request or manual dispatch | Local production AMD64 images | No login or push |
| Docker Packaging Checks | Pull request with packaging changes, affected services on native ARM64 | Local validation name | No login or push |
| Docker Packaging Checks | Ordinary manual dispatch, both services on AMD64 and ARM64 | Local validation name | No login or push |
| Docker Packaging Checks, publish-candidates=true | Explicit manual dispatch on the branch to test | `candidate-<run id>-<attempt>` | GHCR and configured mirrors |

`PUSH_LATEST_IMAGES=false` disables every registry push for latest builds,
including manual backfills. Manual latest dispatch on another branch is skipped
so a feature branch cannot overwrite `latest`. Candidate publication remains
available for testing that branch without moving normal tags.

To backfill the current main, open **Actions → Build Latest Docker Images →
Run workflow**, select **main**, and run it. This rebuilds both services for both
architectures and publishes the current main's SHA and latest tags. It does not
rebuild historical releases. For a failed existing release workflow, rerun that
original run so it retains its source commit and tag; expired digest artifacts
require a full rerun. Use the pinned recovery procedure below if a new run is
needed. Do not create another release merely to backfill latest.

## PR-first release gates

`Prepare Release PR` accepts a final `vX.Y.Z` increase on main and creates only
`release/version-bump-<tag>`. Its title and version commit use
`chore: bump version to vX.Y.Z`. Its version-file scope is the Web npm manifest
and lock root, the vendored engine version, and first-party pinned Compose
images. It does not create a formal tag, Release or deployment. AI/scripts must
never merge or enable auto-merge. A human reviews CI and manually merges into
main; that merge authorizes the automatic formal publication sequence, with no
second **Publish release** click.

`Publish Merged Release` in `draft-release.yml` runs on main pushes without
changing latest or production CICD/Drone configuration. It freezes the event
SHA and compares the primary Web version at `before` and `after`. No change or
an initial absent baseline skips. Invalid/decreasing versions, forced pushes,
inconsistent npm / engine / Compose versions, or missing exact merged-release-PR
provenance fail. The source must itself introduce the version increase; a
batched push ending in a later non-version commit is not silently substituted
for the merge source.

The provenance guard requires a merged same-repository release branch targeting
main, an exact `merge_commit_sha`, no recorded `auto_merge`, and a non-bot merger.
It explicitly excludes the known `ai-shifu-bot` automation account even though
GitHub reports its type as `User`. **User metadata does not prove a physical
human**, and GitHub may clear auto-merge metadata after completion. Manual review
and repository branch/access policy remain necessary; these workflows do not
change settings or claim to fully attest a human action.

The coordinator first pins the formal tag to the exact source, including peeled
annotated tags, and creates or resumes a draft with `draft=true`,
`prerelease=false`, and `make_latest=false`. It never force-updates a tag. Tag,
target SHA, title, source marker, source versions and pinned images must agree.
It reads the tag and Release back after writes and retains human note edits on
same-source retries. A mismatched or prerelease candidate fails closed.

Before that Release becomes public, the coordinator explicitly invokes
`build-on-release.yml`. Its candidate guard revalidates the draft, source,
version, tag and merged-PR provenance, then passes the immutable source SHA to
the existing native image builder. The candidate-validation job uses a
push-capable repository token because GitHub hides drafts from read-only
credentials; its metadata operations remain read-only, and image builders keep
Contents read permission. Both API and Web must pass native AMD64 and
ARM64 production-image startup smoke checks, tested-content digest checks, and
multi-platform manifest publication/readback for all configured destinations.
The release caller emits only its formal version tag; it never writes `latest`,
including when recovering an older source from a workflow running on main.
Existing image names, registries, architectures and `build-latest.yml` behavior
are retained.

Only after both image services succeed does the coordinator publish the same
Release. The publication helper preserves notes and adds exactly one
`<!-- ai-shifu-release-images-verified:<source SHA> -->` marker together with
the public state, then reads back the source, tag, state and body. The marker is
workflow coordination metadata, not independent cryptographic image
attestation. The coordinator owns when it may be written: only after its image
build dependencies have succeeded.

The legacy `release.published` entry point remains available for manual
publication. Its guard still revalidates the actual Release, source, tag,
metadata, versions and PR provenance. A valid image-completion marker for that
exact source skips duplicate image builds; an unmarked manual publication
retains the existing image-build path. Invalid, duplicate or wrong-source
completion markers fail closed. This explicit handoff works with either a PAT
or `GITHUB_TOKEN`: events caused by the repository token do not start a second
workflow, while PAT-triggered publication cannot duplicate the completed build.
Drafts and prereleases never enter formal image publication.

Only the draft/release mutation steps select the existing `PAT_TOKEN` secret
before falling back to `GITHUB_TOKEN`; note lookups retain the repository token.
The PAT must have repository access plus the classic `workflow` scope, or
fine-grained Contents and Workflows write permissions plus Pull requests read
permission for this repository. GitHub requires workflow-write authorization
when a frozen target's workflow files differ from the current default branch,
including a delayed draft or retry after main changes a workflow.
`GITHUB_TOKEN` cannot be granted that authorization. The fallback therefore
covers targets that do not require workflow-write permission; it does not
replace a correctly scoped PAT for delayed targets. See GitHub's
[release API permission requirements](https://docs.github.com/en/rest/releases/releases#create-a-release).
Credential selection does not change the event, provenance, version or immutable
tag guards.

### Failure recovery

For an interrupted automatic release, rerun the original failed jobs so the
source commit stays frozen. Successful architecture digest artifacts remain
available across attempts; the manifest publisher chooses the newest successful
digest for each required platform from that run. If artifacts have expired, use
a full rerun of that original source.

For an explicit new recovery run, open **Actions → Publish Merged Release →
Run workflow**, select **main**, and provide `source_commit` as the full original
merged SHA plus its matching `expected_version`. The source must already be an
ancestor of main and pass the same version-increase and merged-PR provenance
guards. The workflow runtime comes from its trusted workflow revision, while
release notes and image inputs remain pinned to the original source. Moving
main or choosing its current version is not a substitute for the failed source.

A same-source tag with no Release, or a matching incomplete draft, is
recoverable. A matching published Release with the owned completion marker is
verified without edits or rebuilding its images. An unmarked public Release,
conflicting tag, mismatched metadata, or prerelease state requires investigation;
recovery does not overwrite it. If source or package contents need changing,
merge a fix through the normal PR process and use a new version and tag.

A failed image stage leaves the Release unpublished. Ref, registry and Release
writes are not one atomic transaction: a tag, draft or some service images may
already exist after an interruption. Recovery validates those existing states
instead of deleting them or moving a tag. If a retry returns 403/404 after main
changes workflow files, verify `PAT_TOKEN` has the workflow-write authorization
above, then retry the original source. A successful publication is read back;
there is no second manual publication gate and no automatic production deploy.

Preparation previews and final product/MarkdownFlow notes are file-based. Final
notes use the highest reachable lower final tag at the frozen candidate, not
later main tags. Commitizen runs with `--start-rev` in a temporary local clone
checked out at the candidate, preserving breaking-change bodies and
candidate-specific note configuration without changing the caller's checkout or
local edits. Each rendered entry covers only its own change type, scope and
complete subject; sharing a PR number does not hide another omitted change.
Dependency lookups remain best-effort, with their existing registry-time window,
three-page scan and twenty-line detail limits. CI runs the local release tests
with mocked HTTP writes and real pinned Commitizen execution; it does not
perform real release operations as tests. Historical workflows, tags and
releases are not rewritten by this change.

## Pull request validation

Every explicit packaging input declared by `scripts/select_docker_checks.py`
must trigger both the ARM64 packaging workflow and the AMD64 runtime harness.
Regression tests read both workflows' path filters, including exclusions, so
release-workflow edits cannot silently lose one architecture's build and smoke
coverage.

The runtime harness builds `src/api/Dockerfile` and `src/web/Dockerfile` once with
Docker Bake on the same AMD64 runner and loads both final production images into
that runner's Docker engine. It runs the production-image smoke checks against
those exact images, including their default commands, before starting Compose
with `up --no-build` and running the browser smoke tests. The browser tests reuse
the same images instead of rebuilding them with a separate harness Dockerfile.

Compose applies the API migration and demo-seeding command for the integrated
test stack. Web keeps its production command and user, sets `PORT=5000` to match
the shared nginx route, and reads translations from `/app/i18n`. The image smoke
checks cover default startup independently of the API command override.

Ordinary application code, shared i18n, and production Markdown changes receive
this production AMD64 build, startup, and browser validation. Packaging-related
changes additionally select the affected service's native ARM64 build and smoke
check in Docker Packaging Checks. These include Dockerfiles, runtime dependency
manifests and locks, production dependency checks, and Docker build workflows
and scripts; changes shared by both images select both services.

Ordinary manual packaging dispatch still validates both services on both
architectures. Candidate publication, latest builds, and release builds also
retain both native architectures for both services. An ordinary application
change can therefore first expose an ARM64-specific failure in the main build;
a passing AMD64 runtime harness does not establish ARM64 compatibility or
successful registry publication.

## Acceptance and consumer pulls

Publishing builds use native AMD64 and ARM64 runners. Each final production image
is loaded, started and smoke-tested before digest publication. The same layers
are exported to every destination; their immutable config digest must match the
tested image.
Manifest publication preflights both architecture digests in every configured
repository before moving that service's final tags, and inspects every final tag.
There is no cross-service or cross-registry atomic transaction.

After public visibility is configured, verify from a Docker client with no GHCR
credentials:

```bash
docker pull ghcr.io/ai-shifu/ai-shifu-api:latest
docker pull ghcr.io/ai-shifu/ai-shifu-web:latest
```

The latest Compose bundle uses `aishifu/ai-shifu-api:latest` and
`aishifu/ai-shifu-web:latest`. The pinned release bundle retains its historical
Web image/tag until Prepare Release PR advances it in a manually merged version
PR; no historical tag is copied or republished under the new name. Compose service
and container identifiers stay stable so nginx routing is unaffected.

To use GHCR, supply a local Compose override for the API, both Celery services
and Web, or tag downloaded images locally under the bundle's image names.
For historical releases use the retained `ai-shifu-cook-web` package. Use one
identical version for all four application services; do not mix release and
latest images.

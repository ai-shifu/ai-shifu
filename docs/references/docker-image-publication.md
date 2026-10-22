---
title: Docker image publication
status: canonical
owner_surface: repository
last_reviewed: 2026-10-22
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
| Build and Deploy on Release | Published non-draft, non-prerelease release | Existing release tag rules | GHCR and configured mirrors |
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
original run so it retains its release event/tag; expired digest artifacts require
a full rerun. Do not create another release merely to backfill latest.

## PR-first release gates

`Prepare Release PR` accepts a final `vX.Y.Z` increase on main and creates only
`release/version-bump-<tag>`. Its version-file scope is the two npm manifests and
lock roots, the vendored engine version, and first-party pinned Compose images.
It does not create a formal tag, Release or deployment. AI/scripts must never
merge or enable auto-merge; a human reviews CI and manually merges into main.

`Prepare Merged Release Draft` runs on main pushes without changing latest or
production CICD/Drone configuration. It freezes the event SHA and compares the
primary Web version at `before` and `after`. No change or an initial absent
baseline skips. Invalid/decreasing versions, forced pushes, inconsistent npm /
engine / Compose versions, or missing exact merged-release-PR provenance fail.
The source must itself introduce the version increase; a batched push ending in
a later non-version commit is not silently substituted for the merge source.

The provenance guard requires a merged same-repository release branch targeting
main, an exact `merge_commit_sha`, no recorded `auto_merge`, and a non-bot merger.
It explicitly excludes the known `ai-shifu-bot` automation account even though
GitHub reports its type as `User`. **User metadata does not prove a physical
human**, and GitHub may clear auto-merge metadata after completion. Manual review
and repository branch/access policy remain necessary; these workflows do not
change settings or claim to fully attest a human action.

The draft helper pins the formal tag to that exact source (including peeled
annotated tags), never force-updates a tag, and creates a draft with explicit
`draft=true`, `prerelease=false`, and `make_latest=false`. Tag, target SHA, title,
source marker, source versions and pinned images must agree. It reads the exact
tag and Release back after writes. Same-source reruns retain human note edits;
public releases and conflicting targets fail closed without editing them.

A human separately reviews and Publishes in GitHub. Before release-image builds,
the published-event guard rechecks the source, tag, metadata, versions and PR
provenance, then supplies an immutable source SHA to both reusable image jobs.
An invalid premature publication therefore cannot quietly publish mislabeled
images through this new workflow. Historical workflow runs/tags are not rewritten
or retroactively protected; investigate an existing mismatch rather than moving
its tag or merging an old PR to catch up.

For interrupted new drafts, rerun the original main-push workflow so its event
commit stays frozen. An exact-source tag with no draft is recoverable; a tag or
Release mismatch requires manual investigation. Ref and Release writes are not
an atomic transaction. Never publish as part of retry/recovery. Preparation
previews and final product/MarkdownFlow notes are file-based; final notes use the
highest reachable lower final tag at the frozen candidate, not later main tags.
Dependency lookups remain best-effort, with their existing registry-time window,
three-page scan and twenty-line detail limits. CI runs the local release tests
with mocked HTTP writes; it does not perform real release operations as tests.

## Pull request validation

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

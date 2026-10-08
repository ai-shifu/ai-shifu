---
title: Docker image publication
status: canonical
owner_surface: repository
last_reviewed: 2026-10-08
---

# Docker image publication

GitHub Actions builds the public API and Web images from the repository root
using `src/api/Dockerfile` and `src/web/Dockerfile`. This path is independent
of the production CICD/Drone build and its deployment Dockerfiles.

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
| Docker Packaging Checks | Pull request or ordinary manual dispatch | Local validation name | No login or push |
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

## Acceptance and consumer pulls

AMD64 and ARM64 build on native runners. Each final production image is loaded,
started and smoke-tested before digest publication. The same layers are exported
to every destination; their immutable config digest must match the tested image.
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
Web image/tag until Prepare Release Draft advances it to a new release;
no historical tag is copied or republished under the new name. Compose service
and container identifiers stay stable so nginx routing is unaffected.

To use GHCR, supply a local Compose override for the API, both Celery services
and Web, or tag downloaded images locally under the bundle's image names.
For historical releases use the retained `ai-shifu-cook-web` package. Use one
identical version for all four application services; do not mix release and
latest images.

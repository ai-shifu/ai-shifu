---
title: Production Docker base images
status: active
owner_surface: cross-surface
last_reviewed: 2026-10-06
canonical: true
---

# Production Docker base images

The production [Web Dockerfile](../../src/web/Dockerfile) and
[API Dockerfile](../../src/api/Dockerfile) pin version tags to multi-platform
index digests. Both Web stages share one Node base index. The API builder and
runner retain their full and slim variants, with the same Python patch version.
These pins freeze the pulled filesystem and bundled runtime; package-manager
fetches remain governed by the existing installation steps.

## Verified inputs

On 2026-10-06 UTC, Docker Hub returned the following indexes. Each raw index's
SHA-256 matched its `Docker-Content-Digest` response header. Both Linux platform
manifests and their config blobs also matched their requested content digests.
The config blobs confirmed Node 22.16.0 and Python 3.11.17 on both architectures.
The existing `python:3.11` and `python:3.11-slim` tags resolved to exactly the same
indexes as `python:3.11.17` and `python:3.11.17-slim`; fixing the patch-version
labels did not select a newer image than the existing aliases.

| Image tag | Multi-platform index digest | Supported production platforms |
| --- | --- | --- |
| `node:22.16.0-alpine` | `sha256:41e4389f3d988d2ed55392df4db1420ad048ae53324a8e2b7c6d19508288107e` | `linux/amd64`, `linux/arm64` |
| `python:3.11.17` | `sha256:a12cfee69f94b70fc1d4b25003cd96705f129f383cdeb32090f060ae04d00ec8` | `linux/amd64`, `linux/arm64` |
| `python:3.11.17-slim` | `sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce` | `linux/amd64`, `linux/arm64` |

Use an index digest rather than a child platform digest: one Dockerfile remains
usable on both native runner architectures. Attestation descriptors with an
`unknown` platform do not satisfy either Linux architecture requirement.

## Updating a pin

1. Choose the intended runtime version and image variant explicitly. To refresh
   the filesystem while retaining the runtime version, resolve the current
   version tag. Change the runtime version only as an intentional update.
2. Inspect the candidate with `docker buildx imagetools inspect IMAGE:TAG` and
   record its top-level index digest. Inspect the raw index with
   `docker buildx imagetools inspect --raw IMAGE:TAG`; verify Linux AMD64 and ARM64
   child manifests. Inspect or pull each child digest and confirm its architecture
   and actual `NODE_VERSION` or `PYTHON_VERSION` from the image config. If starting
   from a floating minor-version alias, verify the corresponding exact-version
   tag resolves to the same index before using its version label.
3. Update every production `FROM` using the same input in one pull request. Keep
   Web builder and runner pins identical; keep API builder and runner Python
   versions aligned while preserving their full/slim variants. Retain the
   readable `TAG@sha256:...` form and update the evidence table above.
4. Run build-only checks on native AMD64 and ARM64 runners. Exercise the final
   Web runner's default command, runtime config endpoint, translation endpoint,
   static assets, Sharp image conversion and native SWC. Build the final API
   runner on each platform and verify its runtime imports, FFmpeg and service
   startup with the existing smoke environment. Record the tested commit and
   image digests before approving the pin update.
5. Run the repository harness and commit checks. Merge the focused update through
   a pull request after both platform checks pass. If a registry read or platform
   smoke fails, retain the existing pin until that failure is understood.

Review digest updates regularly so base-image fixes enter through a tested pull
request. [Docker's base-image guidance](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)
explains tag mutability and digest pinning.

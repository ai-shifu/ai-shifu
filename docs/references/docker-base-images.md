---
title: Production Docker base images
status: active
owner_surface: cross-surface
last_reviewed: 2026-10-21
canonical: true
---

# Production Docker base images

The production [Web Dockerfile](../../src/web/Dockerfile) and
[API Dockerfile](../../src/api/Dockerfile) pin version tags to multi-platform
index digests. Both Web stages share one Node base index. The API builder and
runner retain their full and slim variants, with the same Python patch version.
These pins freeze the pulled filesystem and bundled runtime. System CA packages
are explicitly upgraded after pulling, independently of the pinned image.

## Verified inputs

On 2026-10-06 UTC, Docker Hub returned the Python indexes below. Each raw index's
SHA-256 matched its `Docker-Content-Digest` response header. Both Linux platform
manifests and their config blobs also matched their requested content digests.
The Python config blobs confirmed Python 3.11.17 on both architectures.
The existing `python:3.11` and `python:3.11-slim` tags resolved to exactly the same
indexes as `python:3.11.17` and `python:3.11.17-slim`; fixing the patch-version
labels did not select a newer image than the existing aliases. On 2026-10-21 UTC,
the Node 22.23.4 Alpine 3.23 index and both Linux platform manifests/configs were
also verified against their content digests; each config reports Node 22.23.4.

| Image tag | Multi-platform index digest | Supported production platforms |
| --- | --- | --- |
| `node:22.23.4-alpine3.23` | `sha256:206878a60dc7014193f418ab9259b6110c15fbd514b3044a267be706509944e4` | `linux/amd64`, `linux/arm64` |
| `python:3.11.17` | `sha256:a12cfee69f94b70fc1d4b25003cd96705f129f383cdeb32090f060ae04d00ec8` | `linux/amd64`, `linux/arm64` |
| `python:3.11.17-slim` | `sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce` | `linux/amd64`, `linux/arm64` |

Use an index digest rather than a child platform digest: one Dockerfile remains
usable on both native runner architectures. Attestation descriptors with an
`unknown` platform do not satisfy either Linux architecture requirement.

## Independent trust stores

The eMudhra incident requires more than replacing an image tag. Both Node
stages inherit a shared trust stage that upgrades Alpine `ca-certificates` and
`ca-certificates-bundle` to at least `20261020-r0`; the pinned Node image still
contains an older system bundle. Node 22.23.4 updates the built-in roots.

The API preserves its Python image pins and upgrades system CA packages in
both stages. The minimum is `20250419~deb12u2` on Bookworm or
`20250419+deb13u1` on Trixie; comparing a package against another Debian
release's version does not prove it contains the fix. Before the first package
index request, hash-verified official wheels bootstrap pip `26.2.2` and certifi
`2026.10.19`. pip's vendored certifi is independent from the application package.
The application pin and post-install checks prevent a requirements install from
downgrading it. The runner removes old pip metadata before copying the builder's
packages and matching console scripts.

The final-image smoke reads the real Python system/certifi/pip trust sets and
Node bundled/default/system trust sets. It rejects affected root fingerprints
from the [incident root inventory](https://emudhra.we-have-a-problem.com/roots.json)
and requires ISRG Root X1 as a positive control. Offline tests inject a public
affected root into each store and require failure; they do not disable TLS or
reject unaffected emSign roots by name. Package sources are
[certifi on PyPI](https://pypi.org/project/certifi/2026.10.19/),
[pip on PyPI](https://pypi.org/project/pip/26.2.2/), and the
[Debian security advisory](https://lists.debian.org/debian-lts-announce/2026/10/msg00039.html).

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

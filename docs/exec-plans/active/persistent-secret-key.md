---
title: Generate and persist installation secret keys
status: active
owner_surface: cross-surface
last_reviewed: 2026-10-26
canonical: false
---

# Generate and persist installation secret keys

## Purpose / Big Picture

New installations should receive an independent authentication key without
asking an operator to invent or copy one. Provision the key once in the same
private environment file that all workers and containers already consume.
Preserve existing keys and the runtime's required-key validation. This change
is independent of administrator setup in PR #3183.

## Progress

- [x] 2026-10-26 CST: Read repository guidance and inspect configuration,
  templates, Docker modes, tests, and workflow consumers.
- [x] 2026-10-26 CST: Create an isolated managed worktree from remote main
  `4f366af485129a8b593321c4b247fe0bc8858973`.
- [x] 2026-10-26 CST: Implement private, atomic new-install configuration
  provisioning and preserve existing configurations.
- [x] 2026-10-26 CST: Align latest, development, pinned-release, and manual
  installation paths and their documentation.
- [x] 2026-10-26 CST: Verify concurrency, failure recovery, compatibility,
  configuration regressions, Compose rendering, and repository gates.
- [x] 2026-10-26 CST: Create ready PR #3186, independent of #3183.
- [x] 2026-10-26 CST: Fix the reviewed release-note installation path and
  validate both published notes and PR previews with 30 release regressions.
- [ ] 2026-10-26 CST: Follow the final review-fix head's CI to completion.

## Surprises & Discoveries

- The pinned v3.0.1 Compose file forces a public demonstration key, even when
  its `.env` contains a different value. Removing that override changes the
  effective key for existing deployments. It needs an explicit fresh-install
  overlay instead of an implicit migration.
- Latest and development Compose services already share one `.env` file.
  No new runtime store or per-process random fallback is necessary.
- Tests deliberately require missing and blank runtime keys to fail.
- Review identified a second official installation entry point in generated
  GitHub release notes. Both release publishers now receive the same installer,
  prerequisites, explicit pinned overlay, and existing-key migration boundary.
- Crash orphans use a reserved temporary-file prefix independent of output
  filenames. Git and both Docker build contexts exclude that namespace so
  interrupted initialization cannot leak a private key through later staging
  or image builds.
- Root and standalone Web Docker contexts also exclude final `.env` files
  recursively, including the manual backend's saved `src/api/.env`; a later
  image build must not copy the installation's key with application sources.
- The shared local Python environment contained older MarkdownFlow and dotenv
  versions. Tests use the repository-pinned `markdown-flow==0.4.2` and
  `python-dotenv==1.2.2` from an isolated temporary overlay; no shared
  environment was changed.
- Existing dotenv interpolation remains supported through established startup
  paths. Startup never invokes provisioning, and the development script fails
  before builds if configuration is absent. A lost existing configuration
  cannot be mistaken for an uninitialized installation during restart.

## Decision Log

- 2026-10-26: Generate at installation, not application import. A stdlib-only
  helper writes a fresh `.env` using secure randomness and no-clobber atomic
  publication. Runtime startup remains read-only and deterministic.
- 2026-10-26: Preserve every valid existing environment file byte-for-byte,
  including old weak keys; invalid existing files fail without repair. Rotation
  requires deliberate operator action because keys also protect encrypted data.
- 2026-10-26: Keep the legacy pinned Compose behavior and add a fresh-install
  overlay that requires the provisioned key for API, worker, and beat.
- 2026-10-26: Remove the pinned legacy `environment` key with Compose's
  `!reset` tag so the shared `env_file` wins over a conflicting shell value.
  Validate the exact tagged file with syntax-only YAML parsing locally and in
  lint CI; keep every other YAML file on the existing strict loader. Actual
  Compose merge tests cover the tag's semantics on 2.24.4 and 5.6.1.
- 2026-10-26: The dollar-key review report is an output-escaping false
  positive. Compose explicitly doubles dollars only when printing config;
  see [the official implementation](https://github.com/docker/compose/blob/v5.6.1/cmd/compose/config.go#L179-L195).
  Replaying the serialized model preserves its environment and service hash
  on Compose 5.6.1. Retain explicit dollar values and cover model round trips
  alongside the manual dotenv/JWT regression instead of rejecting valid keys.

## Outcomes & Retrospective

Local validation passed: 101 installer/Compose/packaging tests, all nine Compose
integration cases on both 2.24.4 and 5.6.1, 30 release workflow regressions,
and 595 backend
configuration/session/encryption regressions, strict mypy for the installer,
shell syntax, development-tool verification, architecture/harness validation,
and the all-files pre-commit gate. Independent review found no outstanding
introduced issue after fixing existing interpolated-config compatibility and
test/CI integration. Hosted acceptance remains to be recorded on the PR.
No deployment, production inspection, automatic merge, or modification of
another task's checkout is authorized or necessary.

## Context and Orientation

`scripts/prepare_env.py` provisions configuration from
`docker/.env.example.full`. The template comes from `ENV_VARS` in
`src/api/flaskr/common/config.py`. `app.py` loads dotenv before initializing
`Config`; `SECRET_KEY` remains required. Latest/development services consume
the host environment file via `env_file`. The pinned release's legacy
`x-environment` explicitly overrides its key.

## Plan of Work

1. Add a standalone installer and synthetic filesystem/subprocess regression
   tests. Do not access local credentials or start application services.
2. Remove the public key from newly generated templates. Wire the helper into
   documented installation and development paths, plus the pinned overlay.
3. Exercise focused regressions and all-files gates, create a focused ready
   PR, and inspect CI results for its exact commit.

## Concrete Steps

From the repository root, use the configured Python environment for:

```bash
python -m pytest scripts/test_prepare_env.py scripts/test_installation_config.py -q
python scripts/check_dev_tools.py
python scripts/check_repo_harness.py
python scripts/check_architecture_boundaries.py
lefthook run pre-commit --all-files
```

Use synthetic temporary directories for environment generation and Compose
rendering; never render real configuration or print actual key material.

## Validation and Acceptance

Prove independent random keys for separate new installations, stable reuse on
restart/upgrade, explicit-key priority on creation, unchanged existing values,
concurrent initializers converging on one complete file, private permissions,
no overwritten symlinks or malformed configuration, sanitized failure output,
and deterministic retry after pre-publication failure. Test each Docker mode
and manual dotenv consumption with synthetic configuration. Follow exact-head
CI to terminal states and distinguish local checks from hosted checks.

## Idempotence and Recovery

Rerunning provisioning validates and keeps an existing file. Never fill an
empty or missing key in an existing file; restore the original configuration
from backup. Crashes before publication can leave only private temporary
files under the reserved `.ai-shifu-env-init-` namespace; Git and Docker ignore
them. Rerun to finish. After publication, reuse the committed file even if
directory synchronization reports an error. Back up configuration with the
database and preserve it across upgrades and replicas.

## Interfaces and Dependencies

The installer uses Python's standard library and filesystem atomic link and
fsync guarantees on supported POSIX hosts. It adds no backend or frontend
dependency, runtime environment setting, database schema, administrator flow,
or analytics event. Pinned release support is opt-in via a Compose overlay.

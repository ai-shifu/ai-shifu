# Runtime Harness Fast Value Gate

## Purpose / Big Picture

The existing Runtime Harness starts the full local development stack, waits for API and all observability services, then runs three browser smoke checks. This provides broad local-stack confidence but makes every applicable pull request pay for Celery, Loki, Tempo, Prometheus, and Grafana even though the smoke suite only requires the API, frontend, database, Redis, and reverse proxy.

This plan delivers the first executable increment of the runtime-harness optimization proposal. It introduces a minimal Compose stack for the required pull-request gate, structured startup and health timeline artifacts, service-scoped failure diagnostics, and reusable authenticated Playwright state. The resulting default gate remains named `runtime-harness`, preserves the existing trigger intent, and verifies login, authenticated administration entry, and learner course entry while removing duplicate browser login work and unrelated service readiness from its critical path.

The full observability stack and asynchronous workers are not deleted. They remain part of the developer stack and are explicitly deferred to a subsequent deep-runtime/observability contract workflow. Deterministic provider-backed learner generation is also deferred: it needs a reviewed CI-only provider seam and must not be improvised in the browser suite.

## Progress

- [x] 2026-08-22T03:00:00Z: Inspected the current Runtime Harness workflow, Compose stack, browser smoke suite, and repository workflow rules.
- [x] 2026-08-22T03:10:00Z: Created this ExecPlan and selected a minimal, standalone Compose file rather than changing default local-development profiles.
- [x] 2026-08-22T03:45:00Z: Added reusable timeline and health-wait script with four focused standard-library tests.
- [x] 2026-08-22T03:47:00Z: Added the minimal API/web/MySQL/Redis/Nginx Compose configuration and wired it into the Runtime Harness workflow.
- [x] 2026-08-22T03:48:00Z: Extracted reusable phone login, added Playwright authenticated setup state, and changed read-only smoke assertions to reuse that state.
- [x] 2026-08-22T03:51:00Z: Regenerated knowledge documents and passed `lefthook run pre-commit --all-files` (all 20 checks).
- [x] 2026-08-22T03:55:00Z: Pushed branch and created PR #2643; the first remote run exposed a connection-reset retry defect in the new readiness helper.
- [x] 2026-08-22T04:03:00Z: Pushed retry fix; the minimal stack health check passed in the second remote run, which then exposed a shell-quoting error in Playwright version resolution.
- [x] 2026-08-22T04:09:00Z: Pushed the version-resolution fix and passed Runtime Harness run 32550726976 in 4m41s; it completed API/Web health checks, Playwright dependency setup, authentication setup, and all fast-value smoke scenarios.

## Surprises & Discoveries

- The current development Compose command keeps API startup coupled to the OTEL collector and starts all observability services and Celery workers by default. Re-profiling that file would change existing local developer behavior and create profile-dependent dependency rules, so the fast gate uses a new, explicit Compose definition.
- The current browser smoke tests duplicate the phone/OTP login flow for every scenario, while Playwright is configured with `fullyParallel: false`.
- The current runner cache setup separates API and Cook Web BuildKit cache scopes, but the default gate still has no durable, machine-readable breakdown of service readiness or scenario timing.
- Docker is unavailable in the implementation sandbox, so Compose execution and GitHub Actions wall-clock validation must be completed by the remote workflow; Prettier is used locally to parse the changed YAML files.
- The first remote Runtime Harness attempt reached the minimal stack health phase but encountered a transient `ConnectionResetError`; the readiness helper initially treated that startup race as fatal instead of retryable. The helper now records the error and keeps polling, with focused regression coverage.
- The second remote Runtime Harness attempt passed minimal-stack health checks. It then failed while resolving the Playwright version because nested double quotes reached Bash unescaped. The expression is now kept inside single quotes and is validated locally against the committed lockfile.

## Decision Log

- Decision: preserve the public workflow name and existing path filters. Rationale: branch protection and existing CI expectations should continue to see the same `runtime-harness` required check.
- Decision: add `docker-compose.runtime-harness.yml` instead of modifying the default development Compose service set. Rationale: the fast CI gate needs only a subset, while local developers retain the full observability-enabled stack unchanged.
- Decision: use one standard-library Python helper to record start/end events and wait for endpoints. Rationale: workflow shell loops currently hide which endpoint is slow; a shared helper produces deterministic JSON and GitHub job-summary output without introducing a new package dependency.
- Decision: use a Playwright setup project and persisted storage state. Rationale: it preserves an actual login assertion while removing repeated phone/OTP interactions from authenticated read-only scenarios.
- Decision: do not add browser-level generated-answer assertions in this increment. Rationale: CI has a placeholder API key; validating streaming generated content requires a reviewed deterministic LLM adapter and belongs in the next product-contract batch.

## Outcomes & Retrospective

The fast-gate implementation now includes a minimal Compose definition, an artifact-producing time-line helper, service-scoped compose logs/status, and Playwright storage-state reuse. Focused Python tests, TypeScript checking, Playwright test enumeration, YAML formatting validation, and `lefthook run pre-commit --all-files` passed. GitHub Actions run 32550726976 passed in 4m41s after the two targeted startup/workflow fixes recorded above. Its measured major phases were image build 105s, stack start 15s, endpoint readiness 45s, frontend test dependencies 36s, and fast-value browser smoke 32s. The baseline remains provisional because this is one successful post-change run, but the fast gate is now implemented and verified; deterministic generated-answer, observability-contract, and full deep-runtime work remain intentionally separate follow-ups.

## Context and Orientation

`.github/workflows/runtime-harness.yml` is the current GitHub Actions job. It builds `ai-shifu-api-dev` and `ai-shifu-cook-web-dev`, starts `docker/docker-compose.runtime-harness.yml`, records a timeline artifact, waits for API and web endpoints, and executes the Playwright setup plus smoke projects.

`docker/docker-compose.dev.yml` is the full local development stack. The new `docker/docker-compose.runtime-harness.yml` must use the same image tags and Nginx configuration but only defines the service names Nginx expects: `ai-shifu-api-dev`, `ai-shifu-cook-web-dev`, `ai-shifu-nginx-dev-dev`, `ai-shifu-mysql`, and `ai-shifu-redis`.

`scripts/harness/runtime_timeline.py` is the new standard-library CLI. Its `wait` command receives named endpoint specifications, appends attempt/ready events to a JSON artifact, writes a concise GitHub Actions summary when `GITHUB_STEP_SUMMARY` is present, and exits with diagnostics when a timeout occurs.

`src/cook-web/e2e/harness-auth.ts` owns the existing deterministic phone login helper. `auth.setup.ts` logs in once and writes storage state under Playwright output. `smoke.spec.ts` retains authenticated product-entry assertions. `playwright.config.ts` creates an explicit setup project and the dependent smoke project.

## Plan of Work

First, create the ExecPlan and the timeline utility with isolated automated checks. Second, use the timeline helper to make image-build, stack-start, endpoint readiness, dependency installation, and browser-run timing visible. Third, move the default runtime gate to a minimal Compose stack; the deep stack remains preserved in the current development Compose configuration. Fourth, make browser authentication a setup dependency so read-only assertions can run with independent contexts and later be safely parallelized. Fifth, run local static validation and commit the change on a dedicated branch.

## Concrete Steps

1. Create `scripts/harness/runtime_timeline.py` with `mark`, `wait`, and `summary` subcommands. Make output path configurable, keep JSON output atomic, and avoid shell-specific parsing.
2. Add focused tests for timestamped event recording, successful endpoint readiness, and endpoint timeout reports using a local HTTP server.
3. Add `docker/docker-compose.runtime-harness.yml` with the API, Cook Web, Nginx, MySQL, and Redis configuration necessary for existing smoke paths. Do not attach source mounts, reload flags, Celery, or observability services.
4. Update `runtime-harness.yml` to use the minimal Compose file, create `artifacts/runtime-harness`, record each phase, wait for API and web endpoints using the helper, record Compose status/logs, and upload the timeline with existing test artifacts.
5. Extract the phone login routine to `e2e/harness-auth.ts`, add `e2e/auth.setup.ts`, and configure setup + smoke projects with generated storage state. Retain an explicit assertion that setup reaches the authenticated admin route.
6. Run focused tests and structural checks. Update Progress and Outcomes with exact commands and any Docker limitation. Regenerate knowledge docs if the harness/index check requires it.

## Validation and Acceptance

- `python -m pytest scripts/harness/tests/test_runtime_timeline.py` proves that event writes, healthy endpoints, timed-out endpoints, request-deadline handling, and interval validation create the expected timeline schema.
- `docker compose -f docker/docker-compose.runtime-harness.yml config` validates the minimal Compose file when Docker is available.
- The workflow YAML parses and contains the original pull-request/push path filters, `runtime-harness` job name, the minimal Compose path, and the uploaded timeline artifact.
- `cd src/cook-web && npm run type-check` accepts the Playwright setup/state configuration. **Passed locally on 2026-08-22.**
- `python scripts/check_repo_harness.py` and `python scripts/check_architecture_boundaries.py` remain green after generated knowledge documents are refreshed.
- GitHub Actions run 32550726976 is the final acceptance evidence for this increment: it preserved login, authenticated administration, learner entry, and zero-5xx browser assertions while no longer waits for Grafana/Loki/Tempo/Prometheus/Celery. It completed successfully in 4m41s.

## Idempotence and Recovery

The timeline script creates or appends to a configured JSON file; repeated `mark` commands produce additional explicit events rather than corrupting prior data. The workflow removes only its named Compose project during cleanup. The new Compose file has a distinct purpose and does not modify `docker-compose.dev.yml`, so reverting the workflow change restores the former full-stack gate without affecting local development. The Playwright authentication file is generated under test output and is not committed.

## Interfaces and Dependencies

The implementation depends on Python standard-library modules, Docker Compose, GitHub Actions, Playwright, the existing deterministic phone verification configuration, the current API and Cook Web image tags, and `docker/nginx.dev.conf`. It does not change public HTTP APIs, database schemas, credentials, provider routing, or production Compose files.

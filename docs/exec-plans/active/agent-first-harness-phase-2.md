# Agent-First Harness Phase 2

This ExecPlan is a living document and must stay aligned with `PLANS.md`.

## Purpose / Big Picture

Upgrade the repository from the first-wave agent-first harness to a second-wave
setup where repository governance, architecture boundaries, default local
observability, browser smoke validation, and recurring harness gardening are
all explicit, versioned, and mechanically enforced.

## Progress

- [x] 2026-04-17 18:40 CST: Audited the current harness state, confirmed the
  existing knowledge/docs layout, and identified the major remaining gaps:
  missing CI-first harness gates, no executable architecture-boundary checker,
  no default local observability stack, and no scheduled doc/debt gardening.
- [x] 2026-04-17 18:55 CST: Added Phase 2 knowledge docs, boundary rules, and
  baseline-aware architecture checker.
- [x] 2026-04-17 19:20 CST: Upgraded the default Docker dev stack with
  observability services and backend instrumentation.
- [x] 2026-04-17 19:45 CST: Extended smoke diagnostics, added CI workflows, and
  generate the harness health report.
- [x] 2026-04-17 20:10 CST: Ran generators/checks/tests, updated knowledge
  indexes, and documented final outcomes.

## Surprises & Discoveries

- Observation: the repository already completed a meaningful Phase 1
  migration, including ExecPlans, generated knowledge indexes, Playwright
  smoke tests, and request-id diagnostics.
  Evidence: `docs/design-docs/agent-first-harness.md`,
  `docs/exec-plans/completed/agent-first-harness-migration.md`,
  `scripts/check_repo_harness.py`, and `src/cook-web/e2e/smoke.spec.ts`.
- Observation: the control plane is stronger than the runtime plane.
  Knowledge docs, generated mirrors, and `pre-commit` exist, but the default
  CI workflows do not yet treat repo-harness and runtime-harness as first-class
  jobs.
  Evidence: `.github/workflows/` contains backend/contract/format/translation
  jobs but no repo-harness or runtime-harness workflow.
- Observation: the default Docker dev stack still fails before the smoke suite
  can go green because migration `6b603528dac8_add_system_profile.py` imports
  runtime helpers that no longer exist.
  Evidence: the migration imports `add_profile_i18n`, which no longer exists in
  `src/api/flaskr/service/profile/profile_manage.py`.
- Observation: the current architecture guidance is mostly documentary.
  The repo has path-scoped AI instructions, but no executable boundary checker
  for frontend route coupling, backend cross-service imports, or new direct
  request paths.
  Evidence: the frontend ESLint config has general rules only, and the backend
  has no architecture-assertion script in `scripts/` or CI.
- Observation: OTEL traces initially failed even after the observability stack
  was added because the collector defaulted to `localhost` listeners inside the
  container.
  Evidence: the collector logs showed `endpoint: "localhost:4318"` and Tempo
  returned 404 for fresh request traces until the receiver endpoints were
  pinned to `0.0.0.0`.
- Observation: the default dev `.env` drifts toward Google-only login, which
  breaks deterministic smoke auth even though the harness expects phone login
  plus the universal verification code.
  Evidence: `docker/.env` overrides `LOGIN_METHODS_ENABLED=google`, and the
  login page rendered only the Google button until `docker-compose.dev.yml`
  pinned phone login for the dev harness.
- Observation: once phone login was restored, the browser smoke suite still
  flaked because repeated `send_sms_code` requests hit the existing SMS rate
  limit while the universal verification code remained valid.
  Evidence: request-scoped diagnostics for
  `pw-1776419058232-admin-operations-page-loads` and
  `pw-1776419075062-learner-chat-shell-renders-and-c` captured
  `/api/user/send_sms_code` responses with `{"code":9999,"message":"SMS sent too frequently"}`.

## Decision Log

- Decision: keep the Phase 2 boundary checker language-agnostic and
  repository-local by implementing it in Python with AST and static import
  scanning.
  Rationale: this keeps the rules legible to agents, avoids adding another
  language-specific lint tool, and allows a single baseline file to govern both
  backend and frontend.
  Date/Author: 2026-04-17 / Codex
- Decision: preserve migration history and fix the failing legacy migration via
  compatibility behavior in current runtime helpers instead of rewriting the
  migration file itself.
  Rationale: existing migration history may already be applied elsewhere; the
  safer compatibility move is to restore the expected legacy helper behavior.
  Date/Author: 2026-04-17 / Codex
- Decision: keep `Langfuse` for LLM-specific traces and add a separate local
  runtime observability stack for generic logs, metrics, and HTTP traces.
  Rationale: the repository already depends on Langfuse semantics for learning
  flows; Phase 2 needs complementary runtime visibility rather than a tracing
  replacement.
  Date/Author: 2026-04-17 / Codex
- Decision: make the default dev stack include observability services, but keep
  release/latest compose files unchanged.
  Rationale: the user explicitly chose the full-closure path, and the Phase 2
  scope is local development and harness diagnostics, not production deployment.
  Date/Author: 2026-04-17 / Codex
- Decision: pin the dev harness to phone login in `docker-compose.dev.yml`
  instead of relying on the mutable shared `.env`.
  Rationale: the browser smoke suite depends on deterministic auth, and the dev
  harness should not inherit unrelated OAuth-focused overrides from shared
  local configuration.
  Date/Author: 2026-04-17 / Codex
- Decision: treat SMS rate limiting as a recoverable UI state in phone login
  and keep the OTP entry path available when the backend reports
  `smsSendTooFrequent`.
  Rationale: the previous code is still valid, the universal verification code
  remains usable in dev, and disabling OTP entry made both smoke automation and
  real user retry flows unnecessarily brittle.
  Date/Author: 2026-04-17 / Codex

## Outcomes & Retrospective

- Added the Phase 2 control-plane assets:
  `docs/design-docs/agent-first-harness-phase-2.md`,
  `docs/references/architecture-boundaries.md`,
  `docs/generated/harness-health.md`,
  `docs/generated/harness-gardening-summary.md`, and the active ExecPlan.
- Added `scripts/check_architecture_boundaries.py`, fixture coverage, a
  committed baseline, `pre-commit` wiring, and the new repo/runtime/gardening
  workflows.
- Upgraded `docker/docker-compose.dev.yml` into the default observability
  harness with Grafana, Loki, Tempo, Prometheus, the OTEL collector, and
  Promtail while keeping release/latest compose files unchanged.
- Added backend request-scoped traces, HTTP metrics, stable structured log
  fields, and richer `harness_diagnostics.py` summaries that include
  Loki/Tempo/Prometheus/Grafana hints.
- Restored default dev boot by adding a self-healing migration residue repair
  step and compatibility behavior for the legacy profile migration path.
- Verified end-to-end request correlation with `X-Request-ID`, `trace_id`,
  Loki matches, Tempo trace lookup, and Prometheus request metrics in the live
  dev stack.
- Restored deterministic browser smoke by pinning phone login in the dev
  harness and allowing OTP entry to continue when SMS sending is rate-limited.

## Context and Orientation

Phase 1 already established the repository knowledge model, root architecture
map, ExecPlan workflow, Playwright smoke suite, and request-id diagnostics.
Phase 2 must add four missing control systems without changing public product
contracts:

- CI-first repo harness governance
- baseline-aware executable boundary checks
- default local observability for the dev stack
- scheduled harness gardening and health reporting

The most delicate runtime blocker is the failing legacy migration in the backend
startup path, which currently prevents the smoke suite from going green in the
default Docker dev stack.

## Plan of Work

1. Add the Phase 2 design docs, reference docs, and generated health-report
   plumbing so the change has a versioned source of truth.
2. Implement a baseline-aware architecture checker and wire it into
   `pre-commit`, repo-harness validation, and CI.
3. Add backend observability primitives plus a Docker dev observability stack.
4. Upgrade smoke diagnostics and add repo/runtime/gardening GitHub workflows.
5. Regenerate docs, run focused validation, and update this ExecPlan with the
   final outcomes.

## Concrete Steps

- Add `docs/design-docs/agent-first-harness-phase-2.md`.
- Add an evergreen boundary reference under `docs/references/`.
- Add `scripts/check_architecture_boundaries.py` plus fixture data and a
  committed baseline file under `docs/generated/`.
- Extend `scripts/build_repo_knowledge_index.py` and
  `scripts/check_repo_harness.py`.
- Add backend compatibility fixes, metrics/tracing support, and expanded
  diagnostics.
- Add observability config files under `docker/observability/`.
- Update `docker/docker-compose.dev.yml`, smoke diagnostics, and GitHub
  workflows.

## Validation and Acceptance

- `python scripts/generate_ai_collab_docs.py`
- `python scripts/build_repo_knowledge_index.py`
- `python scripts/check_repo_harness.py`
- `python scripts/check_architecture_boundaries.py --run-fixture-tests`
- `cd docker && docker compose -f docker-compose.dev.yml config`
- `cd src/cook-web && npm run test:e2e`

## Idempotence and Recovery

The knowledge generators, boundary baseline, and health report must be
deterministic for a fixed repository state. If the default runtime harness still
cannot go green after the compatibility fix, the final summary must say whether
the blocker is migration-related, environment-related, or caused by the new
observability stack.

The final validated state is:

- request-scoped logs, metrics, and traces resolve for the same request in the
  default dev stack;
- `python scripts/check_repo_harness.py` passes;
- `python scripts/check_architecture_boundaries.py --run-fixture-tests` passes;
- `cd src/cook-web && npm run test:e2e` passes against the default dev stack.

## Interfaces and Dependencies

- `docs/generated/architecture-boundary-baseline.json` becomes the committed
  baseline for existing boundary violations.
- `docs/generated/harness-health.md` becomes the generated high-level health
  report for the harness control plane.
- `scripts/check_architecture_boundaries.py` becomes a new repo-level check.
- `docker/docker-compose.dev.yml` gains local observability services only.
- `.github/workflows/repo-harness.yml`,
  `.github/workflows/runtime-harness.yml`, and
  `.github/workflows/harness-gardening.yml` become new harness workflows.

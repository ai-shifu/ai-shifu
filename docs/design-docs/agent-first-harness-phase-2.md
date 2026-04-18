---
title: Agent-First Harness Phase 2
status: implemented
owner_surface: repo
last_reviewed: 2026-04-17
canonical: true
---

# Agent-First Harness Phase 2

## Summary

Extend the repository from the first-wave agent-first harness to a second-wave
setup where repo governance, executable architecture boundaries, default local
observability, and recurring harness gardening are all versioned and enforced.

## Goals

- Promote repo-harness validation from local-only hygiene to CI-first gating.
- Add a baseline-aware architecture checker for frontend and backend boundary
  drift.
- Upgrade the default Docker dev stack into an observability-enabled harness.
- Add recurring doc-gardening and debt-gardening automation plus a generated
  health report.

## Constraints

- Keep public HTTP APIs, business database contracts, and shared i18n contracts
  unchanged.
- Keep `AGENTS.md` navigation-first; new durable knowledge must live in
  `docs/` and generated artifacts.
- Keep `docker-compose.latest.yml` and pinned release compose unchanged.
- Preserve existing Langfuse flows and add complementary runtime visibility
  instead of replacing them.

## Decisions

### Harness governance

- Add a new active ExecPlan for Phase 2 and treat it as the implementation
  source of truth.
- Extend the generated knowledge system with a committed harness health report.
- Make `scripts/check_repo_harness.py` aware of new workflows, docs, and
  generated harness assets.

### Architecture boundaries

- Implement a single Python checker for both backend and frontend boundaries.
- Use a committed baseline file so existing debt is frozen and only new
  violations fail normal checks.
- Keep the first-wave backend allowlist intentionally small:
  `common`, `config`, and stable DTO/model/const entry points.
- Keep the first-wave frontend route rule intentionally narrow:
  new route-internal coupling across `src/app/**` is disallowed, and new
  `src/components/** -> src/app/**` dependencies are blocked.

### Runtime observability

- Default local dev includes Grafana, Loki, Tempo, Prometheus, an OTEL
  collector, and a log shipper.
- Backend runtime traces are request-scoped and carry `X-Request-ID` as a
  stable attribute.
- HTTP metrics are exported from the backend via a local metrics endpoint
  scraped by Prometheus.
- Existing file logs stay in place and gain stable request/trace/status/duration
  fields so Promtail can ship them without changing local workflows.
- The default dev compose must pin phone login for deterministic smoke runs,
  regardless of optional OAuth overrides in shared local `.env` files.
- Default API boot must repair the known legacy migration residue before
  rerunning Alembic so the harness can recover from non-transactional schema
  drift.

### Gardening

- Add a scheduled/manual GitHub workflow that scans for stale docs, retired
  workflow terms, and stale boundary baseline entries.
- Regenerate the harness health report during gardening runs and open a GitHub
  issue when drift is detected.

## Deliverables

- Active ExecPlan and Phase 2 design/reference docs
- `scripts/check_architecture_boundaries.py` plus fixtures and baseline
- Generated `docs/generated/harness-health.md`
- Default dev observability stack and expanded backend diagnostics
- Repo-harness, runtime-harness, and harness-gardening GitHub workflows

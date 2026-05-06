# Agent-First Harness Migration

This ExecPlan is a living document and must stay aligned with `PLANS.md`.

## Purpose / Big Picture

After this change, repository knowledge, complex execution planning, and the
minimum browser-plus-log validation loop will all be discoverable and
mechanically enforced from inside the repository. A contributor should be able
to find the architecture map, follow the current execution-plan workflow, run
the generated indexes, and validate a smoke failure with a request id.

## Progress

- [x] 2026-04-17 16:10 CST: Created the initial migration design doc and
  temporary root checklist required by the pre-migration rules.
- [x] 2026-04-17 16:12 CST: Reorganized the knowledge docs and added the new
  root source-of-truth documents.
- [x] 2026-04-17 16:13 CST: Updated AI entry points, generated compatibility
  docs, and the repository harness checker.
- [x] 2026-04-17 16:14 CST: Added Playwright smoke coverage, request-id
  diagnostics, and failure-artifact capture.
- [x] 2026-04-17 16:14 CST: Regenerated repository knowledge indexes,
  exercised the minimum runtime harness, documented the discovered backend
  blocker, and retired repository-root `tasks.md`.

## Surprises & Discoveries

- Observation: the repository already had a mature layered AI-doc system, but
  it still centered the workflow on `tasks.md`.
  Evidence: root `AGENTS.md`, `docs/README.md`, and generated compatibility
  docs all routed complex work through the retired checklist flow.
- Observation: the minimum smoke harness worked on the first pass as a
  diagnostics loop even though the happy path stayed red.
  Evidence: Playwright emitted `failure.png`, `harness-diagnostics.json`, and
  `trace.zip`, and the diagnostics bundle captured `GET /api/runtime-config`
  plus auth endpoints returning `502` together with the final `X-Request-ID`.
- Observation: the local Docker dev stack currently fails before the login
  flow can complete because backend startup is blocked by a migration import.
  Evidence: `docker compose -f docker-compose.dev.yml logs ai-shifu-api-dev`
  showed `ImportError: cannot import name 'add_profile_i18n'` from
  migration `6b603528dac8_add_system_profile.py`, matching the browser smoke
  failures that left the OTP input disabled.
- Observation: request-scoped diagnostics still provide a usable fallback when
  Langfuse is not configured.
  Evidence: `python scripts/harness_diagnostics.py --request-id <id>` reported
  `mode: local-log-only` and scanned the backend file logs without requiring
  extra infrastructure.

## Decision Log

- Decision: keep `docs/engineering-baseline.md` at the root of `docs/` rather
  than moving it into `docs/references/`.
  Rationale: the current repository and existing docs already treat it as the
  canonical engineering handbook, and the migration plan explicitly keeps that
  path stable.
  Date/Author: 2026-04-17 / Codex
- Decision: treat the first-wave runtime harness as Playwright plus
  request-id diagnostics, not as a full local observability stack.
  Rationale: the migration goal was the smallest closed loop that keeps UI
  failures agent-legible without widening operational scope.
  Date/Author: 2026-04-17 / Codex
- Decision: record the backend migration crash as a surfaced blocker instead
  of expanding this change to fix unrelated backend startup issues.
  Rationale: the user explicitly scoped this wave to repository structure and
  harness plumbing without changing HTTP APIs, database contracts, or taking
  on a broader reliability remediation project.
  Date/Author: 2026-04-17 / Codex

## Outcomes & Retrospective

- Completed the repository-knowledge migration by adding `ARCHITECTURE.md`,
  `PLANS.md`, `docs/QUALITY_SCORE.md`, `docs/RELIABILITY.md`, and
  `docs/SECURITY.md`, reorganizing flat docs into design/product/reference
  buckets, and generating indexes plus a repository inventory.
- Completed the governance migration by shrinking root/backend/frontend
  `AGENTS.md` files into table-of-contents entry points, updating generated
  compatibility surfaces, introducing `scripts/check_repo_harness.py`, and
  retiring repository-root `tasks.md` in favor of ExecPlans.
- Completed the minimum runtime harness by adding Playwright smoke coverage,
  failure-artifact capture, and backend request-id diagnostics that work with
  either Langfuse trace hints or local file logs.
- Remaining gap: the new browser harness is mechanically wired and produces
  actionable diagnostics, but the local Docker dev stack is still blocked by a
  pre-existing backend migration import error that returns `502` on the login
  path. Making the smoke suite green now depends on fixing that backend issue
  in a follow-up task.

## Context and Orientation

The repository currently contains flat topic docs under `docs/`, hand-written
root/backend/frontend `AGENTS.md` files, a generator for compatibility
surfaces, and a checker focused on the existing AI-doc layout. The migration
adds a knowledge hierarchy, moves complex work to ExecPlans, and introduces a
minimum runtime harness without changing product contracts.

## Plan of Work

Create the root architecture and plan docs, move the flat docs into the new
knowledge directories, add metadata and generated indexes, update manual and
generated instruction entry points, replace the old checker with a unified
repo harness checker, then add Playwright smoke coverage and a backend
diagnostics script.

## Concrete Steps

- Reorganize `docs/` and add the new root docs.
- Add metadata to `docs/design-docs/*.md` and `docs/product-specs/*.md`.
- Generate indexes and inventory files from the new structure.
- Update `AGENTS.md`, `src/api/AGENTS.md`, and `src/cook-web/AGENTS.md`.
- Add `scripts/check_repo_harness.py` and make
  `scripts/check_ai_collab_docs.py` a compatibility wrapper.
- Add Playwright config, smoke tests, and backend request-id diagnostics.

## Validation and Acceptance

- `python scripts/generate_ai_collab_docs.py`
- `python scripts/build_repo_knowledge_index.py`
- `python scripts/check_repo_harness.py`
- `cd src/cook-web && npm run test:e2e`

## Idempotence and Recovery

The generated docs and indexes must remain deterministic so rerunning the
generation scripts produces no diff. If the smoke suite cannot run because the
local dev stack is unavailable, the validation summary must say so explicitly.

## Interfaces and Dependencies

- `PLANS.md` becomes the only complex-work execution-plan spec.
- `docs/generated/doc-inventory.md` and generated index pages are build
  artifacts owned by `scripts/build_repo_knowledge_index.py`.
- `scripts/check_repo_harness.py` becomes the standard harness validator.
- `@playwright/test` provides the browser smoke harness in `src/cook-web`.

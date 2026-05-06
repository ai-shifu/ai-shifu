# AI-Shifu Architecture Map

## Purpose

This document is the top-level map for humans and coding agents. It explains
where repository knowledge lives, how the main product surfaces relate to one
another, and which files act as the source of truth for design, execution, and
validation.

## System Surfaces

- `src/api/`: Flask backend, service modules, persistence, provider
  integration, shared backend tests, and backend maintenance scripts.
- `src/cook-web/`: Next.js frontend for learner flows, admin/operator tools,
  authoring, and shared frontend tests.
- `src/i18n/`: Shared translation inventory consumed by backend and frontend.
- `docker/`: Local dev, latest-image, and pinned-release runtime packaging.
- `scripts/`: Repository maintenance, generation, and validation scripts.
- `.github/`: CI, release automation, issue templates, and Copilot
  compatibility instructions.

## Repository Knowledge Model

- `AGENTS.md`: directory-level entry points and hard constraints
- `PLANS.md`: the canonical ExecPlan specification
- `docs/engineering-baseline.md`: stable engineering handbook
- `docs/design-docs/`: implementation and architecture decisions
- `docs/product-specs/`: product and workflow behavior specs
- `docs/references/`: evergreen references and operational guides
- `docs/exec-plans/active/`: current complex work tracked as living ExecPlans
- `docs/exec-plans/completed/`: archived execution plans
- `docs/generated/`: generated knowledge indexes and inventories
- `docs/generated/harness-health.md`: generated summary of harness assets and
  boundary baseline state

## Runtime Flow

### Backend

- HTTP traffic enters the Flask app in `src/api/app.py`.
- Shared request logging and request-id propagation live in
  `src/api/flaskr/common/log.py`.
- Langfuse tracing helpers live in `src/api/flaskr/api/langfuse.py`.
- Business behavior is grouped under `src/api/flaskr/service/<module>/`.

### Frontend

- Route entrypoints live in `src/cook-web/src/app/**/page.tsx`,
  `layout.tsx`, and `route.ts`.
- Shared request transport and business-code handling live in
  `src/cook-web/src/lib/request.ts` and `src/cook-web/src/lib/api.ts`.
- Legacy `c-*` paths remain active compatibility surfaces and must still be
  treated as maintained code.

## Harness Model

- Repository knowledge must be discoverable from versioned files instead of
  chat history or unwritten conventions.
- Complex work is tracked in ExecPlans, not in ad-hoc branch notes.
- Generated indexes and validation scripts make drift visible and fail fast.
- Architecture boundary drift is frozen in a committed baseline and checked by
  `scripts/check_architecture_boundaries.py`.
- Browser smoke tests plus request-id diagnostics provide the minimum agent
  validation loop for UI work.
- The default Docker dev stack now includes local observability services so
  runtime failures can be correlated across logs, traces, and metrics.

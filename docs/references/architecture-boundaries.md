# Architecture Boundaries

This document defines the first-wave executable architecture boundaries enforced
by `python scripts/check_architecture_boundaries.py`.

## Purpose

- Freeze existing architectural debt in a committed baseline.
- Fail new cross-boundary drift early in local development and CI.
- Keep the rules explicit and legible to coding agents.

## Frontend Rules

### Route locality

- Files under `src/cook-web/src/app/**` may import route-local implementation
  files under the same top-level route scope.
- New imports from one top-level route scope into another top-level route scope
  are disallowed.
- Shared code should live under `src/components/`, `src/hooks/`, `src/store/`,
  `src/lib/`, `src/config/`, `src/types/`, `src/api/`, or maintained `c-*`
  compatibility layers instead of inside route directories.

### Components must not depend on route internals

- Files under `src/cook-web/src/components/**` must not add new imports from
  `src/cook-web/src/app/**` route-internal implementation files.
- Existing violations are tracked in
  `docs/generated/architecture-boundary-baseline.json` until they are migrated
  into shared layers.

### Request-path guardrail

- New direct `fetch(...)` call sites are only allowed in the existing request
  transport and bootstrap files:
  - `src/cook-web/src/lib/request.ts`
  - `src/cook-web/src/lib/api.ts`
  - `src/cook-web/src/lib/file.ts`
  - `src/cook-web/src/lib/initializeEnvData.ts`
  - `src/cook-web/src/lib/mock-fixture.ts`
  - `src/cook-web/src/lib/unified-i18n-backend.ts`
  - `src/cook-web/src/config/environment.ts`
- New fetch-based request paths elsewhere are treated as architectural drift.

## Backend Rules

### Service modules must not depend on root routes

- Files under `src/api/flaskr/service/**` must not import `flaskr.route.*`
  unless the file itself is a route adapter named `route.py` or `routes.py`.
- Service route adapters may import `flaskr.route.common` to reuse the shared
  response envelope and auth bypass helpers.

### Route adapters are not public service APIs

- No module outside a service route adapter may import another service's
  `route.py` or `routes.py`.
- Cross-service behavior should depend on service helpers, shared DTOs/models,
  or shared `common` / `config` utilities instead.

### Cross-service imports are baseline-governed

- Cross-service imports are allowed without review only when the target service
  is `common` or `config`.
- Stable shared entry points such as `.dtos`, `.models`, and `.consts` are
  treated as lower-risk and are not flagged by the first-wave checker.
- Other cross-service imports are tracked via the committed baseline and new
  additions fail normal checks.

## Baseline Rules

- The committed baseline file is
  `docs/generated/architecture-boundary-baseline.json`.
- Existing violations listed there do not fail a normal run.
- New violations fail the check.
- Stale baseline entries are reported separately and are intended to be cleaned
  up by the harness-gardening workflow.

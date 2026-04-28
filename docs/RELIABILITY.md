# Reliability

## Goals

- Keep repository knowledge current and mechanically validated.
- Keep request-level diagnostics usable for backend and browser smoke failures.
- Prefer small, repeatable validation loops over large manual QA checklists.

## Current Reliability Loop

- Generated instruction and knowledge indexes must be deterministic.
- `python scripts/check_repo_harness.py` validates documentation ownership,
  generated artifacts, and metadata completeness.
- `python scripts/check_architecture_boundaries.py` freezes current boundary
  debt and fails new architectural drift.
- `cd src/cook-web && npm run test:e2e` validates the browser smoke paths.
- The default dev harness pins phone login for smoke determinism even when the
  shared local `.env` contains other auth overrides.
- Playwright smoke failures must emit a screenshot, console/network summary,
  trace, and the final `X-Request-ID`.
- `cd src/api && python scripts/harness_diagnostics.py --request-id <id>`
  narrows failures to request-scoped backend evidence and local observability
  queries when the dev stack is available.
- Default API boot repairs known legacy migration residue before rerunning
  Alembic so the Docker dev harness can reach a green steady state.

## Known Limits

- The local observability stack exists only in the default Docker dev harness;
  latest/release compose files intentionally stay unchanged.
- Playwright smoke coverage intentionally stays narrow and should not be
  treated as full regression coverage.
- Some flows still depend on seeded demo data and the default Docker dev
  environment.
- Boundary baseline entries represent known debt and are expected to shrink
  gradually instead of being removed in one large refactor.

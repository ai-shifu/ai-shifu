# Reliability

## Goals

- Keep repository knowledge current and mechanically validated.
- Keep request-level diagnostics usable for backend and browser smoke failures.
- Prefer small, repeatable validation loops over large manual QA checklists.

## Current Reliability Loop

- Generated instruction and knowledge indexes must be deterministic.
- `python scripts/check_repo_harness.py` validates documentation ownership,
  generated artifacts, and metadata completeness.
- `cd src/cook-web && npm run test:e2e` validates the browser smoke paths.
- Playwright smoke failures must emit a screenshot, console/network summary,
  trace, and the final `X-Request-ID`.
- `cd src/api && python scripts/harness_diagnostics.py --request-id <id>`
  narrows failures to request-scoped backend evidence.

## Known Limits

- The repository does not yet provide a full local metrics/logs/traces stack.
- Playwright smoke coverage intentionally stays narrow and should not be
  treated as full regression coverage.
- Some flows still depend on seeded demo data and the default Docker dev
  environment.
- The current Docker dev stack can fail before smoke completion because the
  backend migration path imports runtime service code during startup.

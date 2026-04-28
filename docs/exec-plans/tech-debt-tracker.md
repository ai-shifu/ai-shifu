# Tech Debt Tracker

## Purpose

Track small, recurring cleanup work that improves agent legibility and keeps
the repository from drifting into inconsistent patterns.

## Current Debt

- Convert remaining historical references to the retired `tasks.md` workflow
  into `PLANS.md` / ExecPlan language when those files are next touched.
- Shrink `docs/generated/architecture-boundary-baseline.json` steadily rather
  than allowing new frontend/backend drift to accumulate.
- Keep the default observability-enabled dev stack healthy and revisit only if
  maintenance cost outweighs debugging leverage.
- Expand the browser harness only after the three baseline smoke paths stay
  stable in local development.

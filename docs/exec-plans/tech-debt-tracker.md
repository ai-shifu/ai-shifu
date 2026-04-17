# Tech Debt Tracker

## Purpose

Track small, recurring cleanup work that improves agent legibility and keeps
the repository from drifting into inconsistent patterns.

## Current Debt

- Convert remaining historical references to the retired `tasks.md` workflow
  into `PLANS.md` / ExecPlan language when those files are next touched.
- Expand the browser harness only after the three baseline smoke paths stay
  stable in local development.
- Decouple the failing backend startup migration from runtime service imports
  so the default Docker dev stack can pass the new smoke suite.
- Reassess whether a richer local observability stack is justified after the
  request-id diagnostics workflow has been used on real failures.

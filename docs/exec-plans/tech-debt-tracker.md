# Tech Debt Tracker

## Purpose

Track small, recurring cleanup work that improves agent legibility and keeps
the repository from drifting into inconsistent patterns.

## Current Debt

- Backend inventory 2026-07 (see
  `active/backend-inventory-2026-07.md`): 213 scattered
  `db.session.commit()` sites (worst: billing/renewal.py 25), 120
  hand-written `__json__` serializers, 3 identical pagination helpers,
  ~14 in-package env reads bypassing `common/config.py`, 7 endpoints with no
  known consumer, and a cook-web catalog entry (`markFavoriteShifu`) pointing
  at a non-existent backend route. Consumed batch-by-batch by the backend
  overhaul master plan (Phase 2, B1-B7).
- Convert remaining historical references to the retired `tasks.md` workflow
  into `PLANS.md` / ExecPlan language when those files are next touched.
- Shrink `docs/generated/architecture-boundary-baseline.json` steadily rather
  than allowing new frontend/backend drift to accumulate.
- Keep the default observability-enabled dev stack healthy and revisit only if
  maintenance cost outweighs debugging leverage.
- Expand the browser harness only after the three baseline smoke paths stay
  stable in local development.

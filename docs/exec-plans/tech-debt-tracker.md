# Tech Debt Tracker

## Purpose

Keep current, actionable debt separate from dated inventories and delivered work.
Each item below identifies its dependency and next evidence needed.

## Current Debt

- Backend maintainers: investigate external provider HTTP calls held inside
  database transactions and legacy `Model.query` usage. Use the completed
  overhaul journal for entry points; size each change from a fresh census and
  cover transaction/failure behavior before changing it.
- Backend/API owners: verify candidate routes with no known consumer against
  production access evidence before proposing removals. The July inventory's
  count is historical and is not deletion authorization.
- Learning backend: extend deterministic golden fixtures for mid-stream errors
  and resume behavior; choose cases from current `/run` contracts.
- Frontend/product: shared-course editor permission affordances and French
  onboarding copy polish were deferred from the retired home-entry work. First
  confirm current editor behavior and intended scope; no implementation is queued.
- Learning frontend: optional visual page finder with desktop hover previews
  and a cross-device page panel. Before implementation, define thumbnails/typed
  cards, streaming refresh, caching, mobile discovery and rendering-cost limits.
- Growth/Skills: full generation/import attribution beyond the delivered course
  entry events needs its own producer/consumer contract. Cross-repository Skill
  acquisition acceptance remains in the active attribution plan.
- Billing/product: decide preorder-renewal campaign eligibility, price locking,
  stacking and provider behavior. Automatic renewal remains out of scope until
  separately decided; order reuse is owned by the active payment-attempt plan.
- Authentication: broader password IP-policy changes depend on the delivered
  trusted-client-IP boundary and a separately specified policy/test matrix.
- Architecture owners: shrink the committed boundary baseline as individual
  boundary violations are fixed; a fresh scan, not old counts, determines work.

## Completed Debt and Evidence

The July inventory is preserved at `docs/history/backend-inventory-2026-07.md`.
Its 213 direct commits, serializer/pagination/env-read counts and stale endpoint
catalog observations are not current debt. Backend overhaul #2132/#2133 delivered
the refactors and the completed `uow-commit-site-migration.md` eliminated the
remaining outside-DAO commits. The current committed UoW baseline is empty;
`python scripts/check_uow_commit_sites.py` enforces that result.

## External Acceptance

Use the dated [plan review](../history/knowledge-review-2026-09-26.md) for the
complete per-plan disposition and open device, provider, SMTP and deployment
acceptance. Those tasks remain active and are not replaced by this debt list.

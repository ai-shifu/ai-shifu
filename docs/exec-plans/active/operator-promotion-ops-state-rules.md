# ExecPlan: Operator Promotion Ops State Rules

## Purpose / Big Picture

Unify the operator-facing `ops_state` rules used by the promotions and creator
redemption-code pages so filtering, badges, enable/disable guidance, and future
export behavior all read from one consistent source of truth. Today the feature
works, but pieces of the rule set are scattered across backend filter code and
frontend page helpers, which makes drift likely as more states or UI surfaces
arrive.

This plan keeps the scope narrow: align `ops_state` semantics for existing
states such as `expiring_soon` and `used_up`, reuse current APIs where
possible, and avoid mixing in unrelated second-round visual polish or export
features.

## Progress

- [x] 2026-06-18 11:20 CST: Audited current backend `ops_state` rules and
  frontend badge/filter mappings for the operator promotions page. Confirmed
  the current rule set is coupon-only; creator redemption currently reuses the
  backend coupon list helper but does not expose an `ops_state` filter in its
  frontend.
- [x] 2026-06-18 12:05 CST: Chose the first-step ownership model: backend now
  computes coupon `ops_states`, while the frontend consumes that field through
  a shared helper for badges and filter option wiring.
- [x] 2026-06-18 12:20 CST: Implemented the shared `ops_state` path for coupon
  rows and updated focused backend/frontend tests.
- [x] 2026-06-18 12:45 CST: Exposed the same coupon `ops_state` filter contract
  on the creator redemption frontend so both operator surfaces now send the
  same backend filter parameter and consume the same returned badge states.
- [x] 2026-06-18 14:20 CST: Added focused backend/frontend tests for
  `expiring_soon`, `used_up`, empty/default `ops_states`, creator redemption
  `ops_state` request passthrough, and the creator-only status filter option
  guard that removes `ended`.
- [x] 2026-06-18 14:25 CST: Ran narrow validation for promo/admin timezone and
  creator-redemption flows; recorded remaining scope-risk notes around the
  unrelated local-dev config route and dashboard/timezone hardening changes.

## Surprises & Discoveries

- The current `ops_state` feature is narrower than the roadmap wording
  suggests. The backend coupon list helper `_list_promotion_coupons()` accepts
  `ops_state`, but there is no parallel `ops_state` filter for campaign rows,
  and the creator redemption frontend does not expose this filter yet.
- Frontend already duplicates coupon-side `ops_state` semantics in
  `promotionPageShared.tsx` via `isPromotionExpiringSoon()` and
  `isCouponUsedUp()` to render attention badges. That means filtering logic
  and display logic can drift even before any new states are added.
- The current coupon `ops_state` filter applies only two states:
  `expiring_soon` and `used_up`. It is separate from `computed_status`
  (`inactive`, `not_started`, `expired`, `active`).
- Creator redemption table was already reusing the shared coupon badge helper,
  so once backend `ops_states` shipped the remaining gap was only the missing
  frontend filter control and request param wiring.

## Decision Log

- 2026-06-18: Keep backend as the source of truth for accepted coupon
  `ops_state` values. The backend now returns `ops_states` on coupon list/detail
  items, and the frontend uses a shared helper to render badges and shared
  filter options from those returned states instead of recomputing
  `expiring_soon` / `used_up` locally.
- 2026-06-18: Extend the same shared coupon `ops_state` filter options to the
  creator redemption page instead of introducing a second creator-only status
  vocabulary.
- Pending: whether the shared helper should live beside the promotions page
  (`promotionPageShared.tsx`) first, or in a more generic admin operations
  utility module immediately.

## Outcomes & Retrospective

- Coupon `ops_state` ownership is now consistent: backend computes
  `ops_states`, promotions and creator-redemption frontend surfaces both
  consume that field for filtering/badges, and the creator page no longer uses
  the operator-only “ops filter” wording.
- The main remaining risk is PR scope: the branch also carries a local-dev
  `api/config` loopback override and dashboard timezone hardening that are
  useful but not directly part of coupon `ops_state` unification. They should
  either be called out explicitly in the PR description or split if a narrower
  review surface is preferred.

## Context and Orientation

- Backend entry point today:
  - `src/api/flaskr/service/promo/admin.py`
- Frontend entry points today:
  - `src/cook-web/src/app/admin/operations/promotions/page.tsx`
  - `src/cook-web/src/app/admin/operations/promotions/promotionPageShared.tsx`
- Existing tests to extend first:
  - `src/cook-web/src/app/admin/operations/promotions/page.test.tsx`
  - `src/api/tests/service/promo/test_admin_promotions.py`

The current backend already accepts `ops_state` in at least part of the
promotions filter flow, while the frontend owns parts of the label, attention
badge, and interaction logic. That means the first task is not “add a new
feature,” but “map the actual current rule ownership and remove duplicated
interpretations.”

## Plan of Work

1. Audit the current rule set on both backend and frontend.
2. Choose one shared rule ownership model and document it before coding.
3. Implement the shared rule path with the smallest API/UI surface change that
   still removes duplicated logic.
4. Update both filtering and display consumers together.
5. Lock the behavior with focused tests.

## Concrete Steps

1. Inspect `src/api/flaskr/service/promo/admin.py` to list:
   - accepted `ops_state` filter values
   - the actual data predicates behind each value
   - any coupon/activity-specific divergences
2. Inspect `src/cook-web/src/app/admin/operations/promotions/page.tsx` and
   `promotionPageShared.tsx` to list:
   - where status badges are derived
   - where filter options are declared
   - where action gating depends on state-like conditions
3. Record the current matrix in this plan:
   - activity rows vs coupon rows
   - backend filter semantics vs frontend display semantics
4. Decide the ownership model:
   - preferred default: keep backend as the filter source of truth and extract a
     shared frontend helper for label/badge/view logic
   - alternative only if clearly simpler: backend returns richer `ops_state`
     display data directly
5. Implement the shared helper/module and replace ad-hoc page-local branching.
6. Update tests to cover:
   - `expiring_soon`
   - `used_up`
   - empty/default `ops_state`
   - unchanged action availability for enable/disable/edit flows

### Current audit matrix

#### Backend

- Coupon list filter entry point:
  `src/api/flaskr/service/promo/admin.py::_list_promotion_coupons()`
- Accepted `ops_state` values today:
  - `expiring_soon`
    - predicate: `Coupon.end >= now && Coupon.end <= now + 7 days`
  - `used_up`
    - predicate: `Coupon.used_count >= Coupon.total_count`
- No coupon-side backend guard currently excludes inactive / expired rows from
  these predicates; they are combined with whatever other filters the caller
  passed.
- Campaign list currently has no parallel `ops_state` filter implementation.

#### Frontend

- Coupon filter dropdown lives in
  `src/cook-web/src/app/admin/operations/promotions/page.tsx`
  and exposes:
  - `expiring_soon`
  - `used_up`
- Coupon table attention badges live in
  `src/cook-web/src/app/admin/operations/promotions/promotionPageShared.tsx`
  and currently render only when `item.computed_status === 'active'`:
  - `used_up` if `used_count >= total_count`
  - `expiring_soon` if `end_at` is within `PROMOTION_EXPIRING_SOON_DAYS`
- Coupon enable/disable action gating is separate again:
  - `canEnableCouponItem()`
  - `shouldShowCouponStatusToggle()`
- Campaign rows only use `computed_status`; they do not have `ops_state`
  filters or attention badges today.

## Validation and Acceptance

- Promotions and creator redemption code pages show the same meaning for each
  `ops_state` label and filter option.
- Filtering by `ops_state` still returns the same rows as before for existing
  supported states.
- No user-facing strings are hardcoded outside shared i18n JSON.
- Focused tests pass:
  - backend promo tests covering `ops_state` filters
  - frontend promotions page tests covering filter/badge behavior
- `git diff --check` passes.

## Idempotence and Recovery

- The branch can be re-audited safely by rerunning the same backend/frontend
  inspections and comparing the documented matrix against code.
- If the shared helper approach proves too invasive, keep the backend contract
  unchanged and land a narrower extraction inside
  `promotionPageShared.tsx` first.
- If validation shows hidden coupon/activity divergences, stop broad
  generalization and document the divergence explicitly before proceeding.

## Interfaces and Dependencies

- Backend:
  - `src/api/flaskr/service/promo/admin.py`
  - any DTO or serializer files touched by promotions filters/results
- Frontend:
  - `src/cook-web/src/app/admin/operations/promotions/page.tsx`
  - `src/cook-web/src/app/admin/operations/promotions/promotionPageShared.tsx`
  - related admin UI filter/badge helpers if extraction becomes necessary
- Validation dependencies:
  - `src/api/tests/service/promo/test_admin_promotions.py`
  - `src/cook-web/src/app/admin/operations/promotions/page.test.tsx`

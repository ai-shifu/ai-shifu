# Admin Time Display

## Background

The admin/operator surfaces currently render backend datetimes through three
different patterns:

- raw backend strings such as `YYYY-MM-DD HH:mm:ss`
- operator-user-specific UTC formatter logic in Cook Web
- billing/dashboard-specific timezone-aware formatting flows

This causes inconsistent display formats, missing browser-timezone rendering on
several pages, and fragile frontend behavior when backend responses omit an
offset.

## Goal

- Unify admin/operator time display to `YYYY-MM-DD HH:mm:ss`
- Render admin/operator datetimes in the browser timezone on the frontend
- Standardize operator/admin API datetime payloads on timezone-qualified ISO
  strings, preferably UTC `...Z`
- Stop directly rendering raw backend naive datetime strings in admin pages

## Scope

### Frontend

- Extract a shared admin datetime helper for admin/operator pages
- Migrate these pages to the shared helper:
  - operator course list
  - operator course detail
  - operator course users
  - operator follow-up list/detail
  - operator orders list/detail
  - legacy admin order list/detail where applicable

### Backend

- Update operator/admin serializers that still emit naive
  `YYYY-MM-DD HH:mm:ss` values:
  - `flaskr/service/shifu/admin.py`
  - `flaskr/service/order/admin.py`
- Keep existing dashboard/billing timezone query semantics intact for now

## Non-Goals

- No full billing/dashboard formatting refactor in this change
- No learner-side datetime formatting changes
- No schema or database timezone migration

## Contract

### Backend response contract

- Admin/operator datetime fields should return timezone-qualified ISO strings
- Prefer UTC serialization with trailing `Z`
- Frontend should treat offsetless legacy datetime strings as invalid for the
  migrated admin/operator pages

### Frontend display contract

- Admin/operator pages format valid ISO datetimes into
  `YYYY-MM-DD HH:mm:ss`
- Display uses browser timezone from `getBrowserTimeZone()`
- Invalid or empty values render as empty/placeholder labels

### Current exceptions: wall-clock metadata fields

- Some admin/operator metadata fields still come from backend payloads as
  wall-clock values without timezone semantics.
- Until those fields are migrated to timezone-qualified ISO strings, the
  frontend should preserve the returned wall-clock time with the naive
  formatter helpers instead of applying browser-timezone conversion.
- No known wall-clock exceptions remain in the migrated operations users,
  orders, or course surfaces listed below.

The following operator fields have been migrated to the UTC ISO payload contract
and must use browser-timezone rendering with `formatAdminUtcDateTime` or its
operator alias `formatOperatorUtcDateTime`:

- course metadata `basic_info.created_at` / `basic_info.updated_at`
- course list metadata `created_at` / `updated_at`
- course users `last_learning_at` / `last_login_at` / `joined_at`
- course credit usage `created_at`
- course credit usage detail `created_at`
- course follow-up `created_at` / `latest_follow_up_at`
- course follow-up detail `basic_info.created_at` / timeline `created_at`
- course ratings `rated_at` / `latest_rated_at`
- chapter metadata `updated_at`
- user record `created_at` / `updated_at`
- user activity `last_login_at` / `last_learning_at`
- user credits expiry `credits_expire_at`
- user credit ledger `created_at` / `expires_at` / `consumable_from`
- user credit usage detail `created_at`
- learn order metadata `created_at`
- credit order metadata `created_at` / `paid_at` / `failed_at` / `refunded_at`
- order detail metadata `created_at` / `updated_at`
- legacy admin order metadata `created_at`
- legacy redemption-code metadata `created_at` / `updated_at`
- legacy redemption-code time ranges `start_at` / `end_at`
- legacy redemption-code usage timestamps `used_at` / `updated_at`
- promotion coupon/campaign metadata `created_at` / `updated_at`
- promotion coupon/campaign time ranges `start_at` / `end_at`
- promotion coupon/campaign record timestamps `applied_at` / `used_at`
- referral campaign metadata `created_at` / `updated_at`
- referral campaign time ranges `starts_at` / `ends_at`
- referral relation and reward timestamps `bound_at` / `effective_at` / `expires_at`
- credit notification records `created_at` / `updated_at` / `requested_at` / `attempted_at` / `sent_at`
- credit notification template sync `last_synced_at`
- billing subscription period timestamps `current_period_start_at` / `current_period_end_at` / `grace_period_end_at`
- billing renewal event timestamps `scheduled_at` / `processed_at`
- billing order metadata `created_at` / `paid_at` / `failed_at` / `refunded_at`
- billing entitlement time ranges `effective_from` / `effective_to`
- billing domain verification timestamp `last_verified_at`
- billing report windows `window_started_at` / `window_ended_at`

Other event timestamps that are already backed by correct timezone-qualified
payloads should continue to use the browser-timezone rendering flow.

## Implementation Plan

1. Add a shared admin datetime helper in Cook Web and move the current
   operator-user formatter logic into it.
2. Repoint operator/admin pages to the shared helper.
3. Update backend operator/admin serializers to emit UTC ISO strings instead of
   naive formatted text.
4. Update frontend/backend tests to use timezone-qualified datetime fixtures.
5. Verify the main affected pages and targeted tests.

## Risks

- Existing tests may rely on raw `YYYY-MM-DD HH:mm:ss` fixtures and will need
  coordinated updates.
- Some pages may still depend on backend-provided display strings; those should
  be left unchanged in this pass unless they are part of the migrated
  operator/admin flow.

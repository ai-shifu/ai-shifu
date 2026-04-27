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

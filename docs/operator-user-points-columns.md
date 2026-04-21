# Operator User Points

## Context

The operator user management page now needs a clearer credits view instead of
three provisional billing columns.

The underlying source is still the creator billing wallet under `billing`,
keyed by `creator_bid`, so this work stays read-only and reuses the current
wallet bucket / ledger model.

## Confirmed Product Scope

This branch now covers the following operator-facing flow:

- user list keeps only two credits columns:
  - `available_credits`
  - `credits_expire_at`
- clicking `available_credits` jumps to the credits section on the user detail
  page
- user detail adds:
  - credits overview cards
  - credits detail list
  - tabs to keep the page length manageable

This branch still does **not** cover:

- manual credit issuance UI
- new write-side billing APIs
- editing expiry during manual adjustments
- a standalone credits page outside the user detail route

## Ledger Detail Interpretation

The original ledger payload exposed low-level billing fields directly:

- `entry_type`
- `source_type`
- `source_bid`
- optional raw `note`

That shape is still useful for the billing domain itself, but `source_bid` is
not operator-friendly and the raw enum pair is not expressive enough for
operations users to quickly understand what happened.

The operator detail page therefore now follows this display rule:

- remove the `source_bid` column from the operator credits table
- keep raw `entry_type` and `source_type` in the API for compatibility
- add operator-facing display codes on the backend:
  - `display_entry_type`
  - `display_source_type`
  - `note_code`
- translate those codes in Cook Web through shared i18n files

This keeps the billing model unchanged while letting the operator page show
business-readable rows such as:

- subscription grant
- top-up grant
- trial subscription grant
- learning consume
- preview consume
- manual credit / manual debit
- subscription expiry

When a row already carries a free-text `note`, the operator page shows that
text directly. When no explicit note exists, the current operator detail page
renders `--` and keeps `note_code` as backend-only display metadata for future
expansion.

## Product Interpretation

### User List

- `available_credits` means the current active creator credits total
- `credits_expire_at` means the earliest `effective_to` among current active
  credit buckets with remaining balance
- if the user has active credits and none of those buckets has an expiry, the
  frontend should show a long-term-valid label
- if the user is not a creator and has no billing credits, the list should show
  an empty state instead of a misleading zero

### User Detail

- keep the existing basic information and overview sections
- add a dedicated credits overview:
  - available credits
  - subscription credits
  - top-up credits
  - credits expiry
- add a credits detail tab on the same page
- learning courses and created courses move under tabs so the page does not
  become too long

## Backend Plan

- extend `AdminOperationUserSummaryDTO` with `credits_expire_at`
- extend the existing credit summary aggregation helper so it also tracks the
  earliest active bucket expiry
- keep the existing operator list and detail APIs, only extending the payload
- add a new API:
  - `GET /shifu/admin/operations/users/{user_bid}/credits`
- return summary + paginated ledger items for the detail page

## Data Rules

An active bucket counts toward summary and expiry aggregation only when all of
the following are true:

- `deleted = 0`
- `status = active`
- `available_credits > 0`
- `effective_from <= now` when present
- `effective_to > now` or `effective_to is null`

Expiry aggregation rule:

- choose the earliest non-null `effective_to` among counted buckets
- if no counted bucket has `effective_to`, treat the current credits as
  long-term valid on the frontend

This keeps the display accurate even if future manual adjustments introduce
credits without a unified expiry.

## Frontend Plan

- list page:
  - replace the three provisional credit columns with:
    - available credits
    - credits expire at
  - make available credits clickable to
    `/admin/operations/users/{user_bid}#credits`
- detail page:
  - add a credits section with overview cards
  - add tabs:
    - credits detail
    - learning courses
    - created courses
  - when the route contains `#credits`, switch to the credits tab and scroll to
    the credits section after data is ready

## Verification Plan

- backend:
  - cover creator summary, non-creator empty state, earliest expiry, and
    credits detail API payloads
- frontend:
  - update the list test for the two-column credits layout
  - add detail-page coverage for the credits overview, credits tab, and hash
    jump behavior
- focused commands:
  - `cd src/api && pytest tests/service/shifu/test_admin_users.py -q`
  - `cd src/cook-web && npm run test -- src/app/admin/operations/users/page.test.tsx 'src/app/admin/operations/users/[user_bid]/page.test.tsx'`
  - `cd src/cook-web && npm run lint`
- expected existing limitation:
  - `cd src/cook-web && npm run type-check` may still be blocked by the known
    legacy `markdown-flow-ui/slide` type errors under `src/app/c/[[...id]]/`

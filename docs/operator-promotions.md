# Operator Promotions

## Goal

Add a new operator-level `Promotions` area under operations for managing coupon batches and course discount campaigns with a UI consistent with the existing operations console.

## Scope

- Add a new operator menu item and page route at `/admin/operations/promotions`
- Build two tabs on the page:
  - Coupon Codes
  - Campaigns
- Reuse the existing promo, coupon, coupon usage, and promo redemption domain models where possible
- Add operator-facing backend list/detail/create/status APIs
- Add focused backend and frontend tests for the new flows

## Product Decisions

### Naming

- Menu label: `优惠活动`
- Route path: `/admin/operations/promotions`
- Tabs:
  - `兑换码`
  - `活动`

### Coupon Codes

- Main list is batch-based and backed by `promo_coupons`
- Support two usage types:
  - generic code
  - one-code-per-order
- Support two discount types:
  - fixed amount
  - percentage
- Support active time window and scope:
  - all courses
  - single course
- One-code-per-order batches can be created and toggled, but not edited afterward
- Coupon and campaign discounts may stack

### Campaigns

- V1 supports only course-level automatic campaigns
- Same course cannot have overlapping enabled campaign windows
- Campaigns can be created and toggled, but not edited afterward

## Backend Design

### Data Model

- Extend `promo_coupons` with:
  - `name`
  - `updated_user_bid`
- Keep campaign schema unchanged for V1
- Continue storing course scope in the JSON `filter`

### Services

Add operator admin helpers under `src/api/flaskr/service/promo/` for:

- coupon list/detail/create/status update
- coupon usage list
- coupon code pool list
- campaign list/detail/create/status update
- campaign redemption list
- shared computed status helpers
- campaign overlap validation

### Routes

Add operator routes under `/shifu/admin/operations/promotions/...`.

## Frontend Design

- Add `Promotions` to the operator menu
- Build a new page that reuses the existing operations layout style:
  - summary cards
  - filters
  - table shell
  - right-side detail sheets
  - create dialogs
- Keep UI strings in `src/i18n`

## Verification

- Backend pytest for coupon and campaign operator APIs and validations
- Frontend page tests for tabs, rendering, and form validation
- Broader type-check/lint before handoff

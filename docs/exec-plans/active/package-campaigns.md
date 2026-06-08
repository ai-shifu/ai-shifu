# ExecPlan: Package Campaigns

## Purpose / Big Picture

Add an operator-facing `套餐活动` tab under the existing `优惠活动` page so
operators can manage billing product campaigns without introducing a new menu
layer. V1 supports one benefit type per campaign (`discount` or `bonus`),
uses modal dialogs instead of drawers, supports enable/disable, applies to
creator checkout for subscription start / upgrade / topup, keeps automatic
renewal executor orders outside campaigns, and records campaign bonus credits
separately for later reconciliation. User-initiated preorder renewal campaign
eligibility is captured as a follow-up business-rule iteration.

## Progress

- [x] 2026-05-17 12:55 CST: Confirmed product direction with the user, including placement under `优惠活动`, modal-based create/edit, status toggles, and V1 single-benefit campaigns.
- [x] 2026-05-17 14:10 CST: Added billing campaign persistence models, migration, admin API route skeletons, creator catalog campaign projections, and bonus-grant scaffolding.
- [x] 2026-05-18 11:10 CST: Refined the package campaign modal for per-product activity rules, hid the trial plan option, and constrained the dialog plus product area with internal scrolling and icon-based collapse.
- [x] 2026-06-08 13:35 CST: Captured the follow-up order-timeout requirement separately from package campaign launch so future work can decide whether pending orders lock price or reprice.
- [x] 2026-06-08 15:05 CST: Captured the desired follow-up rule that user-initiated preorder renewal should be able to enjoy active package campaign pricing, while automatic renewal executor orders remain out of scope until separately decided.
- [ ] 2026-05-17 13:10 CST: Add the `套餐活动` admin tab, modal forms, and status actions.
- [ ] 2026-05-17 13:10 CST: Apply campaign pricing / bonus logic in checkout and paid-order grant side effects.
- [ ] 2026-05-17 13:10 CST: Add focused tests and run the smallest relevant verification commands.

## Surprises & Discoveries

- The existing `优惠活动` page already provides the preferred UX primitives:
  tabs, modal dialogs, status confirmation, table shell, and tests in one
  place, so package campaigns can slot into that page without introducing new
  route structure.
- The billing catalog already returns stable creator-facing DTOs from
  `read_models.py`, which makes it feasible to attach campaign projections at
  serialization time without changing checkout request shapes.
- Once per-product configuration is shown inline, the modal needs both an
  overall height cap and a dedicated scroll container on the product section
  to avoid pushing the footer off smaller laptop screens.
- Stripe subscription checkout uses recurring line-item pricing. Campaign
  discounts must not lower the recurring line item itself; the safer V1 shape is
  original recurring price plus a one-time first-invoice discount so later
  renewals return to the regular product price.
- Paid-order side effects already centralize credit granting in
  `paid_side_effects.py` and `subscriptions.py`, which is the safest place to
  append campaign bonus grants with idempotency.
- Current billing checkout creates a new order on each fresh subscription or
  topup checkout. Only the in-dialog QR channel switch refreshes an existing
  pending order. Therefore package campaigns can launch before order-timeout
  reuse without introducing stale-price reuse in the initial rollout.

## Decision Log

- Keep package campaigns inside the existing `优惠活动` page as a third tab;
  do not add a third-level navigation menu.
- Use billing-owned tables and APIs; do not reuse the legacy `promo` course
  campaign tables.
- Use modal dialogs for create/edit, matching the existing coupon / campaign
  UX, and keep enable/disable behind the shared confirmation dialog.
- Activity products stay inside the create/edit modal and use an icon toggle
  plus bounded inner scrolling instead of expanding the full dialog height.
- V1 allows exactly one benefit per campaign: a price discount or a bonus
  credit grant, not both at the same time.
- V1 launch keeps automatic renewal executor orders out of campaigns.
  `subscription_start`, `subscription_upgrade`, and `topup` participate.
  User-initiated preorder renewal should be discussed as a follow-up iteration:
  product intent is to let creators prepay the next cycle at the currently
  active campaign price, but the locking, stacking, and provider-specific
  renewal behavior must be designed before implementation.
- Creator-facing activity messaging is derived from structured campaign data
  and shared i18n templates; operator-facing campaign names remain internal
  admin text in this iteration.
- Do not block the package campaign release on billing order timeout / reuse.
  The current checkout path recalculates campaign pricing on each new order,
  which is safer for the campaign launch. Order timeout is tracked as a
  follow-up optimization with an explicit price-snapshot decision.

## Outcomes & Retrospective

- Pending.

## Context and Orientation

- Frontend operator promotions surface:
  - `src/cook-web/src/app/admin/operations/promotions/page.tsx`
  - `src/cook-web/src/app/admin/operations/promotions/page.test.tsx`
  - `src/cook-web/src/app/admin/operations/operation-promotion-types.ts`
- Frontend billing creator surfaces:
  - `src/cook-web/src/components/billing/BillingOverviewShowcase.tsx`
  - `src/cook-web/src/components/billing/BillingPlanComparisonTable.tsx`
  - `src/cook-web/src/components/billing/BillingOverviewCards.tsx`
  - `src/cook-web/src/types/billing.ts`
  - `src/cook-web/src/lib/billing.ts`
- Backend billing routes and read models:
  - `src/api/flaskr/service/billing/routes.py`
  - `src/api/flaskr/service/billing/read_models.py`
  - `src/api/flaskr/service/billing/serializers.py`
  - `src/api/flaskr/service/billing/dtos.py`
- Backend billing write path:
  - `src/api/flaskr/service/billing/checkout.py`
  - `src/api/flaskr/service/billing/subscriptions.py`
  - `src/api/flaskr/service/billing/paid_side_effects.py`
- Billing schema / fixtures:
  - `src/api/flaskr/service/billing/models.py`
  - `src/api/migrations/versions/`
  - `src/api/tests/common/fixtures/billing_products.py`

## Plan of Work

1. Add billing campaign persistence models and migration plus focused admin
   DTOs, serializers, query helpers, and mutation helpers.
2. Register admin billing routes for package campaign list/detail/create/update/
   status and product option bootstrap.
3. Extend the operator promotions page with a `套餐活动` tab, filters, table,
   modal create/edit form, and status actions.
4. Extend billing catalog serialization and checkout / paid-order grant logic
   so matching campaigns affect creator-facing pricing and bonus credits.
5. Add focused backend and frontend tests, then run the narrowest relevant
   verification commands.

## Concrete Steps

1. Create a billing campaign module that can:
   - validate campaign payloads
   - ensure only one active overlapping campaign per product
   - return product options for plans and topups
   - resolve the active campaign for one product and order context
2. Add `BillingCampaign*` SQLAlchemy models and an Alembic migration for:
   - `bill_campaigns`
   - `bill_campaign_products`
3. Extend billing DTO / serializer surfaces for:
   - admin campaign list/detail/options
   - creator catalog campaign summaries
4. Update `checkout.py` to compute campaign snapshots on order creation and to
   lock payable amounts on the order metadata.
5. Update paid-order credit grant logic to create an idempotent bonus credit
   grant when a paid order carries a campaign bonus snapshot.
6. Update the promotions page, API contract, i18n files, and tests for the new
   operator tab.

## Follow-up Requirement: Billing Order Timeout and Reuse

This follow-up is intentionally outside the package campaign V1 release. It
should be planned as an independent PR after campaign pricing is verified in
production.

Desired behavior:

- A creator checkout order has a 30-minute validity window.
- If a creator closes the checkout dialog and starts the same checkout again
  within 30 minutes, the system may reuse the existing pending order and
  refresh the provider payment credential.
- If the pending order is older than 30 minutes, the system marks it
  `timeout` and creates a new order.
- Timeout should apply to billing subscription start / upgrade / preorder
  renewal and topup orders, not to paid renewal executor orders unless that
  flow is explicitly scoped.

Price and campaign policy decision:

- The safer product behavior is "reuse only when the current product price and
  campaign snapshot still match the pending order".
- If a campaign starts, ends, or changes after the pending order was created,
  the old pending order should be marked `timeout` or `canceled`, and a fresh
  order should be created with the current catalog price and campaign snapshot.
- This avoids a mismatch where the page shows a current activity price but the
  payment dialog reuses an older non-campaign order, or where an expired
  activity remains payable during the 30-minute window.
- If product later wants strict order lock pricing, document that 30-minute
  window as a user-facing "price locked until" rule before implementation.

Implementation notes:

- Prefer a billing-specific config such as `BILLING_ORDER_EXPIRE_TIME=1800`
  rather than changing `PAY_ORDER_EXPIRE_TIME`, which also affects legacy
  course-order timeout behavior.
- Add a checkout helper that finds a reusable pending order by creator,
  product, order type, provider/channel context, action metadata, payable
  amount, and campaign snapshot.
- Expire stale pending orders during checkout and sync paths; if a first-time
  subscription start order times out, also clean up or neutralize its draft
  subscription. Upgrade / preorder flows must not mutate the current active
  subscription when expiring a pending order.
- Keep timeout terminal in the billing state machine so late webhook or sync
  events cannot turn an expired order into paid; define the operational
  handling for provider-side late payment before enabling this broadly.
- Frontend can continue calling the subscription/topup checkout APIs. It only
  needs extra UI if the product wants to display a 30-minute countdown or
  "order valid until" copy.

Acceptance tests for the follow-up:

- First checkout creates a pending order.
- Repeating the same checkout inside 30 minutes returns the same
  `bill_order_bid` when price and campaign snapshot are unchanged.
- Repeating after 30 minutes marks the old order `timeout` and returns a new
  `bill_order_bid`.
- Starting, ending, or changing a package campaign inside the 30-minute window
  forces a new order instead of reusing the older snapshot.
- A timed-out order cannot be paid by a later webhook / sync transition.
- Pingxx / native QR channel refresh reuses only valid pending orders and
  creates a new provider credential.

## Follow-up Requirement: Preorder Renewal Campaign Eligibility

This follow-up records the desired business-rule change for later discussion.
It is not required for the initial package campaign PR unless product explicitly
pulls it into scope.

Desired behavior:

- A creator with an active subscription can user-initiate a preorder renewal
  for the next cycle and enjoy the currently active package campaign price for
  that target plan.
- The preorder renewal order locks the campaign snapshot at order creation.
  If the activity ends before the next cycle starts, the paid preorder still
  keeps the campaign price because the creator already prepaid.
- Automatic renewal executor orders remain excluded from campaigns unless a
  separate product decision says otherwise.
- Creator-facing UI should clearly distinguish "prepay next cycle with current
  activity price" from ordinary automatic renewal, so users understand the
  discounted amount is tied to the prepaid order.

Policy decisions to resolve before implementation:

- Whether creators may stack multiple future-cycle preorder renewals during
  one campaign, or only keep one pending/paid preorder renewal at a time.
- Whether same-plan preorder renewal and downgrade preorder share the same
  campaign eligibility rules.
- How to handle campaign bonus credits for preorder renewal: grant immediately
  as reserved credits for the next cycle, or grant only when the preorder
  becomes effective.
- Stripe subscription checkout cannot simply create a recurring discounted
  line item if renewals after the prepaid cycle should return to full price;
  it needs provider-specific first-cycle discount handling or a self-managed
  preorder payment path.
- If billing order timeout/reuse is introduced first, preorder renewal reuse
  must compare product price, order type, checkout action, effective mode, and
  campaign snapshot before reusing a pending order.

Acceptance tests for the follow-up:

- User-initiated preorder renewal created during an active campaign stores the
  campaign snapshot and discounted payable amount.
- User-initiated preorder renewal created outside an active campaign uses the
  regular product price and no campaign snapshot.
- Automatic renewal executor orders continue to create renewal orders without
  campaign snapshots.
- A paid preorder renewal keeps its locked campaign price when the campaign
  later expires or is disabled.
- Campaign bonus preorder behavior is idempotent and follows the chosen
  immediate-vs-effective grant policy.

## Validation and Acceptance

- Operators can open `优惠活动` and switch to a `套餐活动` tab without leaving the
  current page or using a new menu layer.
- Operators can create, edit, enable, and disable a package campaign from a
  modal dialog.
- Campaign list rows show status, product scope, benefit type, rule summary,
  time range, and hit count.
- Creator billing catalog surfaces show campaign-enhanced pricing / bonus
  messaging for matching plans and topups.
- Subscription start / upgrade / topup orders lock campaign snapshots at order
  creation time. Automatic renewal executor orders do not apply campaigns in
  V1; user-initiated preorder renewal campaign eligibility is tracked as a
  follow-up iteration.
- Paid campaign bonus grants create separate, idempotent ledger entries with
  distinct metadata for later reconciliation.

## Idempotence and Recovery

- Campaign status changes and edits only affect future matching orders; already
  created pending orders keep their stored campaign snapshot.
- Bonus grants use a dedicated idempotency key per order so repeated webhook /
  sync processing does not duplicate credits.
- If a campaign is disabled or expires, creators must place a new order to get
  refreshed pricing; old pending orders do not reprice in place.

## Interfaces and Dependencies

- New admin billing routes under `/api/admin/billing/campaigns` and
  `/api/admin/billing/products/options`.
- Creator catalog DTOs extend existing `BillingPlanDTO` / `BillingTopupProductDTO`
  with optional campaign payloads.
- Checkout reuses existing billing order creation and paid-order side effects;
  no new provider integration or webhook endpoint is introduced.

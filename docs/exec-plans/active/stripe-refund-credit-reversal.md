# Stripe Refund Credit Reversal

## Purpose / Big Picture

Correct creator-billing Stripe refunds so a monetary refund reverses the
credits issued by the refunded billing order instead of granting the same
product credits again. The completed behavior must keep the provider refund,
billing order, subscription state, wallet buckets, immutable ledger, and
Stripe webhook retries consistent and idempotent.

The teacher-facing refund route is already disabled. This plan covers the
internal refund orchestration and provider webhook paths before any refund
surface can safely be exposed again.

## Progress

- [x] 2026-09-30 10:30 CST: Created
  `fix/reverse-credits-on-stripe-refund` from the latest `origin/main`.
- [x] 2026-09-30 10:45 CST: Traced paid-order credit grants, direct Stripe
  refunds, Stripe refund webhooks, wallet bucket mutation, ledger writes, and
  existing regression coverage.
- [x] 2026-09-30 10:50 CST: Confirmed the current direct refund path grants a
  second positive credit amount and the webhook path performs no credit
  reversal.
- [ ] Define the product policy for partial refunds and orders whose issued
  credits have already been partly or fully consumed.
- [ ] Implement one idempotent order-credit reversal operation shared by the
  direct refund and webhook reconciliation paths.
- [ ] Align the billing design contract and replace tests that currently
  require the incorrect positive refund grant.
- [ ] Run focused billing refund and wallet tests, then the complete billing
  suite and repository gates.

## Surprises & Discoveries

- `refund_billing_order()` in
  `src/api/flaskr/service/billing/checkout.py` calls
  `grant_refund_return_credits()` after the Stripe provider accepts a refund.
  That helper is a positive grant: it creates or increases a bucket, writes a
  positive `refund` ledger entry, and increases the wallet snapshot.
- A paid order originally writes `grant:{bill_order_bid}` with a positive
  amount and links its ledger and bucket to `bill_order_bid`. The refund path
  does not inspect or reverse that grant. It instead writes a separate
  `refund_return:{refund_id}` operation.
- Existing top-up coverage explicitly codifies the defect: a 20-credit paid
  order is expected to leave the wallet at 40 credits after refund.
- Subscription refund coverage can hide the extra grant because canceling the
  subscription makes subscription-category buckets ineligible in the wallet
  snapshot. The newly granted positive bucket and ledger still exist.
- Stripe webhook events (`charge.refunded` and `refund.created`) can move a
  billing order to `refunded`, but `webhooks.py` does not mutate credits or
  cancel the linked subscription through the same direct-refund orchestration.
  A refund initiated outside this application therefore has a different local
  result from `refund_billing_order()`.
- The direct function accepts a partial monetary `amount`, but always grants
  the product's full credit amount. There is no defined proportional credit
  rule.
- Campaign bonus credits are granted with a second order-linked ledger entry,
  but the current refund logic neither identifies nor reverses that bonus.
- PR #2842 intentionally removed the teacher-facing refund route because
  credit reversal was unsafe. PR #2888 fixed metadata serialization and DB
  atomicity but preserved and strengthened tests around the positive grant; it
  did not implement reversal.

## Decision Log

- Decision: Treat monetary payment refund and credit-consumption refund as
  separate concepts. `grant_refund_return_credits()` may remain valid for
  returning credits after a reversed usage charge, but it must not be called
  by payment refund orchestration.
  Rationale: A payment refund reverses purchased value; a usage refund restores
  consumed value. They have opposite wallet effects despite sharing the word
  "refund".
- Decision: Derive reversal evidence from immutable order-linked grant ledger
  entries, not the current product configuration.
  Rationale: Product credit amounts and campaign bonuses can change after the
  purchase, while `grant:{bill_order_bid}` and
  `grant:campaign_bonus:{bill_order_bid}` record what was actually issued.
- Decision: Use one stable order-level reversal identity and make replay a
  no-op.
  Rationale: provider retries and duplicate/out-of-order webhooks are normal.
- Open decision: For partial monetary refunds, choose between proportional
  reversal, full reversal only, or rejecting partial refunds in this flow.
- Open decision: If credits from the order have already been consumed, choose
  whether to consume other eligible credits, allow debt, reject automated
  refund before the provider call, or complete the refund and create an
  operator-visible recovery item.
- Open decision: Decide which Stripe refund state is authoritative. A created
  or pending refund must not be treated as final if Stripe can later fail it.

## Outcomes & Retrospective

Investigation is complete. No runtime behavior has been changed yet. The
current implementation remains unsafe for automated billing refunds, matching
the existing design note that keeps the public refund route disabled.

## Context and Orientation

Creator billing is isolated under `src/api/flaskr/service/billing/`. A paid
order is represented by `BillingOrder`; purchased credits are materialized in
`CreditWalletBucket` and recorded immutably in `CreditLedgerEntry`.

`subscriptions.grant_paid_order_credits()` writes the base grant with
`idempotency_key=grant:{bill_order_bid}` and may write a campaign bonus with
`idempotency_key=grant:campaign_bonus:{bill_order_bid}`. Both entries point to
their affected buckets.

`checkout.refund_billing_order()` invokes Stripe, marks the billing order
refunded, cancels a linked subscription, and currently calls
`wallets.grant_refund_return_credits()`. That helper is designed to add credits
and uses `idempotency_key=refund_return:{refund_id}`.

`webhooks.handle_billing_stripe_webhook()` and
`provider_state._apply_billing_order_provider_update()` can independently mark
orders refunded. They currently have no shared order-credit reversal step.

The stable contract is documented in
`docs/design-docs/billing-subscription-design.md`, but its current
`refund return` wording conflates payment refunds with restoring consumed
credits and must be corrected with the implementation.

## Plan of Work

First settle the two product-policy decisions: partial refunds and insufficient
unconsumed order credits. Document those choices in the billing design.

Add a wallet-domain operation that loads all positive grant entries belonging
to a billing order, including campaign bonuses, and writes traceable negative
reversal entries against the affected buckets according to the chosen policy.
It must update bucket lifecycle fields and the wallet snapshot in the same unit
of work and return an explicit already-reversed result on replay.

Change direct Stripe refund orchestration to use the reversal operation and
remove its call to `grant_refund_return_credits()`. Make refund completion
recoverable across the external provider call and the local transaction rather
than depending on one in-process attempt.

Route Stripe refund webhook reconciliation through the same finalization
operation so application-initiated and provider-initiated refunds converge on
the same order, subscription, bucket, and ledger state.

Replace the positive-grant refund assertions with observable reversal
coverage. Preserve independent tests for `grant_refund_return_credits()` only
for the distinct usage-credit-return use case.

## Concrete Steps

1. Record the approved full/partial/consumed-credit policy in this Decision
   Log and `docs/design-docs/billing-subscription-design.md`.
2. Add focused failing tests in
   `src/api/tests/service/billing/test_checkout_state_transition_contracts.py`
   and `test_billing_write_routes_refund_auth.py` for top-up, subscription,
   campaign bonus, replay, rollback, and webhook convergence.
3. Implement the order-linked reversal in
   `src/api/flaskr/service/billing/wallets.py` using the original grant ledger
   entries as evidence.
4. Wire it into `checkout.py` and `webhooks.py` through one refund-finalization
   boundary.
5. Update the billing design and any affected admin/read-model labels if a new
   ledger entry/source interpretation is required.
6. Run the focused and broad validation commands below.

## Validation and Acceptance

Acceptance requires all of the following observable behavior:

- A fully refunded top-up no longer leaves the purchased credits available and
  never increases the wallet balance.
- A refunded subscription cancels future service and reverses the credits
  issued by the refunded order according to the approved consumed-credit
  policy.
- Base and campaign bonus grants from the order are both handled.
- Repeating the direct refund or receiving duplicate/reflected webhook events
  creates no additional wallet mutation or provider refund.
- A refund initiated at Stripe converges to the same local state as one
  initiated by the application.
- Provider failure leaves order, subscription, wallet, buckets, and ledger
  unchanged.
- A local failure after provider acceptance is recoverable without issuing a
  second Stripe refund.
- Partial refunds follow the documented rule and have explicit tests.

Validation commands:

    cd src/api
    pytest tests/service/billing/test_checkout_state_transition_contracts.py -q
    pytest tests/service/billing/test_billing_write_routes_refund_auth.py -q
    pytest tests/service/billing/test_billing_wallet_lifecycle_grants.py -q
    pytest tests/service/billing/ -q

Then run from the repository root:

    python scripts/check_uow_commit_sites.py
    python scripts/check_architecture_boundaries.py
    python scripts/check_dev_tools.py
    lefthook run pre-commit --all-files

## Idempotence and Recovery

The reversal must use a stable identity derived from the billing order, not a
random ledger identifier or only the Stripe refund object. Reprocessing the
same order/refund combination must return existing evidence without changing
balances.

The provider HTTP call cannot be rolled back with the database transaction.
Persist enough stable refund-operation evidence before or around that call to
reconcile an accepted Stripe refund after a process or database failure. Never
issue a new provider refund merely because local finalization failed.

Migration and repair work for already affected production refunds is a
separate, evidence-driven step. It must identify the original order grants,
positive refund-return entries, later consumption, and current wallet state
before applying any compensating ledger entries.

## Interfaces and Dependencies

- Stripe integration remains behind
  `src/api/flaskr/service/order/payment_providers/stripe.py` and the shared
  `PaymentRefundRequest` / `PaymentRefundResult` contracts.
- Billing transaction ownership remains with `unit_of_work()` and
  `app_context_scope()`; wallet helpers add and flush but do not commit.
- `BillingOrder`, `BillingSubscription`, `CreditWallet`,
  `CreditWalletBucket`, and `CreditLedgerEntry` are the affected persistence
  surfaces.
- Existing unique ledger identity is `creator_bid + idempotency_key`; the new
  reversal operation must fit that contract or introduce an explicitly
  reviewed schema change.
- No teacher-facing refund route should be re-enabled as part of this repair
  unless the product explicitly expands scope after all acceptance criteria
  pass.

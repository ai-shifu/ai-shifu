# Stop Stripe Refund Credit Regrant

## Purpose / Big Picture

Fix the immediate Stripe refund defect without introducing credit reversal.
A successful payment refund must no longer grant the product's credits a
second time. Existing refund behavior remains otherwise unchanged: a refunded
subscription is canceled and its subscription credits become unusable, while
a refunded top-up keeps its original credits for now.

Proportional refunds, order-level bucket reversal, and recovery of already
affected accounts are explicitly separate follow-up work.

## Progress

- [x] 2026-09-30 10:30 CST: Created the investigation branch from the latest
  `origin/main` and traced direct refund, webhook, bucket, and ledger paths.
- [x] 2026-09-30 10:50 CST: Confirmed `refund_billing_order()` incorrectly
  calls the positive `grant_refund_return_credits()` helper after Stripe accepts
  a refund.
- [x] 2026-09-30 11:20 CST: Product scope narrowed to stopping the duplicate
  grant while preserving the existing cancellation and no-reversal behavior.
- [x] 2026-09-30 12:00 CST: Removed the positive grant from payment refund orchestration and updated
  focused regression coverage.
- [x] 2026-09-30 12:10 CST: Aligned the billing design contract and ran the billing and repository
  verification gates.

## Surprises & Discoveries

- A 20-credit top-up currently becomes 40 credits after refund because the
  refund path creates a second positive bucket/ledger mutation.
- Subscription cancellation can hide the duplicate grant in the wallet total,
  because subscription buckets become ineligible, but the incorrect positive
  refund bucket and ledger entry are still created.
- `grant_refund_return_credits()` remains valid for returning credits consumed
  by a usage charge. Monetary payment refund and usage-credit return are
  distinct operations and must not share this call site.
- Stripe refund webhooks do not call this helper, so the immediate defect is in
  the direct `refund_billing_order()` path.

## Decision Log

- Decision: Remove only the positive credit grant performed after a successful
  payment refund.
  Rationale: This fixes the demonstrated doubling defect with the smallest
  safe behavior change.
- Decision: Preserve immediate cancellation of a linked subscription.
  Rationale: Product confirmed that canceled-package credits becoming unusable
  is expected.
- Decision: Do not deduct top-up credits in this change.
  Rationale: Correct deduction requires an order-aware bucket and consumed
  credit policy; that is a larger follow-up.
- Decision: Keep `grant_refund_return_credits()` for usage-credit restoration,
  but document that payment refunds must not invoke it.

## Context and Orientation

`src/api/flaskr/service/billing/checkout.py` owns the direct Stripe refund.
It updates the billing order, cancels a linked subscription, and currently
calls `wallets.grant_refund_return_credits()`, which adds credits rather than
removing them.

Focused coverage lives in
`src/api/tests/service/billing/test_billing_write_routes_refund_auth.py` and
`src/api/tests/service/billing/test_checkout_state_transition_contracts.py`.
The stable behavior is documented in
`docs/design-docs/billing-subscription-design.md`.

## Plan of Work

Remove the refund-time product lookup and positive grant call. Update the
top-up regression to prove 20 credits remain 20 and no refund bucket or refund
ledger is created. Update the subscription transaction test to prove refund
state and cancellation commit atomically without any credit mutation, while a
late local failure still rolls them back.

Clarify the design contract: subscription refund cancels access to subscription
credits; top-up refund does not yet reverse the original grant; neither path
issues a second positive grant.

## Concrete Steps

1. Remove `grant_refund_return_credits()` and its now-unused product lookup
   from `refund_billing_order()`.
2. Replace the refund tests that expect a positive grant with assertions that
   the wallet, buckets, and ledger receive no new credit mutation.
3. Update the billing design contract and regenerate the repository knowledge
   index.
4. Run the focused tests, complete billing suite, and repository gates listed
   below.

## Validation and Acceptance

- A paid 20-credit top-up remains at 20 credits after refund, never 40.
- Refund creates no positive refund bucket or refund ledger entry.
- A refunded subscription is canceled and its subscription credits are not
  usable under the existing eligibility rules.
- Repeating the direct refund creates no credit mutation and does not call the
  provider twice.
- Provider failure and a late local failure preserve existing rollback
  behavior.
- The independent usage-credit-return helper remains covered by its wallet
  lifecycle tests.

Validation commands:

    cd src/api
    pytest tests/service/billing/test_checkout_state_transition_contracts.py -q
    pytest tests/service/billing/test_billing_write_routes_refund_auth.py -q
    pytest tests/service/billing/test_billing_wallet_lifecycle_grants.py -q
    pytest tests/service/billing/ -q

Then run from the repository root:

    python scripts/build_repo_knowledge_index.py
    python scripts/check_repo_harness.py
    python scripts/check_uow_commit_sites.py
    python scripts/check_dev_tools.py
    lefthook run pre-commit --all-files

## Outcomes & Retrospective

The direct Stripe refund path no longer creates a positive refund bucket or
ledger entry. Focused refund and wallet tests passed. The complete billing
suite passed 1,651 tests and exposed one unrelated state-leak failure in the
creator-customization suite; that test passed when rerun in isolation. The
repository harness, unit-of-work ratchet, and focused Ruff checks passed.

## Idempotence and Recovery

An already-refunded billing order returns before the provider call, so replay
must continue to issue neither another provider refund nor any credit mutation.
Provider failure and late database failure retain the existing transaction
behavior. Recovery from a provider success followed by local failure is a
pre-existing concern and is not expanded by removing the positive grant.

## Interfaces and Dependencies

- Stripe remains behind the shared payment-provider adapter and
  `PaymentRefundRequest` / `PaymentRefundResult` contracts.
- Transaction ownership remains with `unit_of_work()` and
  `app_context_scope()`.
- This change does not alter database schemas, DTOs, public routes, or the
  `grant_refund_return_credits()` interface used by usage-credit restoration.

## Follow-up Work

Define and implement proportional/order-level credit reversal for top-ups and
subscriptions, including partially consumed grants, campaign bonuses, partial
monetary refunds, Stripe-initiated webhook convergence, and historical repair.
That work needs its own focused plan and pull request.

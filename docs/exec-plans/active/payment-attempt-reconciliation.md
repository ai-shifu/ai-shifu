# Payment Attempt Reconciliation

## Purpose / Big Picture

Provide one billing-service operation that settles non-paid plan orders before
a caller performs an irreversible lifecycle action. The operation distinguishes
paid, provider-confirmed unusable, and unresolved attempts across Stripe
Checkout, Stripe subscription renewal invoices, Ping++, Alipay, and WeChat Pay.
It does not terminate subscriptions, clear credits, or make operator-policy
decisions.

## Progress

- [x] 2026-10-03 18:00 CST: Created
  `feat/payment-attempt-reconciliation` from the latest `origin/main` in an
  isolated worktree.
- [x] 2026-10-03 18:15 CST: Confirmed that Stripe checkout orders store Session
  IDs, while Stripe renewal orders store subscription IDs and require
  invoice-level reconciliation.
- [x] 2026-10-03 18:30 CST: Implemented provider cancellation for asynchronous
  Stripe Checkout and Stripe subscription renewal invoices.
- [x] 2026-10-03 18:45 CST: Implemented the provider-neutral reconciliation
  service and durable order evidence.
- [x] 2026-10-03 19:00 CST: Added focused provider and orchestration tests
  covering asynchronous Checkout, unpaid and paid renewal invoices, durable
  evidence, missing references, and replay.
- [x] 2026-10-03 19:15 CST: Passed focused provider, billing state, callback,
  Ruff, architecture, repository harness, and full pre-commit gates.
- [x] 2026-10-03 19:20 CST: Pushed the branch and opened PR #3010.
- [x] 2026-10-03 20:00 CST: Bound Stripe renewal closure to the order's exact
  billing cycle, kept uncollectible invoices unresolved, and rejected terminal
  evidence when the order's provider reference changes during closure.
- [x] 2026-10-03 20:10 CST: Passed 106 provider contract tests, 4
  reconciliation tests, 43 checkout state-transition tests, and 12 callback
  tests after the review fixes.
- [x] 2026-10-03 20:20 CST: Passed the final repository gate; review fixes are
  ready to commit and push.

## Surprises & Discoveries

- Stripe renewal orders bind the Stripe subscription ID instead of the Invoice
  ID. Safe closure therefore has to list that subscription's invoices and
  select exactly one whose period matches the order's stored renewal cycle; it
  must not assume `latest_invoice` belongs to every order.
- A completed Stripe Checkout Session can still be unpaid for asynchronous
  methods. Session completion alone is not terminal payment evidence; its
  PaymentIntent must be canceled or shown as already canceled.
- Backend tests that initialize different application fixtures in one process
  can share the singleton configuration. Running the existing state-transition
  contract in its own process avoids an unrelated logging-path collision.

## Decision Log

- Return one of `paid`, `closed`, or `unresolved` for every order. Callers may
  proceed only when no result is unresolved.
- Do not treat local `FAILED`, `TIMEOUT`, `CANCELED`, or replacement metadata as
  proof that a provider can no longer collect money.
- Bind terminal evidence to provider name, provider reference, confirmation
  time, and reconciliation operation ID so it cannot be reused after the
  reference changes.
- Treat Stripe `uncollectible` as unresolved because it can still transition to
  paid; only a paid or void invoice is terminal evidence.
- Expose this as a billing-service API only. Integration with operator
  termination remains a separate change after this capability merges.

## Outcomes & Retrospective

The implementation now has a provider-neutral result contract and provider
support for the Stripe cases that previously left termination unable to
converge. Review follow-up now binds renewal invoices to exact billing cycles
and closes reference-replacement races. Production provider behavior still
requires test-environment acceptance before another feature consumes this
operation.

## Context and Orientation

`src/api/flaskr/service/billing/payment_attempt_reconciliation.py` owns the
orchestration and durable terminal evidence. The public billing boundary is
`src/api/flaskr/service/billing/api.py`. Provider lookup crosses the stable
`src/api/flaskr/service/order/payment_providers/api.py` boundary. Stripe-specific
closure behavior lives in
`src/api/flaskr/service/order/payment_providers/stripe.py`.

Billing orders for subscription start, upgrade, and renewal are included. Paid
and refunded orders are observations, not cancellation targets. Every provider
mutation happens outside the database transaction; local evidence is persisted
only after the provider confirms cancellation.

## Plan of Work

Extend the existing payment-provider cancellation contract for Stripe's async
Checkout and renewal-reference shapes. Add an orchestration service that loads
relevant subscription orders, attempts provider closure, synchronizes uncertain
results, and persists reference-bound terminal evidence. Export that service
through the billing API and cover provider and orchestration behavior with
focused regression tests.

## Concrete Steps

1. Resolve each non-paid plan order's existing provider reference type.
2. Ask the provider adapter to close that exact reference.
3. If closure is uncertain, use the existing order synchronization path and
   return `paid` only when normal paid-order processing confirms payment.
4. For Stripe renewal orders, require an exact invoice period match and keep
   ambiguous or uncollectible invoices unresolved.
5. After confirmed closure, lock the order and recheck payment status and the
   provider reference before recording cancellation and terminal evidence.
6. Return all per-order outcomes to the caller without performing subscription
   or credit mutations.

## Validation and Acceptance

- Open Stripe Checkout can be expired and becomes `closed`.
- Complete and unpaid asynchronous Stripe Checkout cancels its PaymentIntent or
  remains `unresolved`; it is never closed merely because the Session is
  complete.
- A Stripe renewal closes only the single invoice matching the order's stored
  billing cycle. Missing, duplicate, or uncollectible matches remain
  `unresolved`; a paid match synchronizes the order and becomes `paid`.
- Ping++, Alipay, and WeChat Pay use their existing provider cancellation
  contracts and persist terminal evidence only after confirmation.
- A missing reference or provider error leaves the order unchanged and returns
  `unresolved`.
- Replaying one operation does not repeat closure or paid side effects.
- If checkout reopens with a new provider reference while the previous attempt
  is being closed, the new reference is not marked canceled.

## Idempotence and Recovery

Replays first verify terminal evidence against the order's current provider and
reference, so a confirmed closure is not sent again. A paid race is detected
after locking the order and resolves to `paid`. A changed reference, provider
exception, ambiguous invoice match, or nonterminal invoice remains `unresolved`
and does not write terminal evidence, allowing a later retry to query and
converge without claiming success prematurely.

## Interfaces and Dependencies

- Reuse `PaymentProvider.cancel_payment`, `sync_billing_order`,
  `BillingOrder.metadata_json`, provider raw snapshots, and existing paid-order
  side effects.
- Extend the provider cancellation contract with optional reconciliation
  context; Stripe uses the expected renewal-cycle timestamps while other
  providers ignore the context.
- Export `PaymentAttemptReconciliation`,
  `SubscriptionPaymentReconciliationResult`, and
  `reconcile_subscription_payment_attempts` through the billing API.
- No schema migration or new table is required.

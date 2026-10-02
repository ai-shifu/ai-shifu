# Operator Paid Subscription Termination

## Purpose / Big Picture

Add an operator-only User Management action that immediately terminates the
user's current paid or operator-granted plan. Termination stops provider renewal
where applicable, marks the subscription ineffective immediately, and forfeits
the remaining credits attributable to that plan. Credit packs, referral rewards,
and other promotional credits are not removed. A plan with zero remaining plan
credits can still be terminated.

## Progress

- [x] 2026-10-01 CST: Created `feat/operator-subscription-termination` from
  the latest `origin/main`, including #3006.
- [x] 2026-10-01 CST: Inspected subscription cancellation, provider adapters,
  domestic prepaid renewal events, paid/manual grants, wallet buckets, and the
  operator user action surface.
- [x] 2026-10-01 CST: Implemented the idempotent termination workflow with
  paid-origin safeguards and recoverable provider retry state.
- [x] 2026-10-01 CST: Added the operator confirmation UI, API contract,
  translations, and privacy-bounded analytics.
- [x] 2026-10-01 CST: Added focused subscription, wallet, provider-boundary,
  route, dialog, and page coverage; all repository pre-commit gates passed.

## Surprises & Discoveries

- Stripe's existing `cancel_subscription()` schedules cancellation at period
  end; immediate operator termination needs a distinct provider operation.
- Domestic providers (`pingxx`, `alipay`, `wechatpay`) are self-managed prepaid
  subscriptions. They have no remote recurring subscription to delete, but
  local renewal/preorder events must be canceled.
- Subscription-category wallet buckets are reused. Paid plan grants can
  therefore share a bucket with historical manual plan grants. Bucket balance
  alone cannot safely identify the paid remainder.
- Referral rewards use their own manual-source subscription-category buckets;
  credit packs use top-up buckets. Neither may be forfeited by this operation.
- The local Python environment does not install the optional `stripe` package,
  so the existing Stripe provider contract module cannot collect locally. The
  shared provider boundary test and all repository gates pass; CI remains the
  execution environment for the focused Stripe SDK mock test.

## Decision Log

- Decision: Target an effective subscription backed by either a paid provider
  order or an operator manual-plan grant. Recognize both current
  `admin-plan-grant:` references and historical unmarked manual subscription
  orders. Referral reward plans and trials remain excluded by their explicit
  metadata.
- Decision: Stripe is terminated immediately through a dedicated provider
  adapter method. Self-managed domestic prepaid plans are terminated locally
  and all future renewal/preorder lifecycle events are canceled.
- Decision: Forfeit available balance only from a subscription bucket whose
  grant ledger proves exclusively eligible paid or operator-granted plan origins.
  If a non-zero bucket contains reward, unknown, or conflicting grant
  origin, reject the entire operation for manual reconciliation instead of
  guessing. An open usage reservation also rejects until its in-flight operation
  settles, avoiding a dangling hold. A zero-balance bucket never blocks
  termination.
- Decision: Do not mutate top-up or reward buckets.
- Decision: Record forfeiture as negative expiry ledger entries and move the
  bucket's available/reserved amounts into expired credits so wallet audit
  invariants remain balanced. The operation uses a client request ID for replay.

## Outcomes & Retrospective

The implementation covers immediate Stripe termination, domestic prepaid and
operator-granted local termination, eligible-plan credit forfeiture, mixed-origin refusal,
zero-balance termination, request replay, operator UI, and analytics. Final
repository-wide verification has passed. Focused backend tests pass (5 domain
and provider-boundary tests plus 94 operator-route tests), and focused frontend
tests pass (33 dialog/page tests).

## Context and Orientation

Subscription lifecycle behavior lives in
`src/api/flaskr/service/billing/subscriptions.py`; provider adapters live under
`src/api/flaskr/service/order/payment_providers/`; wallet buckets and ledgers
live in `src/api/flaskr/service/billing/wallets.py` and `models.py`. Operator
routes and orchestration live under
`src/api/flaskr/service/shifu/admin_operations/`. The User Management action
menu is in `src/web/src/app/admin/operations/users/page.tsx`.

## Plan of Work

Add a termination service that locks and validates the current paid plan and
its forfeitable balance, performs the provider action outside the database unit
of work, then revalidates and finalizes subscription, renewal events, paid plan
bucket, ledger, and wallet state atomically. Expose this through an
operator-only endpoint and one destructive confirmation dialog that identifies
the account, explains the effects, and requires a reason before submission.

## Analytics Contract

The UI emits `operator_subscription_termination_attempt` immediately before a
valid confirmed request and `operator_subscription_termination_result` once on
success or failure. The eligible population is authenticated operators using
User Management; opening or dismissing the dialog and invalid forms are
excluded. A pending single-flight guard deduplicates repeated clicks. The only
allowlisted payload is `surface=operator_user_management`, plus
`outcome=success|failed` for the result. User IDs, contact details, subscription
IDs, provider IDs, balances, reasons, request IDs, dates, and raw errors are
never tracked. Operations reliability reporting is the downstream consumer;
analytics is best-effort and never changes the termination result.

## Concrete Steps

1. Add immediate provider termination capability for Stripe and a local-only
   path for self-managed prepaid providers.
2. Add paid-subscription selection, origin validation, forfeiture ledger, and
   request replay behavior.
3. Add operator DTOs/routes plus focused backend tests.
4. Add frontend API types, action/dialog, translations, analytics, and tests.
5. Update product/billing documentation and generated indexes.
6. Run focused suites and the repository pre-commit gate.

## Validation and Acceptance

- Stripe paid plan: remote subscription ends immediately, local status becomes
  canceled, future renewal events disappear, and eligible paid plan credits
  become unavailable.
- Domestic prepaid paid plan: local subscription ends immediately and future
  renewal/preorder processing stops without calling an unsupported remote
  subscription API.
- Zero remaining paid plan credits still permits successful termination.
- Credit-pack balances are unchanged.
- Manual plan and referral reward balances are unchanged.
- A non-zero mixed/unknown subscription bucket rejects without changing the
  subscription, wallet, or provider.
- Replaying one request does not repeat provider termination or ledger writes.
- The operator UI clearly identifies the account and plan, warns that the
  action is immediate, requires confirmation, prevents duplicate submission,
  refreshes user data, and reports a privacy-safe terminal result.

## Idempotence and Recovery

Use the operator request ID as the local forfeiture ledger identity and persist
provider termination evidence in subscription metadata. Before retrying an
uncertain provider result, query or reconcile the provider subscription rather
than creating a second external action. Local finalization is one unit of work;
provider I/O never occurs inside a database transaction.

## Interfaces and Dependencies

- Existing `BillingSubscription`, `BillingOrder`, `CreditWalletBucket`, and
  `CreditLedgerEntry` tables are reused; no new table is planned.
- The payment-provider base contract gains an immediate termination method;
  Stripe implements it, while prepaid domestic providers remain local-only.
- The frontend uses the existing operator API client, dialog primitives, i18n
  namespaces, and Umami tracking helper.

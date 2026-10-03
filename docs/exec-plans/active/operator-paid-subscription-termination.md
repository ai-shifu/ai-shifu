# Operator Paid Subscription Termination

## Purpose / Big Picture

Add an operator-only User Management action that immediately terminates the
user's current paid or operator-granted plan. Termination stops provider renewal
where applicable, marks the subscription ineffective immediately, and forfeits
all available credits in the current shared subscription bucket. This includes
active trial or referral credits already mixed into that bucket. Separate credit
packs are not removed. A plan with zero remaining plan credits can still be
terminated; any reserved balance remains a safety blocker until deferred rewards
can be separated in follow-up work.

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
- [x] 2026-10-02 CST: Aligned list eligibility and execution to prefer the
  active subscription proven by the currently available plan-credit grant;
  zero-balance accounts retain the product-priority fallback.
- [x] 2026-10-03 CST: Completed the first mixed-bucket phase: terminate the
  eligible plan and clear its entire available subscription bucket, including
  active trial/referral credits mixed into it, while preserving the reserved
  balance blocker and all separate top-up buckets.
- [x] 2026-10-03 CST: Bound confirmation and execution to one subscription ID,
  resolved the target bucket through that subscription's eligible grant ledger,
  isolated it from concurrent new-plan grants, and blocked late activation of
  operator-terminated subscriptions.
- [x] 2026-10-03 CST: Blocked termination while the target subscription has an
  unsettled plan order and made cycle repair preserve operator termination as a
  terminal state.
- [ ] After #3009 merges: deliver PR 1.1 for termination operational hardening:
  protect the free-text reason from generic request-body logs and refresh the
  affected user row after a failed/uncertain request.
- [ ] After PR 1.1: deliver PR 2 to move deferred invitation rewards out of a
  paid plan bucket while preserving their scheduled activation.
- [ ] After PR 2: deliver PR 3 to permit termination when deferred invitation
  rewards exist, while keeping genuine in-flight usage reservations blocked.

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
  credit packs use top-up buckets. Independently stored rewards and top-ups are
  not forfeited, but historical trial/referral grants can share the paid bucket.
- A creator can retain multiple effective subscription rows. Product priority
  alone can select a different row from the order that granted the currently
  available plan credits.
- The local Python environment does not install the optional `stripe` package,
  so the existing Stripe provider contract module cannot collect locally. The
  shared provider boundary test and all repository gates pass; CI remains the
  execution environment for the focused Stripe SDK mock test.
- Selecting a bucket by runtime category is insufficient when the paid bucket
  is empty: a separate reward bucket can become the primary category bucket.
  The terminating order's grant ledger is the durable bucket identity.
- A provider call creates an unavoidable transaction gap. Marking the pinned
  old bucket as termination-pending prevents a concurrent new plan grant from
  reusing it; finalization must keep the stored bucket ID and never retarget to
  whichever bucket is current after provider I/O.
- A pending upgrade can complete payment while termination is in progress.
  Allowing both paths to succeed leaves a paid order with neither credits nor
  an active plan because late activation is intentionally fenced.
- Subscription cycle repair treats paid-order history as repair evidence, but
  that evidence must not override an explicit operator termination decision.

## Decision Log

- Decision: Target an effective subscription backed by either a paid provider
  order or an operator manual-plan grant. Recognize both current
  `admin-plan-grant:` references and historical unmarked manual subscription
  orders. Referral reward plans and trials remain excluded by their explicit
  metadata.
- Decision: When available plan credits exist, resolve the termination target
  through the active bucket's current grant ledger and eligible order before
  applying product priority. When no balance-backed grant exists, fall back to
  the existing effective-plan priority so zero-balance plans remain terminable.
- Decision: Stripe is terminated immediately through a dedicated provider
  adapter method. Self-managed domestic prepaid plans are terminated locally
  and all future renewal/preorder lifecycle events are canceled.
- Decision: Once an eligible paid/operator-granted subscription is proven,
  forfeit the entire available balance of the current shared subscription
  bucket. Active trial or referral rewards already mixed into that bucket are
  inseparable and therefore end with the plan. Independently stored reward and
  top-up buckets remain untouched.
- Decision: Reject termination whenever the target subscription bucket has a
  reserved balance. It may represent in-flight usage or a deferred invitation
  reward; migrating future rewards into an independent bucket is explicitly
  deferred to the next PR. A zero-balance bucket never blocks termination.
- Decision: The list response exposes the exact eligible subscription ID. The
  dialog displays and submits it, and the backend rejects the operation if the
  currently selected subscription differs from the confirmed ID.
- Decision: During provider I/O, pin the original bucket in operation metadata
  and exclude a termination-pending bucket from runtime reuse. Finalization may
  absorb changes to that exact old bucket but may never switch to a new bucket.
  Bucket reuse takes a current-read row lock, and preparation rechecks the
  latest eligible plan grant while holding the bucket lock, closing the race
  where a grant selected the old bucket just before the marker committed.
- Decision: Paid-event activation and credit grant paths reject `TERMINATING`
  subscriptions and `CANCELED` subscriptions carrying a completed operator
  termination marker. Ordinary canceled subscriptions retain existing behavior.
- Decision: Reject termination while any start, upgrade, or renewal order for
  the target subscription can still become paid through provider sync or a
  webhook. This includes `INIT`, `PENDING`, `FAILED`, `TIMEOUT`, and ordinary
  `CANCELED` orders; a canceled order explicitly invalidated as
  `replaced_by_new_package` is exempt because the payment state machine already
  forbids its revival. The order rows are locked before the subscription enters
  `TERMINATING`, so payment completion wins or termination rolls back; the
  system never locally cancels a possibly paid provider order without provider
  reconciliation.
- Decision: Cycle repair always skips `TERMINATING` subscriptions and canceled
  subscriptions carrying the operator termination marker. Historical paid
  cycles cannot restore their dates or status.
- Decision: Record forfeiture as negative expiry ledger entries and move the
  bucket's available/reserved amounts into expired credits so wallet audit
  invariants remain balanced. The operation uses a client request ID for replay.

## Outcomes & Retrospective

The implementation covers immediate Stripe termination, domestic prepaid and
operator-granted local termination, whole-current-bucket forfeiture, reserved-balance
refusal, zero-balance termination, request replay, operator UI, and analytics. Final
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

## Pull Request Sequence

1. **PR 1 — #3009, core termination:** bind the confirmed subscription and
   grant-backed bucket, terminate provider/local lifecycle state, clear only the
   pinned active plan bucket, preserve independent rewards/top-ups, and close
   replay and concurrent-purchase races.
2. **PR 1.1 — operational hardening:** build from `main` after #3009. Mark the
   termination endpoint request body as sensitive so the free-text `reason`
   never enters generic request logs. On failed or uncertain termination,
   refresh the affected user row and eligibility so `TERMINATING` or completed
   state is visible and the operator cannot act on stale UI state. This is a
   production-rollout gate but does not change credit ownership rules.
3. **PR 2 — deferred reward separation:** move future/unactivated invitation
   rewards from a paid plan bucket into an independent reward bucket, retaining
   the original activation time, expiry, idempotency, and audit trail. Keep the
   termination blocker in place while migration is incomplete.
4. **PR 3 — reserved-reward-aware termination:** distinguish migrated deferred
   rewards from genuine usage reservations, allow termination when only
   deferred rewards exist, and verify those rewards still activate later.

PR 1.1 deliberately precedes PR 2 and PR 3. It touches the termination route
and dialog rather than the reward migration model, avoids mixing privacy/UI
recovery with bucket migration, and ensures operational safeguards are present
before the broader termination cases are enabled.

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
- A separate manual/reward bucket is unchanged. Active trial/referral credits
  already mixed into the paid plan bucket are cleared with that bucket.
- Any reserved balance in the target subscription bucket rejects without
  changing the subscription, wallet, or provider.
- Replaying one request does not repeat provider termination or ledger writes.
- A separate reward bucket remains intact when the paid bucket is exhausted;
  a concurrent new plan receives a different bucket and survives old-plan
  finalization; late paid/manual event replay cannot revive the old plan.
- Submitting a stale dialog after the target subscription changes is rejected.
- A target subscription with a plan order that provider sync or webhook can
  still mark paid is rejected without changing either order or subscription;
  after payment settles or provider reconciliation makes it terminal, the
  operator can retry against the resulting current state.
- Cycle repair leaves an operator-terminated subscription canceled with its
  shortened terminal period.
- The operator UI clearly identifies the account and plan, warns that the
  action is immediate, requires confirmation, prevents duplicate submission,
  refreshes user data, and reports a privacy-safe terminal result.
- Before production rollout, generic request logging does not record the
  termination `reason`, and a failed/uncertain request refreshes the affected
  row so the displayed state and available actions match the server.

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

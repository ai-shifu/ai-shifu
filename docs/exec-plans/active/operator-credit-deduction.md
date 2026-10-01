# Operator Credit Deduction

## Purpose / Big Picture

Add a dedicated operator action on user management that deducts currently
spendable credits. The operation consumes paid subscription/top-up buckets
before manually granted credit buckets, supports credit values with at most two
decimal places, rejects insufficient balances atomically, and is idempotent by
client request ID.

This is an audited manual adjustment. It is not a payment refund, usage
settlement, package cancellation, or authorization to deduct reserved,
inactive, future, or expired credits.

## Progress

- [x] 2026-09-30: Created `feat/operator-credit-deduction` from current main.
- [x] 2026-09-30: Inspected the existing operator grant UI, admin routes,
  wallet adjustment helper, bucket ordering, and analytics contract.
- [x] 2026-09-30: Implemented the paid-first idempotent wallet mutation,
  operator service, DTOs, and route.
- [x] 2026-09-30: Added the operator dialog, two-step confirmation,
  translations, API contract, and privacy-bounded analytics.
- [x] 2026-09-30: Passed focused backend wallet, service, route, frontend
  dialog/page, lint, repository harness, architecture, and UoW checks.
- [x] 2026-09-30: Re-ran the full pre-commit gate successfully. Recorded the
  separate repository-wide frontend type-check failures for follow-up; none are
  in files changed by this plan.

## Surprises & Discoveries

- The existing negative `adjust_credit_wallet_balance()` can span buckets, but
  it creates a random operation identity and sorts manual subscription-category
  buckets alongside paid subscription buckets. It therefore cannot satisfy
  request replay or paid-first behavior directly.
- Ordinary manual credit grants have `source_type=MANUAL` and their own bucket.
  Subscription/top-up buckets use their matching source types. Manually granted
  packages can share those category buckets with paid orders, so the current
  `source_bid` cannot prove the remaining balance's payment provenance; package
  buckets stay in the package tier instead of being guessed from the latest
  order.

## Decision Log

- Decision: Add a dedicated deduction API instead of accepting negative values
  in the grant API. Rationale: permissions, validation, analytics, copy, and
  idempotency are different contracts.
- Decision: Deduct eligible subscription/top-up package buckets first and
  eligible direct manual-credit grant buckets second. Preserve the existing
  expiry/creation/database-ID ordering inside each tier. Reward and
  refund-return metadata is explicitly excluded.
- Decision: Reject the entire request when paid plus manual eligible credits
  are insufficient. Do not touch other gift/refund buckets or reserved credit.
- Decision: Accept positive decimal strings with at most two fractional digits
  and use Decimal throughout.
- Decision: Continue representing a manual debit as negative ADJUSTMENT ledger
  rows and consumed bucket balance so the existing bucket invariant remains
  valid. Usage reporting must continue to count CONSUME, not ADJUSTMENT rows.

## Context and Orientation

The backend wallet mutation lives in
`src/api/flaskr/service/billing/wallets.py`; the operator-facing orchestration,
DTOs, and route live under `src/api/flaskr/service/shifu/admin_operations/` and
`src/api/flaskr/service/shifu/admin_dtos_users.py`. Wallet buckets are the
source of truth for available credit, while `CreditLedgerEntry` records each
grant, consumption, expiry, or adjustment.

The User Management list is implemented in
`src/web/src/app/admin/operations/users/page.tsx`. The deduction workflow uses
its own dialog beside the existing grant dialog, with request types in
`operation-user-types.ts` and the endpoint mapping in `src/web/src/api/api.ts`.
Shared user-facing copy lives under `src/i18n/<locale>/modules/`.

## Analytics Contract

### operator credit deduction

- Business question: how often do operators attempt credit deductions and what
  share reaches a successful terminal result?
- Metric definition: count accepted HTTP attempts and terminal outcomes by
  outcome during a selected reporting period; no exact one-to-one correlation
  is claimed because no request ID is collected.
- Events: `operator_credit_deduction_attempt` and
  `operator_credit_deduction_result`.
- Actor/surface: authenticated operators on `operator_user_management`.
- Trigger: attempt immediately after valid confirmation and before HTTP;
  result once after the request resolves or rejects.
- Population: operator accounts only; exclude invalid forms, cancelled
  confirmation, and guarded duplicate clicks.
- Deduplication: pending single-flight guard; deliberate later retries count as
  new attempts.
- Consumer: operations workflow reliability reporting.
- Compatibility: additive v1 event family.

Payload allowlist:

| Field | Type | Allowed values | Privacy | Why |
| --- | --- | --- | --- | --- |
| `surface` | string | `operator_user_management` | non-personal | distinguish workflow surface |
| `outcome` | string | `success`, `failed` (result only) | non-personal | terminal success rate |

Do not emit target IDs, contact data, amount, reason/note, request ID, bucket
IDs, balances, dates, or raw errors. Analytics remains fire-and-forget and
cannot affect deduction behavior.

## Plan of Work

Add a wallet-domain operation that locks the wallet and eligible buckets,
classifies paid versus manual origin, validates the total before mutation,
deducts across buckets in tiered runtime order, writes one negative adjustment
ledger row per bucket, refreshes the wallet snapshot, and returns the original
result on request replay.

Expose the operation through an operator-only DTO and route adjacent to credit
grant. Add a separate deduction dialog and action so grant/package state does
not absorb debit behavior. Refresh user and billing data after success.

## Concrete Steps

1. Add backend result/request contracts and paid/manual bucket classification.
2. Add backend service orchestration, route, and focused atomicity/idempotency
   tests.
3. Add frontend API types, user action, deduction dialog, i18n, analytics, and
   focused tests.
4. Update the billing design and generated knowledge indexes.
5. Run focused tests, type/lint checks, backend billing tests, and pre-commit.

## Validation and Acceptance

- A 600.25 paid + 400.50 manual balance can deduct 800.40 as 600.25 paid and
  200.15 manual, leaving 200.35 manual.
- Paid eligible buckets are exhausted before any manual bucket changes.
- Within each tier the existing runtime ordering is preserved.
- Insufficient eligible balance writes nothing.
- Reserved, inactive, future, expired, gift, and refund-return buckets are not
  deducted.
- Replaying one request ID returns the original result without another debit.
- Every changed bucket has one negative adjustment ledger entry and wallet,
  bucket, and ledger state commit atomically.
- The operator UI validates two-decimal positive input, requires a reason,
  confirms the action, prevents duplicate submission, refreshes data, and
  reports analytics without sensitive fields.

## Idempotence and Recovery

Use `operator_credit_deduction:{request_id}:{wallet_bucket_bid}` as ledger
identity and the normalized request ID as the operation source. A replay must
validate the original requested amount and return the persisted ledger/bucket
result. The whole mutation is one database unit of work; no external side
effect is required.

## Interfaces and Dependencies

- Backend remains within billing wallet helpers and shifu operator routes.
- Frontend uses the existing generated API map and shared request path.
- No database migration or new table is required.
- Existing credit notification behavior is unchanged; deductions do not send
  a credit-granted notification.

## Outcomes & Retrospective

The implementation now provides a dedicated paid-first operator deduction with
decimal validation, atomic insufficient-balance rejection, per-bucket audit
entries, request replay protection, a two-step operator UI, and privacy-bounded
analytics. Focused checks pass. The repository-wide frontend type-check is
currently blocked by pre-existing errors in the user-detail test and
MarkdownFlow locale mapping, neither changed by this work.

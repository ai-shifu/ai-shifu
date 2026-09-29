# Preserve Independent Credit Validity

## Purpose / Big Picture

Prevent a subscription start or upgrade from shortening independently granted
credit validity. Audit China production for historical rows affected by the
same transition and prepare an explicit, reviewable recovery list without
mutating production during the audit.

## Progress

- [x] 2026-09-29 18:05 CST: Reconciled the reported account wallet, buckets,
  ledger, subscription, renewal event, and usage history with read-only queries.
- [x] 2026-09-29 18:12 CST: Reproduced the causal path in current `main`: a
  subscription start realigns all runtime-subscription buckets, including
  manual grants that do not require an active subscription.
- [x] 2026-09-29 18:24 CST: Added focused regression coverage and excluded
  subscription-independent buckets from cycle realignment.
- [x] 2026-09-29 18:31 CST: Passed focused Ruff, 42 relevant billing tests,
  and the repository harness. The full billing suite reached 1,355 passing
  tests but its app-backed tests were blocked by the checkout's pre-existing
  `/var/log/ai-shifu.log` permission configuration.
- [x] 2026-09-29 18:27 CST: Audited production impact: five manual-grant
  buckets were shortened by the cache-overcharge bonus subscription and later
  expired, totaling 146,729.23 credits. One separate still-active aligned
  compensation row was excluded from the loss set.
- [x] 2026-09-29 18:54 CST: Added an evidence-gated, idempotent recovery script
  and ran it without `--apply` in a China production API pod. All five targets
  were eligible and the computed total matched 146,729.23 credits.
- [x] 2026-09-29 19:08 CST: Addressed PR review by persisting recovery
  provenance in the grant transaction, preserving historical idempotency
  verification after expiry, and blocking possible compensation under another
  idempotency key.
- [ ] Obtain explicit recovery scope approval before running the production
  script with `--apply`.

## Surprises & Discoveries

- The affected 55,000-credit manual reward was issued with legacy `1y`
  validity, but its grant ledger `updated_at` changed at the exact timestamp of
  the later cache-overcharge bonus subscription grant.
- The bonus subscription renewal later failed with
  `renewal_order_context_unavailable`; the expiry worker then expired both the
  bonus balance and the already-shortened manual balance.

## Decision Log

- Decision: treat manual and gift buckets as independent of subscription cycle
  boundaries, matching `wallet_bucket_requires_active_subscription()`.
  Rationale: admission already permits these balances without an active
  subscription, so changing their explicit expiry during a subscription
  transition violates the existing contract.
- Decision: keep production auditing and recovery read-only until the exact
  target rows, amounts, and replacement expiries are reviewed.

## Outcomes & Retrospective

Pending implementation and verification.

The preventive fix and production impact audit are complete. Production
recovery tooling and its production dry-run are also complete. The write
remains intentionally pending explicit approval of whether to restore only the
reported account or all five confirmed affected accounts.

## Context and Orientation

Subscription credit grants are orchestrated in
`src/api/flaskr/service/billing/subscriptions.py`. Start and upgrade grants call
the shared realignment helper in
`src/api/flaskr/service/billing/cycle_state_transitions.py`. Bucket runtime
classification and subscription-dependency semantics live in
`src/api/flaskr/service/billing/bucket_categories.py`.

## Plan of Work

Add a regression fixture containing an active manual grant with a longer
explicit expiry, apply a subscription-cycle realignment, and assert the manual
bucket and its grant ledger retain that expiry while true subscription credit
still follows the cycle. Narrow the shared loader/realignment behavior using
the existing subscription-dependency predicate. Then scan production for
manual or gift grant ledgers whose expiry was updated at a later subscription
start/upgrade and that subsequently produced an expiry entry.

## Concrete Steps

1. Extend the focused cycle-state bucket realignment tests.
2. Update the shared realignment helper without changing public DTOs or schema.
3. Run the focused pytest file, billing suite as warranted, Ruff, and harness
   checks for the new ExecPlan.
4. Run read-only production SQL to enumerate affected buckets and calculate
   recoverable independent balances and intended expiries.

## Validation and Acceptance

- A subscription start/upgrade must not change a manual or gift bucket's
  `effective_to` or its grant ledger `expires_at`.
- Subscription-owned credits must still align with their subscription cycle.
- The reported account must appear in the audit with an evidence-backed amount
  and intended expiry.
- No production write occurs without a separately reviewed recovery command.

## Idempotence and Recovery

The code change is behavior-preserving on repeated calls because excluded
buckets are untouched and eligible rows continue to be assigned the same cycle
end. Any later recovery must use stable idempotency keys and verify existing
repair entries before writing.

## Interfaces and Dependencies

No external API, DTO, schema, analytics, or provider contract changes. The fix
reuses the existing bucket classification and subscription-dependency helpers.

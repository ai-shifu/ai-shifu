# Billing refund retry and reconciliation

## Purpose / Big Picture

Prevent a billing refund retry from creating another external refund after
Stripe succeeds but the local transaction fails. A separate PR follows the
metadata serialization correction in #2888. The public teacher refund route
remains disabled; existing order, subscription, and credit-return semantics
remain the finalization contract.

## Progress

- [x] 2026-09-21 05:14 CST: Confirmed the missing durable refund identity and
  provider/local transaction gap against #2888 and its base.
- [x] 2026-09-21 05:14 CST: Created an isolated branch based on #2888 and copied
  local environment files without overwriting or committing them.
- [x] 2026-09-21 05:14 CST: Chose a dedicated refund operation journal rather
  than order metadata, which several existing writers can overwrite.
- [x] 2026-09-21 05:24 CST: Implemented provider reconciliation; all 293 order
  domain tests passed, including 98 new adversarial provider cases.
- [x] 2026-09-21 05:26 CST: Generated and reviewed the journal migration;
  eight migration cases passed across SQLite and an isolated MySQL instance.
  The complete fresh MySQL migration chain, downgrade, and re-upgrade passed.
- [x] 2026-09-21 05:28 CST: Implemented durable intent, external reconciliation,
  and atomic local finalization; 25 core cases passed, including two real
  MySQL concurrency cases with independent sessions and no external payments.
- [x] 2026-09-21 05:45 CST: Addressed status changes, stale responses, and
  invalid request parameters. The independent original reproductions and
  additional observation-conflict checks passed after the fixes.
- [x] 2026-09-21 05:57 CST: Final full backend verification passed: 5499 tests,
  107 skips, and 50 subtests. Developer-tool doctor, all-files lefthook,
  repository harness, architecture boundaries, and unit-of-work checks passed.
  Implementation is ready for the separate PR and its current-head CI follow-up.
- [x] 2026-09-21 05:55 CST: Final focused verification passed all 46 cases,
  including the MySQL precision regression and result-commit failure recovery.
  Both real-MySQL cases passed in three consecutive independent runs.

## Surprises & Discoveries

- A refund currently calls Stripe inside the same unit of work as all local
  writes. Rolling back those writes cannot roll back the external refund.
- The existing rollback test deliberately fails after the credit grant but
  never retries, so it does not detect duplicate external refunds.
- A stable Stripe key alone is insufficient: Stripe may prune keys after at
  least 24 hours. Every recovery must reconcile before considering a retry.
- Order metadata is not a durable operation journal. Webhook, sync, and
  notification paths replace whole JSON values from their current snapshots.
- The existing creator credit lock is intentionally fail-open. Correctness
  must rely on database constraints and locked finalization, independently of
  that best-effort contention reduction.
- A webhook may mark the original order refunded before local credit and
  subscription finalization. The operation's completion marker must decide
  whether that local work has finished.
- Stripe can change a previously successful refund to `requires_action` or
  `failed` after a bank returns the funds. Independent failure-first tests
  reproduced the danger of permanently retaining success before local
  finalization. A versioned observation must accept later provider evidence
  while rejecting stale concurrent responses.
- The optional existing fresh-MySQL test has an outdated Langfuse stub and
  fails during app import. The complete migration chain was instead verified
  against a fresh isolated MySQL schema through a minimal Flask/Alembic app.
- Real MySQL concurrency exposed fractional-second rounding in `DATETIME(0)`:
  storing a timestamp ending in `.8` can round it into the future and make an
  immediate retry fail the clock-regression guard. The initial submission
  timestamp is floored to whole seconds before persistence, conservatively
  shortening the retry window rather than widening it. The concurrent test
  fixes the clock at `.8` to reproduce this deterministically.

## Decision Log

- Preserve one terminal refund operation per billing order. This change does
  not introduce a series of independently requested partial refunds.
- Store immutable operation identity, payment identity, amount, currency,
  reason, provider evidence, submission time, and finalization time in
  `bill_refund_operations`, with a unique original billing-order key.
- Commit intent before HTTP. Use a separate short unit of work for each
  persistence step, and reject callers already owning the same transaction.
- Resolve an omitted amount to the original paid amount before creating the
  operation. Replays reuse the stored parameters; conflicting explicit
  parameters fail rather than allocating a different identity.
- Reconcile an explicit refund reference or exact operation metadata first.
  Historical unkeyed recovery requires full payment-reference, ownership,
  amount, currency, and pagination checks. An unreferenced legacy partial
  refund, conflicting evidence, or unknown provider status fails closed.
- Persist the first submission timestamp before sending. Reuse the same key
  and parameters only inside a conservative 23-hour retry window. An older
  uncertain submission with no provider result requires reconciliation;
  elapsed time never authorizes another operation or a new key.
- Only `succeeded` finalizes local business state. `pending` and
  `requires_action` retain their provider identity and remain pending.
  Failed/canceled outcomes do not allocate a second operation.
- Version provider observations in the journal. Persist a result only if its
  captured version still matches; otherwise query again with the current
  version, with bounded retries. Before local finalization, a later valid
  provider status replaces an earlier success.

## Outcomes & Retrospective

The implementation prevents retries from creating a new external refund and
keeps local completion atomic. Verification used real SQLite transactions,
independent sessions against isolated MySQL 26.7.0 schemas, strict Stripe SDK
replacements, and the complete backend suite. No live payments were invoked.

The full-suite run needed proxy environment variables removed because the
local SOCKS proxy configuration required an optional HTTPX package; the seven
affected existing tests then passed. Optional existing tests account for the
107 skips. The standalone full-MySQL migration check avoided the unrelated
existing Langfuse stub defect described above. Historical ambiguous partial
refunds still require manual reconciliation, and the public route remains
disabled. Publication and current-head CI evidence belong to the pull request.
The original #2888 thread remains open while its separate fix awaits merging.

## Context and Orientation

`src/api/flaskr/service/billing/checkout.py` owns the existing refund entry
point. Billing business state is separate from legacy learner orders.
`service/order/payment_providers` is the shared external-provider boundary;
only its Stripe implementation currently supports billing refunds. The
existing metadata fix is PR #2888, and this branch targets that branch so its
diff contains only refund retry/reconciliation work.

`dao/uow.py` owns commits and rollback. `models.py` owns billing schema, and
Alembic migrations own production schema changes. Existing billing tests use
isolated databases; provider tests replace the Stripe SDK without making
external payments.

## Plan of Work

1. Extend the provider abstraction with read-only refund reconciliation.
2. Add the durable operation model, uniqueness constraints, and migration.
3. Split refund execution into short persistence phases surrounding provider
   calls. Preserve existing raw snapshots, subscription lifecycle handling,
   and credit-return behavior inside atomic finalization.
4. Add failure-first regressions and real database interleaving tests.
5. Update the canonical billing design and run focused then broader checks.
6. Publish one ready PR, link the original finding, and independently verify
   review feedback and CI for the published head.

## Concrete Steps

Work from the isolated `sunner/refund-retry-reconciliation` checkout.

    cd src/api
    python -m pytest -p no:testmon tests/service/order/test_stripe_refund_reconciliation.py tests/service/billing/test_refund_retry_reconciliation.py -q
    python -m pytest -p no:testmon tests/service/billing tests/service/order -q

At repository root, run the developer-tool doctor, repository harness,
architecture boundaries, unit-of-work ratchet, and all-files lefthook gate.
Generate the Alembic revision from the model against an isolated baseline,
inspect upgrade/downgrade SQL, and verify the resulting schema independently.

## Validation and Acceptance

- External success followed by local failure and retry produces exactly one
  provider refund and one committed local credit-return transition.
- Concurrent requests preserve one immutable operation and cannot finalize
  the same subscription, snapshot, or ledger return twice.
- Provider calls run with neither an active unit of work nor a database
  transaction implicitly opened by expired ORM attributes.
- Historical successful full refunds reconcile without another POST;
  ambiguous, partial-without-identity, or mismatched evidence never creates a
  refund automatically.
- Pending/requires-action refunds cannot grant credits or cancel a
  subscription; a later successful query completes the same operation.
- An expired uncertain request with no provider result cannot issue a new
  POST. Conflicting amounts/reasons/payment identities are rejected.
- Migration upgrade/downgrade and unique-operation constraints are verified.
- The disabled public refund route remains absent.

## Idempotence and Recovery

The durable operation record survives local finalization failure. Recovery
uses its immutable request and existing provider identity. Failed local work
rolls back atomically while preserving committed intent and external-result
evidence. Uncertain or contradictory historical evidence is retained for
operator reconciliation rather than converted into permission to refund.

## Interfaces and Dependencies

`PaymentProvider.reconcile_refund(request, app)` returns a validated
`PaymentRefundResult` or `None` only after a complete, valid empty provider
query. It never creates a refund. Metadata includes the original payment
references, `currency`, `payment_amount`, `refund_operation_bid`, optional
`refund_reference_id`, and owner identifiers. The create call additionally
uses the operation's stable `idempotency_key` as a Stripe request option.

Provider documentation: [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests)
and [Stripe refunds](https://docs.stripe.com/api/refunds).

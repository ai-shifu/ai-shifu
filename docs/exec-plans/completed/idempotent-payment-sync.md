# Keep common payment synchronization idempotent

> Lifecycle review, 2026-09-26: Completed original scope. The recorded 72 focused and 187 order tests cover retry-safe payment side effects; no new provider rollout is claimed. Merge evidence: [#2857](https://github.com/ai-shifu/ai-shifu/pull/2857) (`56e1e884b`)

## Purpose / Big Picture

The common learner `/payment/sync` entry must not wrap Stripe's dedicated
transaction owner in another unit of work, and concurrent native-provider
synchronizations must not schedule duplicate success side effects.

## Progress

- [x] 2026-09-18 22:16 CST: Confirmed the common Stripe dispatch is nested
  inside the generic sync transaction and native synchronization lacks the
  per-order payment lifecycle lock.
- [x] 2026-09-18 22:31 CST: Separated Stripe dispatch from the common
  preflight transaction and revalidated native orders under the lifecycle
  lock.
- [x] 2026-09-18 22:34 CST: Added transaction-boundary, lock ownership, and
  repeat-notification coverage; 44 focused and 181 order tests pass.
- [x] 2026-09-18 22:52 CST: Unified native webhook and sync finalization on
  the order lifecycle lock, moved provider I/O outside database transactions,
  and made lost-lock failures roll back before notices; 72 focused and 187
  order tests pass.

## Decision Log

- Decision: perform an ownership/channel preflight in a discarded unit of
  work, perform provider I/O outside a database transaction, then dispatch
  Stripe to its owner or reload and finalize native orders under the existing
  payment lifecycle lock.
  Rationale: provider-specific synchronization owns its transaction, while the
  reload prevents authorization or provider changes between preflight and use.
- Decision: enter the final unit of work before the native payment lifecycle
  lock so lock-exit ownership validation occurs before the transaction commits.
  Rationale: losing the Redis lease must roll back payment completion and drop
  post-commit notifications rather than report the loss after durable effects.

## Context and Orientation

`src/api/flaskr/route/order.py` exposes the common endpoint.
`src/api/flaskr/service/order/funs.py` owns generic, Stripe, and native
synchronization plus success side effects.

## Validation and Acceptance

- Common Stripe sync enters the dedicated function with no active outer UoW.
- Alipay and WeChat Pay provider I/O runs outside a database transaction, while
  sync and webhook finalization share the per-order payment lifecycle lock.
- Repeated successful synchronization does not repeat fulfillment or notices.
- Ownership and payment-channel validation are rerun inside the native lock.
- Losing the lifecycle lock before commit rolls back completion and suppresses
  post-commit notices.

## Interfaces and Dependencies

This is stacked on PR #2854 until that PR merges. No schema, response, or
deployment configuration changes.

## Surprises & Discoveries

Repeated provider confirmations can re-enter paid side effects; a final order state alone is not a sufficient idempotency boundary.

## Outcomes & Retrospective

Merged #2857 with recorded 72 focused and 187 order tests; synchronization preserves a single entitlement/credit outcome across repeats.

## Plan of Work

Use the existing paid-order boundary to make duplicate provider confirmations harmless, with repeated and concurrent synchronization regression coverage.

## Concrete Steps

Inspect the sync and paid-side-effect tests in `src/api/tests/service/order/` and `src/api/tests/service/billing/`; run their focused suites before changing payment transition logic.

## Idempotence and Recovery

Retain provider evidence and the existing idempotency keys on retry. Do not repair a failure by manually replaying entitlement or credit grants.

# Keep common payment synchronization idempotent

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

## Decision Log

- Decision: perform an ownership/channel preflight in a discarded unit of
  work, then dispatch Stripe outside that boundary and reload native orders
  under the existing payment lifecycle lock.
  Rationale: provider-specific synchronization owns its transaction, while the
  reload prevents authorization or provider changes between preflight and use.

## Context and Orientation

`src/api/flaskr/route/order.py` exposes the common endpoint.
`src/api/flaskr/service/order/funs.py` owns generic, Stripe, and native
synchronization plus success side effects.

## Validation and Acceptance

- Common Stripe sync enters the dedicated function with no active outer UoW.
- Alipay and WeChat Pay sync provider work and finalization run under the
  per-order payment lifecycle lock.
- Repeated successful synchronization does not repeat fulfillment or notices.
- Ownership and payment-channel validation are rerun inside the native lock.

## Interfaces and Dependencies

This is stacked on PR #2854 until that PR merges. No schema, response, or
deployment configuration changes.

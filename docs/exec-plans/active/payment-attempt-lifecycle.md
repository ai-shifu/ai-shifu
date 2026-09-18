# Make payment attempts safe across retries and coupon repricing

## Purpose / Big Picture

One business order may need more than one provider payment attempt when a
learner changes payment method, retries a recoverable failure, or applies a
coupon after the cashier opens. The system must invalidate obsolete attempts,
reuse only a compatible live attempt, and accept valid callbacks only for the
current amount without leaving a paid learner stuck in an unpaid state.

## Progress

- [x] 2026-09-18 12:00 CST: Split the unfinished payment-attempt work from the
  learner order authorization pull request and preserved it on a dedicated
  branch.
- [ ] 2026-09-18 12:05 CST: Fix latest-attempt selection and callback handling
  for multiple provider records and recoverable Stripe failures.
- [ ] 2026-09-18 12:05 CST: Match reusable attempts to the requested provider,
  channel, and payment mode.
- [ ] 2026-09-18 12:05 CST: Make coupon repricing close every obsolete live
  attempt and serialize concurrent coupon requests without stale snapshots.
- [ ] 2026-09-18 12:05 CST: Make provider cancellation and local recovery
  idempotent after timeouts, already-closed responses, and commit failures.
- [ ] 2026-09-18 12:05 CST: Add full HTTP, service, callback, and frontend
  regressions, then run the repository verification gates.

## Surprises & Discoveries

- SQLAlchemy `scalar()` raises `MultipleResultsFound` when the latest-attempt
  query orders rows but does not limit the result to one row.
- Stripe may reuse one PaymentIntent after a recoverable payment failure, so a
  local failed status is not equivalent to cancellation or expiration.
- Ping++ JSAPI credentials are mappings, while QR credentials are strings; a
  reusable-attempt check must validate the shape required by the requested
  payment mode rather than assuming every credential is a URL.
- MySQL repeatable-read snapshots can hide the first coupon request from a
  concurrent request when ordinary reads occur before acquiring the order lock.

## Decision Log

- Decision: keep one business order and model provider attempts as replaceable
  children of that order.
  Rationale: coupon repricing and payment-method switches should not create
  duplicate business orders, but obsolete provider credentials must stop being
  payable.
- Decision: reuse requires an exact provider, sub-channel, mode, amount, and
  live-state match.
  Rationale: a credential for QR, JSAPI, Stripe, Alipay, or another amount is
  not interchangeable.
- Decision: acquire the order row lock before coupon eligibility and usage
  reads that participate in the mutation decision.
  Rationale: this avoids establishing a stale MySQL repeatable-read snapshot
  before serialization.
- Decision: the historical Stripe manual-sync callback gate and Checkout
  Session ownership gap are follow-up security work, not part of this pull
  request.
  Rationale: frozen-base comparison shows those issues predate this lifecycle
  change; they will be handled only after the authorization and lifecycle pull
  requests are complete.

## Outcomes & Retrospective

Work is in progress. This section will record the final behavior, verification,
and remaining provider-environment limitations before the plan is completed.

## Context and Orientation

`src/api/flaskr/service/order/funs.py` creates, reuses, synchronizes, and
completes provider attempts. `coupon_funcs.py` applies discounts and coordinates
repricing. Provider-specific cancellation lives under
`payment_providers/`. Desktop and mobile checkout behavior lives under
`src/web/src/app/c/[[...id]]/Components/Pay/`.

## Plan of Work

Define one canonical latest-live-attempt lookup that returns at most one row and
matches the requested payment contract. Separate recoverable failure from
irreversible closure. During coupon repricing, lock first, re-read all mutation
inputs, close every obsolete live attempt, and make repeated cancellation
converge on the provider's actual terminal state. Apply the same current-attempt
and amount rules to asynchronous callbacks without rejecting a valid retry on a
recoverable Stripe PaymentIntent.

Keep the desktop QR-first interaction and mobile JSAPI flow unchanged from the
learner's perspective. Add regressions for all four providers, channel switches,
coupon concurrency on MySQL, cancellation recovery, and complete frontend/API
request sequences.

## Concrete Steps

1. Replace multi-row scalar lookups with deterministic one-row attempt queries.
2. Define reusable and completable states per provider and payment mode.
3. Resolve the requested provider and sub-channel before any reuse decision.
4. Lock the order before coupon-related reads and revalidate attempts under the
   same transaction.
5. Make provider cancellation idempotent and reconcile ambiguous outcomes.
6. Cover callbacks, retries, switches, coupon races, and cashier interactions.
7. Run focused suites, MySQL concurrency coverage, frontend checks, and all
   repository gates.

## Validation and Acceptance

- A discounted replacement attempt can complete the order through Ping++,
  Stripe, Alipay, and WeChat callbacks.
- A recoverable Stripe failure followed by success on the same PaymentIntent
  completes the order exactly once.
- Switching payment method or QR/JSAPI mode never returns credentials from the
  previous selection.
- Coupon repricing leaves no payable attempt at the old amount, including under
  concurrent payment creation.
- Two concurrent coupon requests cannot stack discounts on one order.
- Cancellation retries converge after timeouts, already-closed provider
  responses, and local transaction failures; reopening checkout never returns
  a closed credential.
- Existing desktop QR-first and mobile JSAPI behavior remain covered end to end.

## Idempotence and Recovery

Provider cancellation and callback handling must be safe to repeat. Unknown
remote outcomes are reconciled by querying or interpreting the provider's
already-terminal response before local state changes. Tests use isolated orders
and mocked provider boundaries; MySQL concurrency tests use separate sessions
and clean their fixtures after completion.

## Interfaces and Dependencies

The work changes internal attempt selection and provider cancellation contracts
in the order service. It depends on the learner ownership boundary from #2848
but does not change that public authorization contract. Real-provider smoke
tests still require valid Ping++, Stripe, Alipay, and WeChat test credentials.

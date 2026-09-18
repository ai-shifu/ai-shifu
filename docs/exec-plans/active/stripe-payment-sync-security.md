# Secure learner Stripe payment synchronization

## Purpose / Big Picture

Learner-triggered Stripe synchronization must never complete an order from a
Checkout Session or PaymentIntent that belongs to another order, an obsolete
attempt, or a different amount. Manual synchronization and verified webhooks
must use the same completion rules so one path cannot bypass the other.

## Progress

- [x] 2026-09-18 18:20 CST: Created an independent branch from the latest
  `main` and confirmed the historical manual-sync and ownership gaps remain.
- [x] 2026-09-18 18:46 CST: Added ownership, provider-object identity,
  amount, terminal-state, unpaid-session, and idempotent-sync regressions.
- [x] 2026-09-18 18:52 CST: Applied shared Stripe identity and completion
  guards before snapshot mutation and fulfillment.
- [x] 2026-09-18 19:04 CST: Passed focused and order-wide tests plus Ruff,
  compilation, architecture, UoW, and repository-harness checks.
- [x] 2026-09-18 20:02 CST: Corrected review findings for Stripe's real
  metadata shape, refundable PaymentIntent persistence, and delayed failure or
  cancellation events from superseded attempts.
- [x] 2026-09-18 20:18 CST: Serialized Stripe completion with repricing and
  added delayed Checkout success/failure handling for asynchronous payment
  methods.

## Surprises & Discoveries

- The learner sync endpoint accepts a caller-supplied Checkout Session ID and
  sends it to Stripe before proving it matches the locally stored attempt.
- Manual sync marks the Stripe snapshot successful before checking the current
  attempt, amount, or mutable order state enforced by the webhook path.
- Stripe Checkout can report `status=complete` while `payment_status=unpaid`;
  completion alone is therefore not proof that funds were paid.
- Legacy payment-mode Checkout Sessions carry ownership metadata on the
  PaymentIntent but not the Session itself. New Sessions now carry both, while
  synchronization retains compatibility with the existing provider shape.
- Alipay and WeChat Pay Checkout Sessions can complete before settlement;
  fulfillment must wait for `checkout.session.async_payment_succeeded`, while
  the corresponding failure event may only update its matching current Session.

## Decision Log

- Decision: require a caller-supplied Session ID to exactly match the current
  local Stripe attempt before contacting Stripe.
  Rationale: the browser does not own the mapping between provider objects and
  business orders.
- Decision: share one completion predicate between webhook and manual sync.
  Rationale: duplicated security rules already drifted and allowed manual sync
  to bypass webhook protections.
- Decision: reject mismatched provider identity before mutating raw snapshots.
  Rationale: untrusted provider-object identifiers must not overwrite the
  locally established attempt relationship.
- Decision: preserve idempotent synchronization for the already-successful
  current attempt, while rejecting successful provider data for terminal or
  superseded orders.
  Rationale: browser retries must be safe without reopening fulfillment.

## Context and Orientation

`src/api/flaskr/route/order.py` exposes the authenticated learner sync route.
`src/api/flaskr/service/order/funs.py` owns both manual sync and Stripe webhook
application. `payment_providers/stripe.py` retrieves provider objects and
normalizes their metadata.

## Plan of Work

Add regressions for a foreign caller-supplied Session ID, mismatched Stripe
metadata, mismatched provider object IDs and amounts, superseded attempts, and
terminal orders. Extract narrow helpers that validate remote identity and the
shared local completion gate. Apply them before snapshot mutation in manual
sync and before fulfillment in webhook handling.

## Validation and Acceptance

- Only the current local Stripe attempt can complete its own business order.
- Session, PaymentIntent, metadata order, and available provider amount fields
  agree with the stored attempt and order.
- Manual sync and webhook accept and reject the same local lifecycle states.
- Rejected synchronization does not mutate the order or Stripe snapshot.
- Existing successful and idempotent Stripe flows continue to pass.

## Idempotence and Recovery

Repeated synchronization of the same valid paid attempt remains safe. Invalid
or stale input fails before fulfillment and can be retried with the current
locally stored provider reference.

## Interfaces and Dependencies

No schema or public response change is planned. The internal Stripe completion
guard will be shared by learner sync and webhook application.

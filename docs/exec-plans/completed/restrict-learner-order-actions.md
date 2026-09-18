# Restrict learner order actions to their owner

## Purpose / Big Picture

Learner-facing order endpoints must treat the authenticated user and order as a
single authorization boundary. A learner must not be able to inspect, discount,
or start payment for another learner's order, and payment status responses must
contain only fields required by the learner UI. Coupon application must also
leave completed, refunded, and expired orders immutable.

## Progress

- [x] 2026-09-18 09:00 CST: Created the branch from the latest `main` and
  inspected learner order routes, service functions, and frontend consumers.
- [x] 2026-09-18 10:05 CST: Added service-level owner and mutable-state checks.
- [x] 2026-09-18 10:20 CST: Passed the authenticated user through learner routes
  and minimized learner payment detail responses.
- [x] 2026-09-18 10:45 CST: Added HTTP and service regressions for cross-user and
  terminal-order attempts, plus response allowlisting.
- [x] 2026-09-18 11:15 CST: Ran focused backend/frontend and repository
  verification, then moved this plan to `docs/exec-plans/completed/`.

## Surprises & Discoveries

- Existing Stripe and native payment sync services already accept
  `expected_user` and hide cross-user orders as `orderNotFound`; the adjacent
  query, charge, detail, and coupon paths do not yet follow that contract.
- The Stripe result page only reads `payment_channel`, `status`, and
  `course_id` from payment detail. Provider objects, metadata, receipt URLs,
  payment identifiers, and raw payloads are not required by the learner UI.
- The latest `main` added `pydantic-ai-slim==2.43.0`; the local Python 3.11
  test environment lacked it, so order tests initially failed during
  collection until the pinned dependency was installed.

## Decision Log

- Decision: enforce ownership in service functions, not only in routes.
  Rationale: internal or future callers must not be able to bypass the learner
  authorization boundary.
- Decision: return `orderNotFound` for an ownership mismatch.
  Rationale: this matches existing sync behavior and does not disclose whether
  another learner's order identifier exists.
- Decision: keep operator/admin payment detail loading separate and unchanged.
  Rationale: operator troubleshooting has a different authorization boundary;
  this work only minimizes learner-facing responses.
- Decision: allow coupon application only while an order is in an unpaid,
  mutable state before any provider attempt exists (`init`).
  Rationale: a `to be paid` order already has a live provider attempt at the
  old amount; repricing it would leave that charge usable. Both coupon
  redemption and payment creation lock the order row so they cannot race while
  claiming the initial state.
- Decision: create a provider payment attempt only for an `init` order and
  return the stored provider parameters for a `to be paid` order; retain the
  existing read-only handling for successful orders and explicit rejection for
  refunded orders.
  Rationale: mobile confirmation and reopening an unpaid order need the active
  payment parameters, but a retry must not create another provider charge.
- Decision: initialize the order when the payment modal opens, but defer
  provider payment creation until the learner explicitly starts payment.
  Rationale: this keeps the order in `init` while the learner enters a coupon,
  so an active provider payment is never repriced.

## Outcomes & Retrospective

Learner order lookup, payment creation, payment detail, and coupon redemption
now enforce the authenticated order owner in the service layer. Coupon
redemption accepts only initial orders before a provider attempt exists, and
payment creation and coupon redemption serialize on the order row. The desktop
and mobile payment surfaces defer provider creation until payment starts, and
pending orders reuse their stored provider parameters instead of creating a
duplicate attempt. Learner payment detail responses for Stripe, native
providers, and Ping++ contain only payment channel, course, order, and provider
status; operator detail loading still uses full snapshots.

Regression coverage exercises all four HTTP entry points, direct service calls,
payment-attempt and terminal-order immutability, and provider response
allowlists. Focused order tests, legacy root order tests, frontend payment tests,
TypeScript, Ruff, formatting, architecture boundaries, and unit-of-work checks
pass. The final repository-wide pre-commit gate is run after this completed plan
is written.

## Context and Orientation

`src/api/flaskr/route/order.py` exposes learner order endpoints.
`src/api/flaskr/service/order/funs.py` owns order lookup, payment creation, and
learner payment details. `src/api/flaskr/service/order/coupon_funcs.py` owns
coupon redemption. Provider snapshots remain available to operator code in
`src/api/flaskr/service/order/admin.py`. Frontend response types live in
`src/web/src/api/order.ts`; the Stripe result page is the only direct learner
consumer of payment details.

## Plan of Work

Add an optional expected-user boundary to the shared learner service functions
and require it from HTTP routes. Coupon redemption will load only the current
user's order and reject states other than unpaid mutable states before touching
coupon records. Replace learner payment detail payloads with a stable allowlist
containing the provider name, course ID, order ID, and provider status needed by
the result UI. Preserve full provider snapshots for operator-only code.

Add regressions proving that query, payment creation, payment detail, and coupon
application return `orderNotFound` for another learner; terminal orders reject
coupon application without changing prices or coupon usage; and each provider's
learner detail response excludes raw or sensitive fields.

## Concrete Steps

1. Update order service signatures and all in-repository call sites.
2. Add owner and mutable-state predicates before any mutation or provider call.
3. Define and return the minimal learner payment detail contract.
4. Align frontend TypeScript types with that contract.
5. Add focused route/service tests, then run order and relevant frontend tests.
6. Run development-tool, architecture, unit-of-work, formatting, and
   pre-commit gates.

## Validation and Acceptance

- Another user's order ID produces the same not-found response for query,
  payment creation, payment detail, and coupon application.
- Paid, refunded, and timed-out orders cannot receive a coupon and remain
  byte-for-byte equivalent in price/status/coupon association after rejection.
- The owner can still query an order, start payment, apply a coupon to an unpaid
  order, and obtain the status fields used by the learner UI.
- Learner payment detail contains no provider raw request, raw response,
  notification, metadata, provider object, receipt URL, client secret, or full
  third-party payload.
- Focused order tests, frontend payment tests, Ruff, formatting, architecture
  boundaries, unit-of-work checks, and full pre-commit pass.

## Idempotence and Recovery

The change adds validation before existing mutations and does not migrate data.
Tests use isolated records and can be rerun. If a provider-specific regression
appears, revert the minimal response mapping without changing stored payment
snapshots; admin reads remain independent.

## Interfaces and Dependencies

The affected Python interfaces are `generate_charge`, `query_buy_record`,
`get_payment_details`, and `use_coupon_code`, plus their learner route call
sites. Internal webhook and sync calls must pass or deliberately omit the owner
boundary according to whether they are authenticated learner flows or trusted
provider flows. The frontend `PaymentDetailResponse` contract will be narrowed
to the stable learner-visible fields.

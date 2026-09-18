# Recover legacy Stripe billing timeouts

## Purpose / Big Picture

The billing timeout worker must be able to close an unpaid historical Stripe
Checkout Session that predates Session-level ownership metadata. The
compatibility path must never be usable to accept payment or grant credits.

## Progress

- [x] 2026-09-18 21:32 CST: Reproduced the production validation path from the
  timeout worker through billing synchronization.
- [x] 2026-09-18 21:38 CST: Added the narrow expired-session compatibility
  rule plus paid, mismatched-ID, and foreign-metadata rejection regressions.
- [x] 2026-09-18 21:42 CST: Passed focused billing Checkout and timeout-task
  verification plus repository structural checks.

## Surprises & Discoveries

- Historical payment-mode Checkout Sessions can have no Session metadata and
  no PaymentIntent when the learner never paid, leaving no provider metadata
  for the timeout worker to validate.

## Decision Log

- Decision: accept missing metadata only when the returned Session ID already
  matches the locally stored reference, Stripe marks the Session expired, and
  neither the Session nor its PaymentIntent contains paid evidence.
  Rationale: this closes an unpaid historical order without weakening any path
  that confirms payment or grants an entitlement.

## Context and Orientation

`src/api/flaskr/service/billing/tasks.py` scans expired pending orders.
`src/api/flaskr/service/billing/checkout.py` synchronizes the provider state and
validates Checkout evidence before moving the order to a terminal state.

## Validation and Acceptance

- A matching, unpaid, expired historical Session without metadata becomes a
  timed-out billing order.
- A paid Session without metadata remains rejected.
- A mismatched Session ID or explicit foreign metadata remains rejected.
- No credits, subscription activation, or paid transition occurs through the
  compatibility path.

## Interfaces and Dependencies

No schema, API response, provider configuration, or deployment setting changes.

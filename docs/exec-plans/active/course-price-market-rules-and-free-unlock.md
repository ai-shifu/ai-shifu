# Market-aware course prices and free-course unlock

## Purpose / Big Picture

Course prices must reflect the payment capabilities of each deployment. China
supports free courses and paid prices from CNY 0.01; global supports free
courses and Stripe-paid prices from USD 0.50. A zero-price paywall creates a
successful zero-value order and unlocks learning without invoking a payment
provider.

## Progress

- [x] 2026-09-09 17:05 CST: Confirmed product rules and inspected authoring,
  order initialization, provider dispatch, and learner payment state.
- [x] 2026-09-09 17:25 CST: Implement backend pricing contract and atomic free
  order completion with regression coverage.
- [ ] 2026-09-09 17:05 CST: Implement frontend configuration-driven authoring
  validation and server-authoritative free unlock with regression coverage.
- [ ] 2026-09-09 17:05 CST: Verify, self-review, publish two focused PRs, and
  document their stacking/merge order.

## Surprises & Discoveries

- `DraftShifu.price` and `PublishedShifu.price` already use `DECIMAL(10, 2)`,
  so CNY 0.01 needs no schema migration.
- `generate_charge()` already short-circuits zero amounts before provider
  invocation, but the learner hook currently treats `value_to_pay <= 0` as
  success without making the server transition the order from INIT to SUCCESS.
- Draft creation uses Python truthiness (`price or minimum`), which replaces an
  explicit zero with the configured minimum.

## Decision Log

- Decision: Both markets allow exactly zero. China additionally allows any
  two-decimal price from 0.01; global permits a positive price only from 0.50.
  Reason: zero bypasses payment providers, while positive prices must respect
  the active provider's minimum.
- Decision: Preserve a successful zero-value order rather than inventing a
  separate free entitlement. Reason: existing access checks, audit history,
  and analytics already use successful orders.
- Decision: The server owns price policy and returns it to Cook Web; the web
  app must not infer market rules from hostnames.
- Decision: Initializing a zero-value order completes it atomically. Reason:
  the client must never declare payment success from amount alone.

## Outcomes & Retrospective

Pending implementation and verification.

## Context and Orientation

Course authoring price validation is in
`src/api/flaskr/service/shifu/shifu_draft_funcs.py` and
`src/web/src/components/shifu-setting/ShifuSetting.tsx`. Runtime environment
data flows through the backend runtime-config DTO into `src/web/src/store/envStore.ts`.
Legacy course orders are initialized and charged in
`src/api/flaskr/service/order/funs.py`; learner payment orchestration lives in
`src/web/src/app/c/[[...id]]/Components/Pay/hooks/usePaymentFlow.ts`.

## Plan of Work

First expose one backend course-price policy derived from deployment config,
use Decimal-safe validation for draft create/update, preserve explicit zero,
and complete zero-value orders during initialization. Then consume the policy
in Cook Web, remove the hard-coded 0.5, and require a server SUCCESS state for
free unlock. Keep the backend and frontend commits in separate stacked PRs.

## Concrete Steps

1. Add configuration for default course price and positive minimum, with a
   policy serializer in the existing runtime configuration path.
2. Centralize backend course-price normalization and apply it to draft create
   and update.
3. Mark zero-value course orders successful in `init_buy_record()` within its
   unit of work and return the committed state.
4. Extend backend tests for zero, China 0.01, global 0.01 rejection/global 0.50,
   and proof that no provider is invoked for zero.
5. Extend Cook Web environment state and replace authoring constants with the
   server policy.
6. Make learner payment completion depend on order SUCCESS, with focused tests
   for zero-value initialization.

## Validation and Acceptance

- China: a new course defaults to 0; 0, 0.01, and larger two-decimal values save.
- Global: a new course defaults to 0.50; 0 and values at least 0.50 save; a
  positive value below 0.50 is rejected by both API and UI.
- Reaching a paywall on a zero-price course creates one successful zero-value
  order, invokes no provider, and resumes learning on desktop and mobile.
- A positive China order of 0.01 remains payable; a positive global order of
  0.50 reaches Stripe normally.
- Existing positive course prices remain unchanged.

## Idempotence and Recovery

Order initialization already serializes one active order per user/course and
is retryable. Repeating free initialization must return the same successful
order. Configuration defaults remain backward compatible until deployment
values are explicitly split. No migration or destructive data operation is
required.

## Interfaces and Dependencies

The backend runtime configuration gains course-price policy fields consumed by
Cook Web. The frontend PR therefore depends on the backend PR. Payment provider
interfaces do not change; zero-value orders stop before provider dispatch.

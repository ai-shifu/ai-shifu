# Backend Service: promo

This module owns promotion campaigns, coupon and redemption models, and promo
application or rollback logic tied to order lifecycles.

Entry files in this directory: `funcs.py`, `models.py`, `consts.py`.

## Do

- Keep promo application, rollback, and redemption behavior idempotent with
  respect to order retries and timeout recovery.
- Preserve centralized discount calculation inside promo helpers so coupon
  math does not drift across callers.
- Treat campaign and redemption rows as audit records that should stay
  coherent when business rules evolve.

## Avoid

- Do not split promo rollback logic between order code and promo code in ways
  that make eventual state ambiguous.
- Do not duplicate discount calculations or eligibility filters in frontend
  code or neighboring services.
- Do not change redemption semantics without reviewing order and coupon
  interactions together.

## Tests

`cd src/api && pytest tests/service/promo/ -q`

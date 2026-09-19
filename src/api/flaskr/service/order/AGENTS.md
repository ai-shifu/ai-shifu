# Backend Service: order

This module owns orders, payment-provider integration, coupon handling, admin
order surfaces, and related payment workflows.

Entry files in this directory: `funs.py`, `models.py`, `coupon_funcs.py`,
`admin.py`, `payment_providers/base.py`.

## Do

- Keep payment-provider differences behind the provider abstraction layer
  instead of branching through every order flow.
- Preserve idempotent order, coupon, and payment-notification handling because
  retries are normal in payment systems.
- When legacy provider raw tables are shared with billing snapshots, keep
  legacy `/order` reads and writes scoped to `biz_domain='order'`.
- Treat admin DTOs and public order payloads as compatibility surfaces used
  outside this module.

## Avoid

- Do not wire new payment gateways directly into routes or business helpers
  without extending the provider abstraction.
- Do not split discount, coupon, and order-state transitions across multiple
  places where rollback behavior becomes unclear.
- Do not change payment callback handling without explicit tests for duplicate
  or out-of-order notifications.

## Tests

`cd src/api && pytest tests/service/order/ -q`

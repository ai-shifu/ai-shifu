# Remove Ping++

## Purpose / Big Picture

China production moved learner course orders and creator billing orders from
Ping++ to the native Alipay and WeChat Pay providers on 2026-11-25 12:39 CST
(deploy-config #73, code in #3431). This plan removes Ping++ as a payment
provider from the codebase so new payments can only use Alipay, WeChat Pay or
Stripe, while historical Ping++ orders stay readable for operators and
learners.

## Progress

- [x] 2026-11-25 12:20 CST: Inventoried Ping++ references (21 backend
      modules, 31 web files, 58 test files, i18n, `pingpp` dependency, docs).
- [x] 2026-11-25 13:05 CST: Backend: removed the provider, `pingpp`, the
      callback route, the order and billing Ping++ branches, the creator Ping++
      integration and `PINGXX_*`; kept historical reads (528c297f5).
- [x] 2026-11-25 13:40 CST: Web: removed the `pingxx` payment channel and the
      Ping++ fallback in the learner cashier; renamed the billing QR dialog,
      polling hook and channel type to provider-neutral names; kept the
      historical provider label and operator filters.
- [x] 2026-11-25 13:45 CST: i18n (dropped the Ping++ integration labels and the
      unused provider-with-channel label), regenerated env example and i18n
      keys, updated design docs and the billing AGENTS guide.
- [x] 2026-11-25 13:00 CST: Guard: `test_pingxx_retirement_guard.py` forbids
      `pingpp` and confines `pingxx` to the listed history readers.
- [x] 2026-11-25 13:50 CST: Validation: backend 16329 passed (3 LLM contract
      tests fail locally on main as well); web 3930 passed under `TZ=UTC`
      (two promotion date tests depend on the local time zone); `tsc` and
      ESLint clean.
- [ ] Before merge: read-only settlement check that every paid Ping++ charge
      (`order_pingxx_orders.status = 1`, course and billing domains) maps to a
      paid local order, and that no Ping++ charge is still within its provider
      expiry (after 14:13 CST 2026-11-25); cross-check the Ping++ dashboard.
- [ ] SIM acceptance by the owner: 0.1 CNY WeChat Native and Alipay QR
      purchases complete, and an operator can still open a historical Ping++
      order. Merge and release only after this and the settlement check.
- [ ] Follow-up in deploy-config: remove `PINGXX_*` env, ConfigMap key,
      Secret material and `pingxx_key.gem`; disable the Ping++ app.
- [ ] Follow-up migration: drop the `order_orders.payment_channel` server
      default `'pingxx'` (needs a manual CN `flask db upgrade`).

## Surprises & Discoveries

- Production Ping++ volume was low: 133 orders in the 30 days before the
  switch, 11 paid. The last Ping++ charge (WeChat QR, 2 h provider expiry) was
  created 2026-11-25 12:13 CST and expires 14:13 CST; no Alipay Ping++ code
  (24 h expiry) was created in the 24 hours before the switch.
- No creator had a custom payment integration
  (`CUSTOMIZATION.INTEGRATION.*.ACTIVE`: 0 rows), so the Ping++ integration
  can be removed without migrating tenants.
- `Order.payment_channel` had the ORM default `"pingxx"`, and migration
  `c9c92880fc67` also set the column's server default to `'pingxx'`. ORM
  inserts always send a value (now `""`), so the server default only affects
  raw SQL inserts; dropping it is a follow-up migration rather than part of
  this code change.

## Decision Log

- Keep `order_pingxx_orders`, `PingxxOrder` and `legacy_pingxx_snapshot_query`
  for read-only history (admin order detail, learner payment detail). No data
  migration or table drop.
- No Ping++ grace path in code: production stopped creating Ping++ charges at
  12:39 CST and this change ships after the last charge expired.
- Billing orders and subscriptions whose provider is `pingxx` stay readable;
  renewal and checkout no longer create or reconcile Ping++ attempts.
- `PAYMENT_CHANNELS_ENABLED` defaults to `alipay,wechatpay,stripe`; when unset,
  providers without credentials are dropped, as the old `pingxx,stripe`
  default did.

## Outcomes & Retrospective

To be written after SIM acceptance and release.

## Context and Orientation

- Provider layer: `src/api/flaskr/service/order/payment_providers/`.
- Channel selection: `src/api/flaskr/service/order/payment_channel_resolution.py`.
- Learner orders: `src/api/flaskr/service/order/funs.py`, callbacks in
  `src/api/flaskr/route/callback.py`.
- Creator billing: `src/api/flaskr/service/billing/` (`checkout.py`,
  `webhooks.py`, `renewal.py`, `customization.py`).
- Design: `docs/design-docs/native-cn-payments.md`.

## Plan of Work

Remove write paths first (provider, creation, callbacks, reconciliation),
then configuration and integration surfaces, then the web client, keeping
every read of historical Ping++ rows behind the legacy snapshot query.

## Concrete Steps

1. Delete `payment_providers/pingxx.py`, its registration and `pingpp`.
2. Rewrite channel resolution without a Ping++ fallback.
3. Remove Ping++ branches from learner order creation, resume, repricing,
   refund and callbacks; keep `get_payment_details` read-only for history.
4. Remove Ping++ from billing checkout, webhooks, renewal, policy, campaigns,
   notifications, debug CLI and creator customization.
5. Remove `PINGXX_*` from `common/config.py`; regenerate env examples.
6. Web client, i18n keys, docs.
7. Add the architecture guard and run the validation gates.

## Validation and Acceptance

- `pytest tests/service/order tests/service/billing tests/common tests/route`
  and the full backend suite pass; web unit tests and `tsc` pass.
- No module imports `pingpp`; `pingxx` appears only in the allowlisted
  history readers.
- On SIM, a 0.1 CNY WeChat Native and an Alipay QR purchase complete, and an
  admin can still open a historical Ping++ order.

## Idempotence and Recovery

Code-only removal; no schema change. Rolling back the release restores Ping++
code, but production config already disables it, so rollback needs
`PAYMENT_CHANNELS_ENABLED` to include `pingxx` again plus the retained
`PINGXX_*` settings (kept until the deploy-config follow-up).

## Interfaces and Dependencies

- Removes the `pingpp` Python dependency and `POST /api/callback/pingxx-callback`.
- `resolve_payment_channel(default_pingxx_channel=...)` becomes
  `default_channel=...`.
- Web `PaymentChannel` no longer includes `pingxx` for new payments.

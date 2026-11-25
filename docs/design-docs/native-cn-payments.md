---
title: Native China Payments
status: implemented
owner_surface: backend
last_reviewed: 2026-11-25
canonical: true
---

# Native China Payments

## Scope

This design adds direct merchant integrations for Alipay and WeChat Pay. They replaced Ping++ in China production on 2026-11-25, and Ping++ was then removed from the codebase (see Ping++ Retirement below). Stripe stays available through the same configuration gate.

The first release covers two business flows:

- Learner course purchases through `/api/order/*`.
- Creator billing checkout through `/api/billing/*`.

The first payment surfaces are Alipay QR, WeChat Native QR, and WeChat JSAPI. WeChat H5, Alipay WAP, and native refunds are explicitly out of scope for this release.

## Provider Selection

`PAYMENT_CHANNELS_ENABLED` accepts `alipay`, `wechatpay` and `stripe`, in the order the client should offer them. Unknown names, including the retired `pingxx`, are ignored. When it is empty, every provider whose complete credentials are configured is enabled: Alipay needs the app ID, app private key and Alipay public key; WeChat Pay needs the app ID, merchant ID, merchant serial number, APIv3 key, private key, and either a platform certificate or a WeChat Pay public key together with `WECHATPAY_PUBLIC_KEY_ID`; Stripe needs its secret key (keys may be inline or a file path). A stored credential that cannot be decrypted counts as missing, so it never breaks `/api/runtime-config`. Without a provider hint, an unknown channel such as the retired `wx_wap` is rejected rather than routed to the default provider. Billing discount campaigns use the same effective list to decide whether Stripe coupons must be published first.

Channel resolution:

- `alipay_qr` uses `alipay`.
- `wx_pub_qr` and `wx_pub` use `wechatpay`.
- `stripe:*` stays on Stripe.
- A disabled provider and unsupported provider/channel combinations fail with `server.pay.payChannelNotSupport`; there is no fallback provider.

The resolver also accepts additional providers scoped to the course owner. Free orders are attributed to the market provider (Stripe, then Alipay, then WeChat Pay), or to an empty channel when no provider is enabled. See `payment_channel_resolution.py` under the order service.

## Backend Integration

The shared provider layer under `src/api/flaskr/service/order/payment_providers/` now includes:

- `AlipayProvider`: uses the official `alipay-sdk-python==3.7.1098` package for `alipay.trade.precreate`, notification signature verification, and trade query.
- `WechatPayProvider`: uses `requests` and `cryptography` for API v3 request signing, Native order creation, JSAPI parameter signing, notification signature verification, AES-256-GCM resource decryption, and order query.

Native providers implement `create_subscription` by delegating to one-time payment creation. Local billing subscription activation happens only after a paid order is confirmed.

Payment codes expire with the order. Without this, the default WeChat and Alipay windows outlive the order: a learner could pay an order that has already timed out locally, and the notification would not grant the course. Course orders pass `created_at + PAY_ORDER_EXPIRE_TIME` and billing orders pass their `expires_at` as `PaymentRequest.extra["expires_at"]`. WeChat Pay sends it unchanged as `time_expire` (China time). Alipay converts the remaining time to `timeout_express`, rounded down to whole minutes. WeChat moves any `time_expire` earlier than one minute after it receives the request to that point, so an order with less than two minutes left (one minute plus a margin for signing and the 10 s HTTP timeout) is rejected with `server.order.orderPayExpired` before any provider call instead of getting a code that outlives it.

Closing an Alipay attempt that was never scanned returns `ACQ.TRADE_NOT_EXIST`, because a precreate QR code only becomes a trade once scanned. `cancel_payment` treats that as closed, so learners can switch from Alipay to WeChat Pay before paying. Verified on sim (2026-11-25): after such a close, scanning the old Alipay code shows the trade as closed and it cannot be paid.

Native refunds are intentionally unsupported in this release. `refund_payment` raises an unsupported-provider error path and billing returns `unsupported`.

## Raw Snapshots

Native provider data is stored in independent provider tables:

- `order_alipay_orders`
- `order_wechatpay_orders`

Each table stores:

- `biz_domain`: `order` or `billing`.
- Business order identifiers: `order_bid` and `bill_order_bid`.
- Provider identifiers: `provider_attempt_id` and `transaction_id`.
- Payment shape: `channel`, `amount`, `currency`, `status`, and `raw_status`.
- Raw data: `raw_request`, `raw_response`, `raw_notification`, and `metadata_json`.

Alipay snapshots use `alipay_order_bid`; WeChat Pay snapshots use
`wechatpay_order_bid`. Native provider data is not written into
`order_pingxx_orders`, `order_stripe_orders`, or a shared native payment table.

## Callback Flow

New callbacks:

- `POST /api/callback/alipay-notify`
- `POST /api/callback/wechatpay-notify`

The callback handlers in `src/api/flaskr/route/callback.py` verify and normalize
the provider payload through the shared adapter. Each tries billing first and
then the legacy learner order flow if billing did not match. A verified
notification with no local match is acknowledged and logged. Validation or
processing errors return the provider-specific failure response.

Both flows are idempotent:

- A paid order is only granted once.
- Duplicate notifications update the raw snapshot but do not duplicate wallet grants or course purchase effects.
- Amount mismatch raises an error and the callback returns provider-specific failure output.

For learner course orders, any paid attempt of the order completes it, not only the latest one: a learner may pay a code shown before switching payment method, and that code is still valid because codes expire with the order. A pending or repricing order is completed directly. An order already flipped to timeout (the learner reopened checkout after the deadline) is completed only when the provider's payment time (`success_time` for WeChat Pay, `gmt_payment`/`send_pay_date` for Alipay) is no later than the order deadline. When a course order is paid, everything else the learner could still pay for that course is retired in the same transaction: other open orders of the same learner and course are timed out (coupons and campaigns released as on a normal timeout), and after commit the still-pending native attempts of the paid order and of those orders are closed at the provider. Closing is best effort and never undoes the purchase.

The webhook and payment sync apply the same rules to a paid attempt (`_apply_paid_native_attempt`):

- If this order, or another order of the same learner and course, is already paid, the course is not granted again; the payment is logged as `duplicate native payment needs a manual refund` and a `重复支付告警` Feishu alert is sent. This also covers a sibling retired by the purchase whose own code was paid in time.
- Otherwise the course is granted when the provider amount matches the attempt, the attempt matches the order's current price, and the order may still complete (pending, repricing, or timed out with a payment time no later than the deadline).
- Any other paid attempt (price changed, paid after the deadline) is logged as `paid native attempt not applied` and sends a `支付未入账告警` alert for a manual grant or refund.

Sibling retirement locks other open orders with `SKIP LOCKED` in `id` order, so two concurrent payment flows for the same course never wait on each other; a sibling skipped that way is caught by the duplicate check if it is paid too. An Alipay close whose request failed in transport is only accepted when the trade query reports `TRADE_CLOSED`; `ACQ.TRADE_NOT_EXIST` alone does not prove the close reached Alipay.

## Frontend Behavior

Learner checkout:

- If `wechatpay` is enabled and the learner is inside WeChat, the WeChat option requests `wx_pub` and invokes `WeixinJSBridge`.
- Outside WeChat, WeChat uses QR when enabled.
- Alipay uses QR.
- Stripe remains available when configured.

Billing checkout:

- `stripe` opens Stripe Checkout.
- `alipay` and `wechatpay` use the QR dialog (`BillingNativeQrDialog`) and sync polling (`useBillingQrPolling`).
- Each native provider issues one kind of code, so the dialog shows no channel switch. The provider is fixed before checkout: Alipay when it is enabled, otherwise WeChat Pay; a subscription keeps its own native provider, and a historical Ping++ subscription uses Alipay or WeChat Pay the same way (never Stripe).

## Configuration

New backend configuration keys:

- `HOST_URL`
- `ALIPAY_APP_ID`
- `ALIPAY_APP_PRIVATE_KEY_PATH`
- `ALIPAY_PUBLIC_KEY_PATH`
- `ALIPAY_GATEWAY_URL`
- `WECHATPAY_APP_ID`
- `WECHATPAY_MCH_ID`
- `WECHATPAY_API_V3_KEY`
- `WECHATPAY_MERCHANT_SERIAL_NO`
- `WECHATPAY_PRIVATE_KEY_PATH`
- `WECHATPAY_PLATFORM_CERT_PATH`
- `WECHATPAY_PUBLIC_KEY_ID`
- `WECHATPAY_PUBLIC_KEY_PATH`

Every key, certificate, and public key also accepts an inline value without
the `_PATH` suffix (for example `WECHATPAY_PUBLIC_KEY`). Inline values win over
paths. Only WeChat Pay inline PEM values accept escaped `\n` newlines;
Alipay inline keys are passed to the SDK unchanged, so use the single-line key
content there.

`WECHATPAY_APP_ID` falls back to `WECHAT_APP_ID` when empty.

### WeChat Pay notification verification

WeChat Pay signs notifications either with the merchant's WeChat Pay public
key or with a platform certificate. The `Wechatpay-Serial` header selects the
key:

- A serial starting with `PUB_KEY_ID_` must equal `WECHATPAY_PUBLIC_KEY_ID`
  and is verified with the configured WeChat Pay public key.
- Any other serial must match the configured platform certificate's serial
  number (case-insensitive, leading zeros ignored).

Notifications without the serial header, with an unknown serial, or with a
`Wechatpay-Timestamp` more than five minutes from server time are rejected
before the resource is decrypted. Merchants may configure both keys during a
migration from platform certificates to the public key.
`HOST_URL` is required outside local/test environments. Alipay and WeChat Pay
notification URLs are derived from `HOST_URL` and `PATH_PREFIX` as
`/api/callback/alipay-notify` and `/api/callback/wechatpay-notify` by default.
Stripe webhooks still must be registered in Stripe Dashboard as
`https://your-domain.com/api/order/stripe/webhook`.

## Ping++ Retirement

China production switched `PAYMENT_CHANNELS_ENABLED` from `pingxx` to `alipay,wechatpay` on 2026-11-25 12:39 CST. The last Ping++ charge expired at 14:13 CST the same day, and Ping++ was then removed (`docs/exec-plans/active/remove-pingxx.md`):

- No Ping++ provider, `pingpp` dependency, `PINGXX_*` setting or `/api/callback/pingxx-callback` route remains, and creators can no longer configure a Ping++ integration.
- `order_pingxx_orders`, `PingxxOrder` and `legacy_pingxx_snapshot_query` stay for read-only history: learner payment detail and operator order views and filters.
- Ping++ subscriptions count as manual-payment subscriptions, so they renew, preorder and upgrade with Alipay or WeChat Pay.
- A pending Ping++ billing order is never reopened (`server.order.orderPayExpired`); sync keeps it pending without calling Ping++ so the timeout scan expires it.
- `tests/service/order/test_pingxx_retirement_guard.py` forbids `pingpp` and limits `pingxx` mentions to the history readers it lists.

## Verification Focus

The primary checks are:

- Channel resolution without a fallback provider.
- Provider payload construction and notification normalization.
- Legacy learner order idempotency and amount mismatch rejection.
- Billing checkout, sync, webhook paid state transition, and duplicate grant protection.
- Frontend provider selection, WeChat JSAPI invocation, QR rendering, and polling close behavior.

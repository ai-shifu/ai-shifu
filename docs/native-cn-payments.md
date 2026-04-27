# Native China Payments

## Scope

This design adds direct merchant integrations for Alipay and WeChat Pay while keeping Ping++ and Stripe available through the existing configuration gate.

The first release covers two business flows:

- Learner course purchases through `/api/order/*`.
- Creator billing checkout through `/api/billing/*`.

The first payment surfaces are Alipay QR, WeChat Native QR, and WeChat JSAPI. WeChat H5, Alipay WAP, and native refunds are explicitly out of scope for this release.

## Provider Selection

`PAYMENT_CHANNELS_ENABLED` accepts `wechatpay,alipay,pingxx,stripe`.

Channel resolution is intentionally conservative:

- `alipay_qr` prefers `alipay` when enabled, then falls back to `pingxx`.
- `wx_pub_qr` and `wx_pub` prefer `wechatpay` when enabled, then fall back to `pingxx`.
- `stripe:*` stays on Stripe.
- Unsupported provider/channel combinations fail with `server.pay.payChannelNotSupport`.

Default behavior does not change for existing deployments because the default remains `pingxx,stripe`.

## Backend Integration

The shared provider layer under `src/api/flaskr/service/order/payment_providers/` now includes:

- `AlipayProvider`: uses the official `alipay-sdk-python==3.7.1098` package for `alipay.trade.precreate`, notification signature verification, and trade query.
- `WechatPayProvider`: uses `requests` and `cryptography` for API v3 request signing, Native order creation, JSAPI parameter signing, notification signature verification, AES-256-GCM resource decryption, and order query.

Native providers implement `create_subscription` by delegating to one-time payment creation. This matches the current Ping++ billing behavior: local billing subscription activation happens only after a paid order is confirmed.

Native refunds are intentionally unsupported in this release. `refund_payment` raises an unsupported-provider error path and billing returns `unsupported`.

## Raw Snapshots

Native provider data is stored in `order_native_payment_orders`.

The table stores:

- `biz_domain`: `order` or `billing`.
- Business order identifiers: `order_bid` and `bill_order_bid`.
- Provider identifiers: `payment_provider`, `provider_attempt_id`, and `transaction_id`.
- Payment shape: `channel`, `amount`, `currency`, `status`, and `raw_status`.
- Raw data: `raw_request`, `raw_response`, `raw_notification`, and `metadata_json`.

Native provider data is not written into `order_pingxx_orders` or `order_stripe_orders`.

## Callback Flow

New callbacks:

- `POST /api/callback/alipay-notify`
- `POST /api/callback/wechatpay-notify`

Each callback verifies and normalizes the provider payload through the shared provider adapter. The route then tries billing first. If no billing order is matched, it falls back to the legacy learner order flow.

Both flows are idempotent:

- A paid order is only granted once.
- Duplicate notifications update the raw snapshot but do not duplicate wallet grants or course purchase effects.
- Amount mismatch raises an error and the callback returns provider-specific failure output.

## Frontend Behavior

Learner checkout:

- If `wechatpay` is enabled and the learner is inside WeChat, the WeChat option requests `wx_pub` and invokes `WeixinJSBridge`.
- Outside WeChat, WeChat uses QR when enabled.
- Alipay uses QR.
- Stripe remains available when configured.

Billing checkout:

- `stripe` opens Stripe Checkout.
- `pingxx`, `alipay`, and `wechatpay` use the existing QR dialog and sync polling.
- The QR dialog limits channel switching for native providers because the provider is fixed for the created billing order.

## Configuration

New backend configuration keys:

- `ALIPAY_APP_ID`
- `ALIPAY_APP_PRIVATE_KEY_PATH`
- `ALIPAY_PUBLIC_KEY_PATH`
- `ALIPAY_GATEWAY_URL`
- `ALIPAY_NOTIFY_URL`
- `WECHATPAY_APP_ID`
- `WECHATPAY_MCH_ID`
- `WECHATPAY_API_V3_KEY`
- `WECHATPAY_MERCHANT_SERIAL_NO`
- `WECHATPAY_PRIVATE_KEY_PATH`
- `WECHATPAY_PLATFORM_CERT_PATH`
- `WECHATPAY_NOTIFY_URL`

`WECHATPAY_APP_ID` falls back to `WECHAT_APP_ID` when empty.

## Verification Focus

The primary checks are:

- Channel resolution for native-first and Ping++ fallback behavior.
- Provider payload construction and notification normalization.
- Legacy learner order idempotency and amount mismatch rejection.
- Billing checkout, sync, webhook paid state transition, and duplicate grant protection.
- Frontend provider selection, WeChat JSAPI invocation, QR rendering, and polling close behavior.

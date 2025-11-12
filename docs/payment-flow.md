# Payment Flow Overview

## Ping++ (Current Provider)
- Order creation initiates through `init_buy_record` in `src/api/flaskr/service/order/funs.py`. The function prepares the order, applies discounts, and eventually calls `create_pingxx_order`.
- `create_pingxx_order` (in `src/api/flaskr/service/order/pingxx_order.py`) initializes Ping++ credentials (`PINGXX_SECRET_KEY`, `PINGXX_PRIVATE_KEY_PATH`) via `init_pingxx` and creates a charge with the Ping++ SDK.
- Charge metadata is persisted in the `PingxxOrder` SQLAlchemy model (`src/api/flaskr/service/order/models.py`). Records include charge identifiers, amounts, and raw payload snapshots for later reconciliation.
- When a Ping++ webhook confirms payment, `success_buy_record_from_pingxx` updates both the stored charge payload and the parent `Order` status, promoting the user state and sending Feishu notifications.
- Manual success flows can fall back to `success_buy_record`, which directly marks the `Order` as paid without depending on Ping++ callbacks.

These touch points will guide the upcoming payment factory abstraction; each call site is an integration seam where provider-specific logic must be isolated behind the factory interface.

## Stripe (New Provider)
- Stripe support is implemented via `StripeProvider` (`src/api/flaskr/service/order/payment_providers/stripe.py`), which currently wraps Payment Intent and Checkout Session creation using the official Stripe SDK. It normalises responses into the shared `PaymentCreationResult`.
- `generate_charge` detects the desired provider through `Order.payment_channel` (defaulting to Ping++) and optional `channel` hints (`"stripe"` or `"stripe:checkout_session"`), routing to Stripe when appropriate.
- Newly created Stripe payments persist metadata and raw payloads inside the `StripeOrder` model, ensuring parity with the existing Ping++ audit trail.
- Returned `BuyRecordDTO` instances include a `payment_payload` dictionary (client secret, checkout session info, etc.) so callers can distinguish Stripe flows without relying on the legacy `qr_url` field.
- API consumers can explicitly choose a provider by passing `payment_channel` (`pingxx` or `stripe`) when invoking `/reqiure-to-pay`; the existing `channel` field remains for provider-specific options (e.g., `wx_pub_qr`, `stripe:checkout_session`).
- Refunds can be initiated through `refund_order_payment`, which routes to the Stripe provider, creates a refund via the API, and marks both `StripeOrder` and `Order` records as refunded.

### Request Examples

- **Ping++ (JSAPI)**

```json
{
  "order_id": "ORDER_BID",
  "payment_channel": "pingxx",
  "channel": "wx_pub"
}
```

- **Stripe (Checkout Session)**

```json
{
  "order_id": "ORDER_BID",
  "payment_channel": "stripe",
  "channel": "stripe:checkout_session"
}
```

- **Fetch Payment Detail**

```json
{
  "order_id": "ORDER_BID"
}
```

### Response Snapshot

```json
{
  "order_id": "ORDER_BID",
  "user_id": "USER_BID",
  "price": "199.00",
  "channel": "stripe:checkout_session",
  "qr_url": "https://checkout.stripe.com/c/pay/cs_test_xxx",
  "payment_channel": "stripe",
  "payment_payload": {
    "mode": "checkout_session",
    "client_secret": "cs_test_client_secret_xxx",
    "checkout_session_url": "https://checkout.stripe.com/c/pay/cs_test_xxx",
    "checkout_session_id": "cs_test_xxx",
    "payment_intent_id": "pi_test_xxx",
    "latest_charge_id": "ch_test_xxx"
  }
}
```

### Webhook Handling

- POST `/api/order/stripe/webhook` verifies the Stripe signature, updates the stored `StripeOrder` record, and marks the corresponding `Order` as paid/refunded/failed as applicable. Unrecognised events are acknowledged with HTTP 202 and logged for review.

## Configuration Inventory

### Ping++ Environment Keys
- `PINGXX_SECRET_KEY`, `PINGXX_PRIVATE_KEY_PATH`, and `PINGXX_APP_ID` now live in the central registry (`src/api/flaskr/common/config.py`) under the `payment` group so they flow into generated `.env` examples.
- Ping++ still requires filesystem access to the private key path; ensure deployment artefacts include the key alongside environment configuration.

### Stripe Environment Keys
- `STRIPE_SECRET_KEY` (secret) and `STRIPE_PUBLISHABLE_KEY` expose the core credentials for backend and frontend usage.
- `STRIPE_WEBHOOK_SECRET` secures webhook validation; keep it server-side only.
- Optional helpers such as `STRIPE_API_VERSION`, `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`, and `STRIPE_DEFAULT_CURRENCY` enable consistent behaviour across environments.

### Cook Web Environment Keys
- `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` supplies the publishable key for initializing Stripe.js on the frontend. This should match the backend `STRIPE_PUBLISHABLE_KEY` but can be scoped per environment.
- `NEXT_PUBLIC_STRIPE_ENABLED` toggles the Stripe UI so we can progressively roll out the new flow without rebuilding the backend.

### Frontend Flow & QA Notes
- The Cook Web payment modals now expose a "Stripe" option whenever `NEXT_PUBLIC_STRIPE_ENABLED=true` and the publishable key is configured. Selecting Stripe renders a Payment Element backed by the newly created Payment Intent. If the backend requests a Checkout Session instead, the UI guides the user through a redirect flow.
- Stripe Checkout redirects must target `/payment/stripe/result` so the SPA can recover the order context. Point `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL` to `${APP_URL}/payment/stripe/result?session_id={CHECKOUT_SESSION_ID}`. The frontend also keeps a short-lived `session_id -> order_id` mapping during the redirect.
- Manual QA checklist:
  1. Ping++ WeChat or Alipay QR flow (creation, timeout refresh, coupon application).
  2. Stripe card payment (Payment Intent) with a test card such as `4242 4242 4242 4242`.
  3. Stripe Checkout fallback (temporarily disable card creation, verify the result page surfaces status and the user can jump back into `/c`).
  4. Mobile modal parity (WeChat JSAPI vs Stripe card vs Stripe Checkout).

Remember to regenerate `.env` examples (`python scripts/generate_env_examples.py`) whenever payment configuration changes.

## Database Updates
- `order_orders` now includes a `payment_channel` column (`VARCHAR(50)`) that defaults to `pingxx`, allowing the service layer to route through provider-specific logic.
- New table `order_stripe_orders` stores raw Stripe payment artifacts (payment intent, checkout session, metadata) alongside business identifiers; see `StripeOrder` in `src/api/flaskr/service/order/models.py` for column details.

## Operational Considerations
- Webhooks cover the primary lifecycle transitions; if redundancy is required, schedule a background reconciliation job that calls `sync_payment_status` for orders still in `pending` states and persists any deltas. This job is not implemented yet and remains on the backlog.
- Background workers must fan out by `payment_channel` before invoking provider-specific sync or refund logic to avoid hard-coded dependencies.

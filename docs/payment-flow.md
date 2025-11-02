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
- Returned `BuyRecordDTO` instances surface Stripe-specific data via the existing `qr_url` field (client secret or checkout URL), pending API schema evolution later in the rollout.

## Configuration Inventory

### Ping++ Environment Keys
- `PINGXX_SECRET_KEY`, `PINGXX_PRIVATE_KEY_PATH`, and `PINGXX_APP_ID` now live in the central registry (`src/api/flaskr/common/config.py`) under the `payment` group so they flow into generated `.env` examples.
- Ping++ still requires filesystem access to the private key path; ensure deployment artefacts include the key alongside environment configuration.

### Stripe Environment Keys
- `STRIPE_SECRET_KEY` (secret) and `STRIPE_PUBLISHABLE_KEY` expose the core credentials for backend and frontend usage.
- `STRIPE_WEBHOOK_SECRET` secures webhook validation; keep it server-side only.
- Optional helpers such as `STRIPE_API_VERSION`, `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`, and `STRIPE_DEFAULT_CURRENCY` enable consistent behaviour across environments.

Remember to regenerate `.env` examples (`python scripts/generate_env_examples.py`) whenever payment configuration changes.

## Database Updates
- `order_orders` now includes a `payment_channel` column (`VARCHAR(50)`) that defaults to `pingxx`, allowing the service layer to route through provider-specific logic.
- New table `order_stripe_orders` stores raw Stripe payment artifacts (payment intent, checkout session, metadata) alongside business identifiers; see `StripeOrder` in `src/api/flaskr/service/order/models.py` for column details.

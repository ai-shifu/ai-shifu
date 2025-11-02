# Payment Flow Overview

## Ping++ (Current Provider)
- Order creation initiates through `init_buy_record` in `src/api/flaskr/service/order/funs.py`. The function prepares the order, applies discounts, and eventually calls `create_pingxx_order`.
- `create_pingxx_order` (in `src/api/flaskr/service/order/pingxx_order.py`) initializes Ping++ credentials (`PINGXX_SECRET_KEY`, `PINGXX_PRIVATE_KEY_PATH`) via `init_pingxx` and creates a charge with the Ping++ SDK.
- Charge metadata is persisted in the `PingxxOrder` SQLAlchemy model (`src/api/flaskr/service/order/models.py`). Records include charge identifiers, amounts, and raw payload snapshots for later reconciliation.
- When a Ping++ webhook confirms payment, `success_buy_record_from_pingxx` updates both the stored charge payload and the parent `Order` status, promoting the user state and sending Feishu notifications.
- Manual success flows can fall back to `success_buy_record`, which directly marks the `Order` as paid without depending on Ping++ callbacks.

These touch points will guide the upcoming payment factory abstraction; each call site is an integration seam where provider-specific logic must be isolated behind the factory interface.

## Configuration Inventory

### Ping++ Environment Keys
- Runtime code expects `PINGXX_SECRET_KEY`, `PINGXX_PRIVATE_KEY_PATH`, and `PINGXX_APP_ID` via `get_config`, but these keys are not yet defined in the central config registry (`src/api/flaskr/common/config.py`). We should register them when we revise configuration handling for payment providers.
- Ping++ also relies on filesystem access to a private key path; document deployment requirements when refactoring to the factory pattern.

### Stripe (Proposed)
- `STRIPE_SECRET_KEY` (required, secret, group `payment`): API key used for server-side requests and webhook signature verification.
- `STRIPE_PUBLISHABLE_KEY` (required, group `payment`): Client-facing key returned to the frontend when initializing Stripe elements or checkout sessions.
- `STRIPE_WEBHOOK_SECRET` (required, secret, group `payment`): Signature secret for webhook verification, stored server-side only.
- `STRIPE_API_VERSION` (optional, default to Stripe’s latest supported version): Ensures predictable behaviour across environments.
- `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL` (optional, fall back to web defaults): Used when creating checkout sessions to control redirection.

Additions to `config.py` will require regenerating `.env` examples and updating configuration fixtures once implementation begins.

## Database Updates
- `order_orders` now includes a `payment_channel` column (`VARCHAR(50)`) that defaults to `pingxx`, allowing the service layer to route through provider-specific logic.
- New table `order_stripe_orders` stores raw Stripe payment artifacts (payment intent, checkout session, metadata) alongside business identifiers; see `StripeOrder` in `src/api/flaskr/service/order/models.py` for column details.

# Payment Flow Overview

## Ping++ (Current Provider)
- Order creation initiates through `init_buy_record` in `src/api/flaskr/service/order/funs.py`. The function prepares the order, applies discounts, and eventually calls `create_pingxx_order`.
- `create_pingxx_order` (in `src/api/flaskr/service/order/pingxx_order.py`) initializes Ping++ credentials (`PINGXX_SECRET_KEY`, `PINGXX_PRIVATE_KEY_PATH`) via `init_pingxx` and creates a charge with the Ping++ SDK.
- Charge metadata is persisted in the `PingxxOrder` SQLAlchemy model (`src/api/flaskr/service/order/models.py`). Records include charge identifiers, amounts, and raw payload snapshots for later reconciliation.
- When a Ping++ webhook confirms payment, `success_buy_record_from_pingxx` updates both the stored charge payload and the parent `Order` status, promoting the user state and sending Feishu notifications.
- Manual success flows can fall back to `success_buy_record`, which directly marks the `Order` as paid without depending on Ping++ callbacks.

These touch points will guide the upcoming payment factory abstraction; each call site is an integration seam where provider-specific logic must be isolated behind the factory interface.

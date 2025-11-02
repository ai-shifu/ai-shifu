# Stripe Payment Integration Tasks

## Discovery & Alignment
- [x] Confirm required naming for the new payment channel flag (`stripe` vs `scripe`) to avoid mismatched literals across code and migrations. Decision: use `stripe` consistently; treat `scripe` as a typo in the initial requirements.
- [x] Map the existing Ping++ order flow (creation, payment callbacks, refunds) to understand touch points for the upcoming factory abstraction (`src/api/flaskr/service/order/pingxx_order.py`, related services, and webhook handlers). See `docs/payment-flow.md` for the discovery summary.
- [x] Inventory environment variables and credentials needed for Stripe (secret key, webhook secret, publishable key) and decide naming conventions that follow existing config standards. See `docs/payment-flow.md` (“Configuration Inventory”) for proposed keys.

## Database Layer
- [x] Design the `order_stripe_orders` schema, mirroring `order_pingxx_orders` while capturing Stripe-specific raw payloads (charge/session/payment intent data, status fields, metadata, timestamps). Implemented via `StripeOrder` in `src/api/flaskr/service/order/models.py`.
- [x] Update `src/api/flaskr/service/order/models.py` with a new SQLAlchemy model for Stripe orders, ensuring comments/indexes follow the project database conventions.
- [x] Add the `payment_channel` column to the `Order` model with sensible defaults, length 50, comment, and index if needed for query performance. Default set to `pingxx` to maintain backward compatibility.
- [x] Generate an Alembic migration creating `order_stripe_orders` and adding `payment_channel` to `order_orders`, with downgrade logic and index definitions. See `src/api/migrations/versions/c9c92880fc67_add_stripe_payment_channel.py`.
- [x] Backfill `payment_channel` for existing records (default to `pingxx`) inside the migration or follow-up data task to keep downstream code consistent. Performed in the same migration via SQL update.
- [x] Regenerate environment example files if new env vars are introduced (`python scripts/generate_env_examples.py`). Updated `docker/.env.example.*` with Stripe/Ping++ settings.

## Service Layer & Factory Abstraction
- [x] Define a payment channel factory interface (e.g., `PaymentProvider`, `PaymentContext`) that encapsulates order creation, charge confirmation, refunds, and status sync. Implemented in `src/api/flaskr/service/order/payment_providers/base.py` with registry helpers in `__init__.py`.
- [x] Refactor existing Ping++ implementation to comply with the new factory without changing behaviour; ensure dependency injection slots into current service entrypoints. `PingxxProvider` now backs `pingxx_order` helpers and order creation leverages the registry.
- [x] Implement a Stripe provider class handling session/intent creation, webhook verification, refund initiation, and synchronization, leveraging the new factory. See `src/api/flaskr/service/order/payment_providers/stripe.py`.
- [x] Decide where to store provider selection (likely in order creation workflow) and update service logic to route through the factory based on `payment_channel`. `generate_charge` inspects `Order.payment_channel` and routes to either Ping++ or Stripe flows.
- [x] Implement provider-agnostic refund handling (initially Stripe) and ensure persistence mirrors `StripeOrder` changes. `refund_order_payment` issues refunds via the provider abstraction and updates associated records.
- [x] Update any tasks, schedulers, or background jobs that currently hardcode Ping++ so they use the provider abstraction. Codebase review found no scheduled jobs beyond service functions; existing flows now depend on the provider registry.

## API & Integration Tasks
- [x] Extend order creation APIs/endpoints to accept and validate the desired payment channel, defaulting to existing behaviour when unspecified. `order.reqiure-to-pay` now accepts `payment_channel` and routes requests via the provider abstraction.
- [x] Add new endpoints or extend current ones for Stripe-specific steps (e.g., returning client secret/session ID). Added `/payment-detail` to surface provider-specific payloads.
- [x] Implement Stripe webhook processing (signature validation, event fan-out). `/stripe/webhook` verifies signatures, updates Stripe orders, and marks core orders paid/refunded.
- [x] Implement webhook handlers with signature validation and idempotency protections, persisting Stripe payloads into `order_stripe_orders`.
- [x] Update error handling and response payloads to include payment channel context where relevant. `BuyRecordDTO` now exposes `payment_channel` and structured `payment_payload` for clients.

## Configuration & Infrastructure
- [x] Add Stripe configuration entries in `src/api/flaskr/common/config.py`, with validation and grouping, and update config fixtures/tests.
- [x] Document required environment variables in README/docs and ensure secrets management (local `.env`, deployment manifests) is updated. README now lists required Ping++/Stripe keys.
- [x] Evaluate background job queue or schedulers for Stripe reconciliation (optional depending on business requirements) and plan deployment changes if needed. Documented recommendations in `docs/payment-flow.md` under Operational Considerations; backlog item remains for implementing a reconciliation job.

## Testing & Quality
- [x] Add unit tests for the payment factory to verify provider selection and behaviour parity with Ping++. Covered in `src/api/tests/service/order/test_payment_channel_resolution.py` and associated DTO tests.
- [x] Create integration tests (or service-level tests) covering Stripe charge creation, webhook handling, and refund flows using mocked Stripe SDK responses. Added service-layer tests in `tests/service/order/test_stripe_webhook.py` and `test_stripe_refund.py` using stubbed providers.
- [x] Update existing Ping++ tests affected by the factory refactor to ensure no regressions. Legacy tests now supply the optional `payment_channel` argument.
- [ ] Run full backend test suite (`pytest`) once implementation is complete. (Partial runs for Stripe tests currently blocked by missing optional dependencies such as `flask_migrate` in the test environment.)

## Documentation & Rollout
- [x] Update developer documentation with payment architecture overview and instructions for adding new providers. Expanded `docs/payment-flow.md` with provider selection flow and request samples.
- [ ] Provide migration/rollback guidance and note any data backfill steps for operations.
- [ ] Prepare release notes outlining new payment channel support and configuration steps for staging/production environments.

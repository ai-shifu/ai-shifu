---
title: Native China Payments
status: needs-review
owner_surface: backend
last_reviewed: ""
canonical: true
---

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

`WECHATPAY_APP_ID` falls back to `WECHAT_APP_ID` when empty.
`HOST_URL` is required outside local/test environments. Alipay and WeChat Pay
notification URLs are derived from `HOST_URL` and `PATH_PREFIX` as
`/api/callback/alipay-notify` and `/api/callback/wechatpay-notify` by default.
Stripe webhooks still must be registered in Stripe Dashboard as
`https://your-domain.com/api/order/stripe/webhook`.

## Verification Focus

The primary checks are:

- Channel resolution for native-first and Ping++ fallback behavior.
- Provider payload construction and notification normalization.
- Legacy learner order idempotency and amount mismatch rejection.
- Billing checkout, sync, webhook paid state transition, and duplicate grant protection.
- Frontend provider selection, WeChat JSAPI invocation, QR rendering, and polling close behavior.

## Shared business boundary (PR02 completion)

Business owns payable amounts, currency, campaign eligibility, order identity,
subscription periods and entitlements. Adapters serialize `CheckoutTerms` and
normalize verified/query responses into `PaymentEvent`, `PaymentFacts` and
`SubscriptionFacts`. Contract state is independent from payment state: an active
subscription alone cannot pay an arbitrary first checkout. Existing cycle,
amount, currency, latest-attempt and monotonic-state guards remain in force.
Stripe keeps its payment/subscription modes, provider prices, first-invoice
coupon semantics, contract/customer references, cancellation and resumption.
No gateway SDK/API version, merchant configuration or default routing changes.

Optional catalog readers, discount publishers and signed catalog notification
normalizers register independently. Catalog inbox idempotency and price health
apply to normalized product/price snapshots regardless of protocol envelope.
Raw snapshot writers and recovery readers own compatibility with the original
provider tables; they do not grant credits or change purchase eligibility.
Removing a provider from new-checkout configuration does not rewrite historical
order attribution or abandon existing contracts.
Query, close and recurring-contract renewal discriminators may be declared
independently through `query_reference_type`, `close_reference_type` and
`renewal_reference_type`. The older `reference_type` and historical snapshot
aliases remain compatible defaults. `PaymentQueryTerms.reference_kind` separates
payment versus contract identity validation from these protocol strings; new
renewal/preorder metadata snapshots that distinction and old records retain their
previous meaning. An unpaid next-cycle order does not prevent
the current hosted contract from recovering its active or scheduled-cancel state;
initial and upgrade access still require their own paid order.

Refund writers can register independently from native snapshot storage. Existing
Stripe and native refund writers retain their schemas; other integrations fall
back to order metadata for the refund ID, status and response. Missing a native
snapshot model must not turn a completed external refund into a local rollback.
Registered hosted billing callbacks do not require a native table. Checkout,
notification and query writers can register independently; their generic
non-native fallback keeps the evidence in order metadata. Late checkout receipts
retain the external reference, action, raw response and independent attempt status
without repointing a settled order. Learner options require a registered learner
attempt implementation or native snapshot storage; billing-only integrations are
excluded from learner options before selection. Unmatched or invalid callbacks
remain unsuccessful.
The integration declares `webhook_transport`; Stripe and Ping++ keep their dedicated
legacy entry points. Pending checkout reuse and replacement follow the integration's
recovery protocol rather than table registration. A supported close response can
confirm cancellation when query is unavailable; unsupported close operations fail
before provider I/O. The shared cancellation result admits `canceled`,
`cancelled`, `closed` and `expired` (case/whitespace normalized) consistently for
billing replacement, learner repricing and generic recovery. Progress, unknown,
failed and completed-payment outcomes do not confirm closure. Existing gateway
SDK calls and raw statuses are preserved.

Learner and billing refunds commit the original request and stable idempotency key before
provider I/O, retain the provider response in a separate transaction, then apply
their local effects atomically. A separate per-order renewable lease serializes
refunds independently from callback and credit locks. Failed local finalization
uses the saved receipt; uncertain transport or receipt-commit outcomes reuse the
same request/key. A learner refund explicitly retried after a definite failed or
canceled result gets a new operation key and retains the rejected receipt for
association of delayed events. In-progress or uncertain outcomes never rotate the
key. Refund-capable adapters must honor that key (Stripe already
supports it through its existing request option). Other Stripe request parameters
and the existing refund result and cancellation behavior stay compatible.
A refund response is final only when its normalized status is `succeeded`.
Pending or action-required responses remain durable and return their actual status;
they do not refund the order, cancel its plan, or remove its credits. Verified
refund notifications or queries complete the saved operation without a second RPC,
and replayed pending events cannot downgrade success. Stripe refund-object events
(`refund.created`, `refund.updated`, `charge.refund.updated`, `refund.failed`)
use the object's status when reconciling a saved refund operation; creating a
refund is not proof that the saved operation succeeded. Both learner and billing
paths retain these asynchronous semantics. Without a saved operation or history,
the existing Stripe `refund.created` payment projection remains compatible with
the pre-abstraction implementation, including progress events. Tightening that
independent legacy behavior belongs to the follow-up reliability change.
Learner callbacks and queries for registered non-Stripe adapters use the same saved-operation
reconciliation as Stripe: a verified current-attempt refund success removes paid
order access and promotes the durable refund receipt, without repeating the RPC.
Old attempts, another provider, mismatched prices and unverified notifications
cannot settle the current refund; duplicate or delayed paid events cannot restore
refunded access. See the official
[Stripe refund test cases](https://docs.stripe.com/testing#refunds) and
[event types](https://docs.stripe.com/api/events/types).

Cancel and resume independently enforce the registered contract capabilities at
the write API, while platform-managed plans retain local lifecycle operations.
Provider-managed command responses must identify the requested contract before
local finalization; missing or foreign IDs cannot change lifecycle state.
They must also report a recognized live contract status and an explicit boolean
`cancel_at_period_end` equal to the requested renewal setting. Pending, failed,
unknown or already-ended results, absent flags and contradictory flags cannot
finalize the command. Adapters normalize provider-specific status names; Stripe
maps `unpaid` to the existing delinquent state. The generic guard validates the
adapter's declared outcome. Stripe's legacy SDK decoder still defaults a missing
response ID to the requested contract and coerces the renewal flag with `bool`;
strict decoding of those independent legacy behaviors belongs to the follow-up
reliability change. Clearing cancellation does not clear delinquency or a pause,
and scheduling cancellation during a trial retains access through the current
period. Management reuses the existing local status vocabulary and preserves
historical contract-event translation. It does not renew the paid period,
issue credits or reset renewal time.
An explicitly scheduled cancellation remains reversible when the contract is
delinquent: both API admission and serialized management operations use the
cancellation flag without granting active access. Existing frontend consumers
continue to render the server-owned management operations.
See the [Stripe subscription update contract](https://docs.stripe.com/api/subscriptions/update).
Opposing commands share a renewable lease; provider I/O holds no database
transaction. Finalization locks and rereads the subscription, preserves the
provider receipt, and rejects an obsolete command when a webhook, renewal, or
plan change committed during I/O. These desired-state provider operations must
be safe to retry after an uncertain response. Local failure never commits a
partial status/lifecycle transition. For an already admitted refund operation, both domains use the same receipt
merge rule: an earlier matching progress callback cannot hide a definitive RPC
response. A known terminal result is retained over a later progress response;
missing receipt IDs may be filled without changing finality, and mismatched
nonempty refund IDs cannot promote each other's outcomes. Original progress
receipts remain in operation metadata for reconciliation.

The default query interpreter requires the returned payment or contract identity
to be present and equal to the requested reference. Matching amount and currency,
or repeating the request's merchant-order lookup, cannot replace this evidence.
Unidentified results cannot fulfill learner purchases or settle billing orders
and issue credits. Provider-specific query interpreters retain their own explicit
identity validation, including Stripe's existing stricter checks.

Definite refund failures in both domains retain their terminal receipt over
delayed pending/action-required or unknown events, so explicit retry remains
available. Billing refund retries also archive rejected operation IDs, so delayed
callbacks, including stale success, cannot claim a replacement while its response
is still in flight. Refund events for saved operations bypass generic
payment-status transitions in callbacks and queries. Registered native snapshot
writers project the admitted business result after reconciliation, rather than
projecting raw reversal facts first. An unidentified refund cannot claim a
replacement with archived history. This applies to learner payment details and
billing order/subscription/wallet state, with duplicate and rollback coverage.
Only the association-aware refund handler can settle them after validating the
saved operation. Raw payment snapshots project the resulting admitted business
state. A valid current success still settles the order, subscription and wallet
once; an archived or mismatched success leaves them unchanged.
The admission decision reads the freshly locked order. Verified reversals without
a saved platform refund operation retain their existing legacy order projection;
this repair does not add new refund entitlement policy for those notifications.
Learner Stripe callbacks likewise defer payment-detail and response projection
until saved-operation reconciliation. An archived or mismatched refund success
cannot mark a replacement's payment snapshot refunded or return `refunded` while
that replacement remains pending. Current successful evidence atomically updates
the learner order, payment details and saved operation; duplicate success remains
idempotent. Stripe reversals without a saved learner refund operation retain their
legacy snapshot-only projection.

Verified Stripe subscription events and
subscription queries are authoritative contract evidence; Checkout completion
remains payment-only evidence. A contract arriving before payment has the same
authority as one arriving afterwards: later payment hints cannot overwrite its
status, cancellation flag or event clock. Draft access can activate after valid
payment, and initial paid grants preserve already blocked contract states.
Recoverable paused or delinquent contracts can regain their existing grant after
real authoritative recovery; Stripe cancellation is terminal, per the
[Stripe cancellation contract](https://docs.stripe.com/api/subscriptions/cancel).
Paid-grant repair must preserve a confirmed
contract, including cancellation, delinquency, pause, and expiry.

Contract queries reject a missing or foreign Stripe subscription ID before any
recovery, paid transition or credit grant.

Billing synchronization reads detached query terms, closes its database transaction,
then calls the provider without holding the credit lock. Finalization acquires the
credit lock and fresh order/subscription row locks, revalidates the provider,
reference, product and authorized price/currency, and discards stale evidence when
a callback or subscription-management action committed during I/O. Paid/refunded
state, cancellation/resumption and exactly-once grants keep their existing policy.

Merchant order identity and gateway payment identity are separate. The default
notification mapper uses `order_bid` to associate the local business order and
verified `PaymentFacts.provider_reference` to update its gateway reference. When
that fact is absent, retain the reference saved during creation. Protocol-specific
mappers, including Stripe, retain their declared reference contracts. Raw snapshots
use the order's reference so later query, closure and refund operations remain valid.
Verified early callbacks may create their raw snapshot before checkout returns.
When checkout returns the same current payment, retain the callback's terminal
snapshot and original provider object, and store the creation response as a
separate receipt. A genuinely different late payment remains pending evidence.
Reported payment references must match an already-bound attempt before any callback
storage, state transition or credit/purchase effect. An unpersisted creation may
establish its gateway reference from the first verified callback; row/lifecycle
locks serialize that binding. Later callbacks cannot retarget it. The learner also
requires the order's current provider before fulfillment. A merchant-only lookup
belongs in `notification.order_bid`, with an absent payment fact represented as
`None`; it must not masquerade as a different gateway identity. Contract-only
notifications do not replace a checkout's payment reference. A late creation result
that conflicts with a verified learner binding is retained for reconciliation,
without replacing that binding or presenting the conflicting payment action.
Billing creation revalidates the same binding after provider I/O even when the
early callback left the order pending. A conflicting result is an independent
receipt, not the current raw payment or browser action; an omitted response
reference retains the verified binding. A subsequent paid callback for that
binding can still settle exactly once.

An existing hosted subscription rejects a different nonempty contract reference.
The first binding and absent optional legacy references remain supported. Rebinding
requires a newly validated paid upgrade through the current provider, shared by
query and webhook settlement; ordinary contract events and paid-order replays
cannot authorize it. This preserves Stripe's new-contract upgrade flow while
preventing foreign active, delinquent or canceled contracts from taking over.
Direct learner checkout commits its authorized request and pending snapshot before
provider I/O, then finalizes without rewinding an early callback. Retries reuse the
original merchant request. Creation and coupon repricing serialize independently
from callbacks so payment can settle while creation is still in flight.

Billing option discovery and modern `payment_option` admission share the same
client capability predicate: QR/hosted scenes with `qr` or `redirect` actions.
Routes requiring `sdk_confirm`, `jsapi`, or another unimplemented billing action
are not advertised as available. Their modern explicit selection fails before
provider I/O or order creation. Learner SDK/JSAPI consumers and legacy explicit
provider/channel clients retain their existing transport contracts. Adding a new
billing action requires its consumer and admission contract in the same change.

Capabilities gate execution as well as presentation. A provider-managed plan
requires `subscription_create`; otherwise plan options and plan checkout reject
it before provider I/O, while one-time topups remain eligible. Platform-managed
plans continue to use ordinary payments. When `query` is false, learner and billing
return recovery reads local state and waits for verified callbacks without calling
an unsupported query or replaying paid effects. Query-capable Stripe recovery
keeps its existing behavior.

Authenticated billing catalogs expose per-product `checkout_operations`: action,
availability, ordered allowed payment option IDs, i18n label/tooltip keys and tone.
The browser presents this decision and submits the selected option. Checkout
revalidates the same policy. Old server responses use an isolated compatibility
reader; current UI does not derive eligibility from gateway names. Shared
`paymentContracts` parses modern actions and legacy QR/JSAPI/SDK responses once.
QR content is opaque data, while redirects require HTTP(S). Mobile keeps its
existing web and wallet app launches; other QR data is rendered after an
accepted pay click and never passed to browser navigation. Both learner views
dispatch SDK actions through `PaymentSdkForm`: the built-in Stripe handler
retains `StripeCardForm`, and additional SDK handlers register during application
setup before payment views mount. Unregistered SDKs fail closed. Refreshing a
selection immediately clears the old action and suspends execution and polling
until the latest response arrives; stale responses cannot restore it.
A new hosted provider uses `/payment/billing-result` or `/payment/result`;
Stripe's existing return paths and session-storage keys remain supported.
Hosted return URLs are independent of optional catalog support. Pending JSAPI
and SDK actions can be recovered without a QR URL or a built-in channel name;
the existing WeChat prepay re-signing path remains at its protocol boundary.

Regression proof includes exact Stripe request terms before and after migration,
ordinary and provider-managed extension providers with distinct protocols,
prices plus 50%/100% first-cycle discounts, duplicate signed notifications,
renewals, cancel/resume, refunds, disabled-new-checkout/history behavior,
read-only catalog eligibility and desktop/mobile action execution. External
merchant calls are simulated in these isolated tests; they do not establish
live gateway acceptance. Alipay/WeChat cutover remains separate work.

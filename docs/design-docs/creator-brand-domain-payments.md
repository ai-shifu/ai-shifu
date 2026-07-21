---
title: Creator Brand Domain And Payments
status: implemented
owner_surface: shared
last_reviewed: 2026-07-12
canonical: true
---

# Creator Brand Domain And Payments

## Background

AI-Shifu already resolves creator billing entitlements, creator-owned custom
domains, and entitlement-backed logo overrides. Learner payments and WeChat
OAuth still use process-wide environment configuration. This design lets an
eligible course owner supply account-level brand, domain, WeChat OAuth, and
learner-payment configuration without introducing a second tenant identity.

The account boundary is `creator_bid`. All courses owned by the same account
share the configuration. Chinese product copy calls this role `课程负责人`.

## Goals

- Let an eligible course owner configure wide and square logos, one active
  custom domain, a WeChat OAuth app, and Pingxx, Stripe, Alipay, or WeChat Pay.
- Route learner course payments directly to the course owner's merchant account.
- Keep secrets encrypted and write-only through public APIs.
- Bind every new learner order to the exact integration version used to create it.
- Preserve global configuration for existing courses and keep old callbacks
  working after an entitlement expires or credentials rotate.

## Non-Goals

- No new tenant hierarchy, platform commission, split settlement, or managed
  merchant onboarding.
- No per-course override in the first version.
- No silent fallback from an expired custom merchant to the platform merchant.
- No custom-domain access to another owner's courses.

## Ownership And Entitlements

`BillingEntitlement` remains the access source. `branding_enabled` and
`custom_domain_enabled` retain their current meaning. Product or manual
entitlement payloads add `custom_wechat_enabled` and
`custom_payment_enabled`. The global `CREATOR_CUSTOMIZATION_ENABLED` switch
can prevent new configuration and new custom checkouts without disabling
historic callback processing.

User-entered settings are not stored inside entitlement payloads. They reuse
the SaaS plugin's unified `saas_user_configs` table with namespaced keys. Brand
settings use one mutable JSON key. Each integration version uses an encrypted
version key plus a small active-pointer key. The last verified version is used
for new requests, while old version rows remain addressable by existing orders.

Logo uploads use the managed courses OSS profile, accept only validated PNG,
JPEG, or WebP content up to 2 MB, and preserve the extension in the object key.
Saved logo URLs may point only to configured managed-storage hosts or local
managed storage. A custom domain becomes effective only after TXT ownership,
the configured CNAME target, and a trusted matching TLS certificate are all
present.

## Runtime Resolution

The backend derives the course owner from the requested Shifu. On a verified
custom host, that owner must equal the domain owner. Runtime config then emits
owner branding, WeChat App ID, ready payment channels, and the relevant Stripe
publishable key. Secrets are never serialized.

Custom WeChat identities use an App-ID-scoped credential identifier. The
platform app keeps the legacy identifier shape for compatibility.

## Payments And Callbacks

Learner orders snapshot `creator_bid` and `payment_integration_bid`. Payment
providers accept an optional credential context; absence means the current
global environment configuration. Provider clients must not retain one
creator's credentials in process-global state.

Custom webhooks use the stable platform API route
`/api/order/webhooks/<provider>/<callback_token>`. The token resolves an
integration version before signature verification. The verified provider
result must match the order's creator and integration snapshot. Duplicate and
out-of-order notifications keep the existing idempotent order transitions.

When entitlement or configuration becomes unavailable, new custom payments
stop. Existing webhook, sync, refund, and reconciliation operations continue
with the snapshotted integration version.

## Order Ownership And Reporting Boundaries

Independent payment and independent domain are separate reporting dimensions.
They must not be inferred from each other.

For platform-domain orders that use a course owner's independent payment
channel, the order remains an AI-Shifu platform order. The order belongs in the
teacher-facing order menu and in operator order management, but reporting must
mark it as `creator` settlement so it contributes to GMV/order counts without
being counted as platform-collected revenue.

For custom-domain orders, the order may still be written to the shared learner
order tables for authorization, callbacks, refunds, reconciliation, and support.
The custom-domain dashboard scope is narrower than "all orders for this
teacher": it is the current `domain_binding_bid` plus the owning `creator_bid`.
If that product surface is limited to owner-collected payments, it should also
filter to creator settlement. Operator tooling may keep an audit/search view,
but platform-domain order lists should not silently mix in custom-domain orders.

Custom-domain order reporting needs an order-time snapshot instead of deriving
history from current configuration. The required snapshot fields are:

- request host at checkout time
- matched `domain_binding_bid`
- whether the order was created from a custom domain
- settlement owner (`platform` or `creator`)
- payment integration snapshot already used for independent payment

This follow-up is intentionally separate from the first platform-domain
independent-payment reporting pass.

## Public Interfaces

- `GET /api/billing/customization`
- `PUT /api/billing/customization/branding`
- `POST /api/billing/customization/branding/logo`
- `POST /api/billing/customization/domains`
- `POST /api/billing/customization/domains/<domain_binding_bid>/verify`
- `DELETE /api/billing/customization/domains/<domain_binding_bid>`
- `PUT /api/billing/customization/integrations/<provider>`
- `POST /api/billing/customization/integrations/<provider>/verify`
- `DELETE /api/billing/customization/integrations/<provider>`
- `POST /api/order/webhooks/<provider>/<callback_token>`

Secret-bearing writes replace complete secret sets. Reads expose only masked
metadata such as `secret_configured`, readiness, last verification time, and
the callback URL.

## Rollout And Compatibility

Schema and read paths land first, followed by configuration APIs, runtime
resolution, payment dispatch, and the admin UI. A whitelist/manual entitlement
is used for the first production accounts before product payloads grant the
capability automatically. Existing environment configuration, old order rows,
and standard-domain behavior remain valid throughout rollout.

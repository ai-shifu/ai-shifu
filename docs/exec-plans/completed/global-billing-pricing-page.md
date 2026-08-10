# Global Billing Pricing Page

## Purpose / Big Picture

The global deployment needs an international SaaS pricing experience while the
China deployment keeps its existing billing page and checkout behavior. The
runtime `PAYMENT_CHANNELS_ENABLED` value is the deployment selector: a
Stripe-only deployment renders the new global pricing page, while every other
configuration fails closed to the existing domestic experience.

## Progress

- [x] 2026-08-10 13:20 CST: Confirmed the approved pricing, credit amounts,
      DeepSeek estimate copy, tracking contract, and coming-soon behavior.
- [x] 2026-08-10 13:25 CST: Inspected the billing route, catalog contract,
      runtime environment store, i18n files, and existing tests.
- [x] 2026-08-10 13:40 CST: Implemented the global pricing experience and route
      selection without changing the domestic checkout component.
- [x] 2026-08-10 13:42 CST: Added aligned English, Chinese, and French copy and
      regenerated i18n key types.
- [x] 2026-08-10 13:48 CST: Added focused selection, pricing, interaction, and
      no-checkout regression tests.
- [x] 2026-08-10 13:59 CST: Ran focused tests, lint, architecture checks, and
      visual verification.
- [x] 2026-08-10 16:03 CST: Aligned the final English copy and card density
      with the domestic comparison structure, clarified 12-month annual credit
      validity and permanent credit-pack rules, and removed preview-only
      routes before release.
- [x] 2026-08-10 19:30 CST: Adopted review feedback: the global pricing page
      now follows the active i18n language (copy and number formatting)
      instead of pinning `en-US`, and catalog currency values are normalized
      defensively so a missing currency fails closed instead of crashing.

## Surprises & Discoveries

- The product catalog is intentionally database-managed through
  `flask console billing upsert-product`; migrations do not seed paid SKUs.
- Billing-specific UI that imports admin route components belongs under the
  route-local `src/app/admin/billing/components/` directory.
- Existing catalog DTOs already expose all plan and credit-pack fields needed;
  no API schema change is required.
- The first production build used a stale local `markdown-flow-ui@0.1.126`
  installation even though `package.json` and `package-lock.json` require
  `0.2.8`. Running `npm ci` restored the locked dependency and the complete
  production build then passed.

## Decision Log

- Use `paymentChannels.length === 1 && paymentChannels[0] === "stripe"` after
  normalization as the global selector. Empty, mixed, and non-Stripe values
  render the domestic page.
- Keep the existing `BillingOverviewTab` completely unchanged and render a new
  global component only in the packages tab.
- Read price and credit values from `/api/billing/catalog`; recognize a fixed
  set of global product codes and reject incomplete or non-USD catalogs rather
  than displaying stale domestic products.
- Payment CTAs only track intent and open a coming-soon dialog. They never call
  any checkout endpoint.
- Annual-plan credits remain the authoritative per-cycle amounts; the page
  does not describe the small difference from twelve monthly allocations as
  bonus or extra credits.
- Annual-plan credits are valid for 12 months from grant. Credit-pack credits
  arrive immediately and never expire, but can be consumed only while an
  active subscription exists; unused pack credits remain in the account while
  a subscription is inactive.
- Preview-only catalog and page routes must not ship because they would shadow
  the real catalog request with hardcoded data.

## Outcomes & Retrospective

Implemented an isolated Stripe-only global pricing page with four responsive
plan cards, monthly/annual switching, two credit packs, DeepSeek estimates,
payment-intent tracking, and a non-transactional coming-soon dialog. The final
copy states 12-month annual validity and the permanent-but-subscription-gated
credit-pack rule. The existing domestic component and checkout paths were
unchanged. Learner-session estimates now derive from the same domestic
benchmark of 5-15 complete learner sessions per 100 credits, and validity is
shown only once in the shared footnote rather than repeated in every plan
card. All 50 focused billing and i18n tests passed, changed production files
passed lint, and architecture checks reported zero new violations. Final
responsive QA verified four columns at 1440px, two columns at 768px, and one
column at 375px with no horizontal overflow. Global payment CTAs expose at
least a 44px mobile touch target, and the coming-soon dialog keeps 16px side
clearance at 375px. All preview-only routes and mock catalog data were removed
after QA. After restoring the lockfile dependency set with `npm ci`, the full
Next.js production build, including lint and TypeScript validation, passed.

## Context and Orientation

`AdminBillingPageClient.tsx` owns packages/details tab composition.
`BillingOverviewTab.tsx` owns the current domestic catalog and checkout flows.
Runtime payment channels live in `useEnvStore`. The catalog response contains
`BillingPlan[]` and `BillingTopupProduct[]`. User-visible copy lives in the
three locale-specific `modules/billing.json` files.

## Plan of Work

Add a pure deployment-selector helper and a route-local global pricing
component. The component fetches the existing catalog, validates the expected
global products, renders responsive monthly/annual plan cards and credit-pack
cards, reports payment-intent clicks, and shows a non-transactional dialog.
Add locale-aligned copy and tests around selection, pricing, cycle switching,
tracking, error handling, and preserved domestic rendering.

## Concrete Steps

1. Add the Stripe-only selector and use it in `AdminBillingPageClient` only for
   the packages panel.
2. Add `GlobalBillingPricing` under the route-local billing components folder.
3. Add the global pricing namespace to every billing locale and regenerate
   `src/cook-web/src/types/i18n-keys.d.ts`.
4. Add component and page-level tests, then run the focused and frontend-wide
   checks.
5. Record final verification here and move this ExecPlan to `completed/`.

## Validation and Acceptance

- Stripe-only renders the global page; Ping++-only, mixed, missing, and unknown
  configurations render the existing domestic page.
- Annual is the default, Business has a compact recommendation badge, Studio
  can switch to monthly, and all approved USD amounts and DeepSeek estimates
  are present.
- Every plan or credit-pack CTA emits exactly one
  `creator_billing_checkout_click` event with the approved payload and opens
  the coming-soon dialog without calling checkout APIs.
- Incomplete or non-USD catalogs display an unavailable state and no payment
  CTA.
- Focused Jest tests, linting, architecture checks, responsive visual
  inspection, and the complete Next.js production build pass.

## Idempotence and Recovery

The frontend changes are additive and can be reverted independently. Catalog
provisioning is deployment-specific and uses idempotent upsert commands; old
global SKUs should be marked inactive rather than deleted. The domestic
database is never targeted.

## Interfaces and Dependencies

No public API or database schema changes. The implementation depends on the
existing runtime `paymentChannels`, `GET /billing/catalog`, `BillingPlan` and
`BillingTopupProduct` types, SWR, shared UI primitives, and `useTracking`.

The global deployment must provision these active USD products with the
existing `flask console billing upsert-product` command before release. Prices
are stored in cents.

| Product code                      | Kind / interval |  Price | Credits |
| --------------------------------- | --------------- | -----: | ------: |
| `creator-global-studio-monthly`   | plan / month    |   5900 |    1000 |
| `creator-global-growth-monthly`   | plan / month    |  22900 |    4000 |
| `creator-global-growth-yearly`    | plan / year     | 219900 |   50000 |
| `creator-global-business-monthly` | plan / month    |  41900 |    8000 |
| `creator-global-business-yearly`  | plan / year     | 399900 |  100000 |
| `creator-global-scale-monthly`    | plan / month    |  83900 |   18000 |
| `creator-global-scale-yearly`     | plan / year     | 799900 |  220000 |
| `creator-global-credits-250`      | topup / none    |   2900 |     250 |
| `creator-global-credits-3000`     | topup / none    |  27900 |    3000 |

Monthly and yearly plans use recurring billing, per-cycle allocation, interval
count 1, and auto-renew enabled. Credit packs use one-time billing, one-time
allocation, no interval, and auto-renew disabled. Old global SKUs should be
marked inactive after the new catalog has been read back. No command should be
run against the China deployment.

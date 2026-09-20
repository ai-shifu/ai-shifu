---
title: Billing learning-time estimates
status: completed
owner_surface: shared
last_reviewed: 2026-09-20
canonical: false
---

# Billing learning-time estimates

## Purpose / Big Picture

Help teachers compare credit plans by estimated cumulative learning time instead
of fixed learner counts. Ground the example in current billing code, production
usage and an explicitly named course. Keep the main comparison concise and place
the agreed concise assumptions and listening note in its footnote. Keep detailed
calibration evidence in the product specification.

## Progress

- [x] Fetched current main and verified China production revision `61bb7677f`;
  rebased implementation onto `b15e6e287` before publication.
- [x] Read current catalog, regional rates and bounded usage through read-only
  transactions; reviewed billing rounding, learning modes and content linkage.
- [x] Replaced fixed learner counts with catalog-based calculations and five
  aligned translations. Preserved the existing purchase actions and analytics.
- [x] Passed the initial 114 focused tests, full type check with the declared UI
  dependency, all pre-commit gates and desktop/mobile browser review.
- [x] Calibrated against the user's 2.5-hour completion duration for
  跟 AI 学 AI 通识. One fully traced reading completion cost 25.24 credits at 1×,
  giving 99.05 hours per 1,000 credits.
- [x] User selected approximately 100 hours per 1,000 credits with the named
  course, duration assumption and sample limitations stated explicitly.
- [x] User requested minimal information in the main comparison; all detailed
  assumptions now belong in footnotes below the pricing content.
- [x] Rechecked the deployed old page and current catalog: 1,000 credits formerly
  meant 5–15 listening completions, or 12.5–37.5 learning hours. The new reading
  example is higher. Audited storage, settlement and display with no unit error.
- [x] The hour-based revision passed 118 focused tests, full type checking against the
  declared UI package, and every repository pre-commit gate.
- [x] Verified the hour-based course-example revision at desktop and mobile widths,
  including the final plan after horizontal scrolling; prepared one focused PR.

- [x] User finalized the title 预估支持学习时长, consistent minute units,
  Chinese compact large numbers and one shared short footnote. Retained the
  existing capacity coefficient and all detailed calibration evidence.
- [x] Minute-display revision passed 122 focused tests, full type checking against
  the declared UI dependency and every repository pre-commit gate.

## Surprises & Discoveries

- Production allocations differ from old test fixtures; fixed SKU copy cannot
  describe live credits reliably.
- Progress timestamps do not measure active learning time. Counting prose omits
  thinking, exercises, visual study and review, so the first 10–30-hour draft did
  not fit the supplied complete-course duration. It was replaced before release.
- The strict reading sample covers all current visible lessons and all generated
  content. Historical completed samples support the magnitude but mostly lack
  learning-mode metadata, so they are not claimed as confirmed reading samples.
- Legacy block linkage and anonymous-account migration complicate historical
  audits. Stable progress IDs retain usage association across identity changes.
- Regional default speech providers have different rates; the China numeric
  voice example cannot be presented as a global default.
- Mobile review found six columns squeezed into the viewport. Preserve a
  minimum column width inside the existing horizontal scroller.

## Decision Log

- Use current per-request 1× repricing with separate input, cache and output
  rounding; never divide historical ledger charges by a displayed multiplier.
- Use the user's chosen named-course example: 2.5 assumed learning hours divided
  by 25.24 sample credits, approximately 100 hours per 1,000 credits. Do not
  present a single-course observation as a universal statistical range.
- Keep the main content to an estimated-learning-time label and approximate
  minute value. Keep the shared footnote to historical data, reference-only
  status, consumption variability and higher credit usage
  in listening mode. Keep course, sample and rate details in the product specification.
- Keep purchase actions and existing analytics unchanged: this replaces
  explanatory values and copy without adding an interaction path.
- Review confirmed that the existing capacity explanation is a presentation-only
  change under the analytics contract, not a new capability requiring exposure
  events. Existing checkout events do not prove conversion improvement.
- Accept valid global catalog allocation edits instead of comparing credits
  with fixed defaults. Keep the other purchase validation constraints intact.
- Reuse domestic pricing copy in Global, except plan names and purchase button
  labels. Show actual period prices and cumulative existing benefits. Use the
  original detailed domestic validity note after the user corrected the earlier
  simplification. Keep provider-managed validity copy separate because actual
  credit-bucket expiry differs for Stripe. Keep one shared, conditional campaign note:
  “优惠仅适用于本次支付。”; checkout retains the recurring billing terms.
- Keep identities, raw content, credentials and detailed business traffic totals
  out of the public repository. Retain the full aggregate audit locally.

## Outcomes & Retrospective

The initial implementation passed 114 focused tests and all repository gates.
Type checking used the declared `markdown-flow-ui@0.2.26` in an isolated temporary
package because the shared local installation held 0.2.21. Desktop and mobile
browser review verified the existing horizontal scroller.

The implementation uses the course-example coefficient chosen by the user;
purchase conversion impact remains unmeasured. The evidence and maintenance
contract live in `docs/product-specs/billing-learning-hours-estimate.md`.
Its hour-based revision passed 118 focused tests, type checking and all-file
pre-commit gates. Browser review of that revision confirmed concise main values, complete footnotes and no
page overflow at 1440-pixel desktop and 390-pixel mobile widths.
The later minute-display revision passed 122 focused tests, full type checking
and all-file pre-commit gates. It preserves the existing table structure and
replaces the longer footnotes with one shared paragraph.
A subsequent copy refinement removes the domestic audience scenario row, joins
Chinese compact magnitudes directly to 分钟, and describes listening as consuming
more credits without introducing a separate credit concept.
That refinement passed the same 122 focused tests and full type checking.
Readback of the local billing page confirmed the removed row, compact minute
spacing and revised footnote; a desktop screenshot confirmed the table layout.
Review follow-up removed the fixed global allocation check. The added regression
changes Growth Monthly from 4,000 to 5,000 credits, verifies 30,000 learning
minutes and the existing checkout path, and checks that the checkout event uses
the updated allocation. Invalid allocations remain rejected. All 127 focused
tests and full type checking passed after this fix.
The user subsequently removed the reading-mode and 1×-model parenthetical from
the public footnote; the calibration and internal evidence remain unchanged.
The global cards also omit their audience-description section, matching the
domestic comparison while preserving the learning estimate, benefits and
purchase controls.
The subsequent Global copy alignment reuses domestic translations and the
footnote component, shows full-period prices and cumulative benefits, and passes
128 focused tests plus full type checking. Browser readback confirmed the
shared short validity note on the domestic page.
Review follow-up restores the catalog loading announcement through a shared
localized status for both skeleton screens. Focused regressions verify that
the announcement is present only while the catalog is pending.

## Context and Orientation

Domestic plans are rendered by `BillingPlanComparisonTable.tsx`; global plans by
`GlobalBillingPricing.tsx`. Both receive catalog `credit_amount`. The shared
helper is `src/web/src/lib/billingLearningTime.ts`. Copy belongs in
`src/i18n/*/modules/billing.json`. Charging logic is in
`src/api/flaskr/service/billing/charges.py`.

## Plan of Work

Audit usage and billing semantics, calibrate the named-course completion,
implement both pricing surfaces with aligned copy, verify behavior and rendering,
then create one focused PR.

## Concrete Steps

Follow the read-only completion and usage contract in the product specification.
Run focused billing Jest suites, frontend type checking and lint. Regenerate i18n
keys and repository knowledge indexes. Run the dev-tool doctor and repository
pre-commit gate before committing.

## Validation and Acceptance

- Live 50-credit plans show approximately 300 minutes; 1,000 credits show 6,000.
  Chinese annual allocations show 30 万, 60 万 and 132 万 minutes.
  Catalog changes update estimates without SKU edits or annual multiplication.
- Only the learning-time label and approximate value appear in the comparison.
- One shared footnote states historical data, reference-only status and variable
  credit consumption; listening uses more credits. Reading-mode and 1×-model
  calibration assumptions remain in the internal product specification.
- Invalid allocations do not promise minutes; positive sub-minute values remain
  distinct from unavailable data. Locale formatting remains intact.
- Existing checkout behavior stays covered by billing regression suites.

## Idempotence and Recovery

No production configuration, rates or database rows are changed. Revert frontend,
translations and documentation together to restore the prior display. Recalibrate
when rates, course content, models or the completion assumption change.

## Interfaces and Dependencies

No API, database schema or runtime dependency changes. Catalog credit allocations
remain authoritative. The estimate is presentation-only and must never be used
for settlement, permissions or balance enforcement.

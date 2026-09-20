---
title: Billing learning-hour estimates
status: completed
owner_surface: shared
last_reviewed: 2026-09-20
canonical: false
---

# Billing learning-hour estimates

## Purpose / Big Picture

Help teachers compare credit plans by estimated cumulative learning time instead
of fixed learner counts. Ground the example in current billing code, production
usage and an explicitly named course. Keep the main comparison concise and place
all assumptions and listening differences in its footnotes.

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
- [x] Final revision passed 118 focused tests, full type checking against the
  declared UI package, and every repository pre-commit gate.
- [x] Verified the final course-example revision at desktop and mobile widths,
  including the final plan after horizontal scrolling; prepared one focused PR.

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
  number. Put the course name, reading mode, 1× model, cumulative-time definition,
  duration assumption, single-sample limitation and speech costs in footnotes.
- Keep purchase actions and existing analytics unchanged: this replaces
  explanatory values and copy without adding an interaction path.
- Keep identities, raw content, credentials and detailed business traffic totals
  out of the public repository. Retain the full aggregate audit locally.

## Outcomes & Retrospective

The initial implementation passed 114 focused tests and all repository gates.
Type checking used the declared `markdown-flow-ui@0.2.26` in an isolated temporary
package because the shared local installation held 0.2.21. Desktop and mobile
browser review verified the existing horizontal scroller.

The final implementation uses the course-example coefficient chosen by the user;
purchase conversion impact remains unmeasured. The evidence and maintenance
contract live in `docs/product-specs/billing-learning-hours-estimate.md`.
Its final 118 focused tests, type check and all-file pre-commit gate passed.
Final browser review confirmed concise main values, complete footnotes and no
page overflow at 1440-pixel desktop and 390-pixel mobile widths.

## Context and Orientation

Domestic plans are rendered by `BillingPlanComparisonTable.tsx`; global plans by
`GlobalBillingPricing.tsx`. Both receive catalog `credit_amount`. The shared
helper is `src/web/src/lib/billingLearningHours.ts`. Copy belongs in
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

- Live 50-credit plans show approximately 5 hours; 1,000 credits show 100 hours.
  Catalog changes update estimates without SKU edits or annual multiplication.
- Only the learning-time label and approximate value appear in the comparison.
- Footnotes name the course, 2.5-hour assumption, reading mode, 1× model,
  cumulative learner time and limited sample; listening is additional.
- Invalid allocations do not promise hours; positive sub-hour values remain
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

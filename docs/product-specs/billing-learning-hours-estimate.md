---
title: Billing learning-time estimates
status: implemented
owner_surface: shared
last_reviewed: 2026-09-20
canonical: true
---

# Billing learning-time estimates

## Product contract

Plan comparisons show **approximately 6,000 minutes of cumulative learning per
1,000 credits**, scaled from the catalog's `credit_amount`. This is the previously
calibrated 100-hour reference expressed in minutes, with no capacity increase.
The main comparison shows only the label **预估支持学习时长** and an approximate
minute value. Minutes remain the time unit for every plan; large Chinese numbers
use compact magnitudes such as 万. Both pricing surfaces omit the audience
scenario descriptions to keep the comparison concise.

Both pricing surfaces use this concise shared Chinese footnote, with aligned
translations in all five locales:

> 时长按历史数据估算，仅供参考。课程内容、所选模型和互动情况都会影响实际积分消耗，听课模式会消耗更多积分。

Global pricing reuses the domestic labels, credit amounts, cumulative benefit
wording, credit-pack notes and footnote component. Plan names and purchase button copy remain Global-specific. Validity
wording also reflects the actual payment-provider rules. Prices show the actual catalog
amount for the displayed monthly or annual period; annual plans no longer show
a monthly equivalent or savings copy. The existing Global benefit sets,
including priority support, remain unchanged.

The domestic validity note retains its original detailed wording, with aligned
translations: **积分有效期：月度套餐自获取之日起 30 天内有效（含当日）；年度套餐自获取之日起按自然年有效。两类均以到期日 23:59 为截止。**
Global currently retains **积分有效期以账户显示为准。** for its provider-managed
period. The actual credit-bucket expiry follows each payment provider's cycle;
changing display copy does not change the billing rules. Discounted
plans show the original and payable period prices; a shared note below the plans
states **优惠仅适用于本次支付。** only when a displayed plan has a campaign discount.
Stripe Checkout continues to show recurring payment terms and uses a one-time
campaign coupon. Ordinary annual pricing and bonus-credit campaigns do not
trigger this discount note.

The reading-mode, 1×-model assumptions remain in this specification rather than
the public footnote. The historical usage and assumed completion duration behind that copy remain
fully documented below. The short copy does not claim measured online time,
a broad statistical average or a guaranteed service entitlement.

The benchmark is the Chinese course **跟 AI 学 AI 通识** (Understanding AI with AI).
Its course owner supplied a typical completion duration of **2.5 hours**. One
fully traced reading-mode completion cost **25.24 credits** when repriced at
current 1× rates. This gives 99.05 hours per 1,000 credits, rounded to approximately
100 hours, or 6,000 minutes, for the purchase comparison. The user selected this
course-example basis on 2026-09-20, then approved minute-based display and a concise
footnote while retaining the calibration details in this specification.

Hours add up across learners: ten learners studying for one hour represent ten
cumulative hours. This is a single-course example, not measured online time,
a universal course estimate or a guaranteed entitlement. Different courses,
models and interactions change consumption. Course creation, preview, debugging
and other credit uses reduce the balance available for learner delivery.
Promotional bonuses are not included in the recurring allocation estimate.

The shared implementation is `src/web/src/lib/billingLearningTime.ts`, consumed
by the domestic and global plan comparisons. Settlement, eligibility, purchase
actions and checkout analytics remain unchanged. No new user interaction is
introduced. An increase in purchase conversion has not yet been established.

This replaces the existing capacity explanation, including the global page's
previous catalog-derived learner estimate. It adds no action, control, route,
workflow or state transition, so the presentation-only exception in
`docs/references/frontend-product-analytics.md` applies. Existing checkout
events are not an exposure denominator or proof of conversion improvement.

## Evidence and calculation

- China production data cutoff: **2026-09-20 11:00:00 UTC**, end exclusive.
- Deployed API at extraction: `61bb7677f`; implementation subsequently rebased
  onto `b15e6e287`.
- Sources: `shifu_log_published_structs`, `shifu_published_outline_items`,
  `learn_progress_records`, `learn_generated_blocks`, `bill_usage`,
  `credit_usage_rates` and `bill_products`.
- Queries ran in read-only transactions with statement timeouts. Learner
  identities, prompts, generated text and credentials are not published.

The strict reading example completed all **20 visible leaf lessons** in the
current published course structure. All **51 successful billable model calls**
explicitly recorded reading mode and matched the 51 generated content blocks.
There was no speech synthesis or identity mismatch in this example. Calls used
`qwen/deepseek-v4-flash-0731`, a route verified at current 1× rates. This is not a
claim that every current 1× route produces the same token counts.

The live reference is `LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS=0.066667`.
The example route's input, cached-input and output rates were each verified as
**0.000066667 credits/token**, billing unit 1 and credit precision 2. Equality
across these rates does not follow automatically from the 1× output label.
Reproduce `charges.py` and `primitives.py` for each request:

```text
credits = round_half_up(max(input - input_cache, 0) × rate, 2)
        + round_half_up(input_cache × rate, 2)
        + round_half_up(output × rate, 2)

sample_credits = sum(per_request_credits) = 25.24
sample_hours = 2.5  # Course-owner assumption, not measured learner activity.
hours_per_1000_credits = 1000 / 25.24 × 2.5 = 99.05
published_reference = approximately 6000 minutes per 1,000 credits
plan_minutes = catalog_credit_amount / 1000 × published_reference
```

Do not add cached tokens on top of total input, round only after summing all
requests, or divide historical charges by a displayed model multiplier.
Historical tokens repriced at current rates do not simulate a different model.

## Completion and coverage rules

1. Select the latest undeleted published structure for the named course.
   Resolve exact outline row IDs from its JSON tree. Recursively prune missing,
   deleted and hidden outlines, including their descendants. Leaves have no
   outline children; legacy block children do not make a lesson a chapter.
2. Include all visible leaf lessons, regardless of guest/trial/paid access type.
   Rank undeleted progress by `(user_bid, outline_item_bid)`, with
   `updated_at DESC, id DESC`. Select the latest record before requiring status
   603 for every leaf, matching the strict course credit-usage completion helper.
3. Join usage through those stable `progress_record_bid` values. Include all
   retained successful billable production request-level LLM calls across the
   full learning process, including follow-up questions. Do not restrict cost
   to a recent month if the learner started earlier. Exclude speech, preview
   and debugging charges from the reading benchmark.
4. Exclude learning processes that began before complete metering coverage.
   Require explicit `learning_mode=read` for the strict reading example and
   verify the generated content linkage. Do not silently treat missing modes
   or missing usage as free reading.

Legacy coverage needs separate interpretation. Metering began in February 2026,
normal teaching-block linkage was added in May, and learning-mode metadata was
added in August. Follow-up answers may have progress linkage without block
linkage. Anonymous-to-signed-in account migration preserves progress IDs but
updates their user IDs without updating old usage user IDs. Therefore a
current-user-only billing query can omit earlier costs, and a missing block ID
alone does not prove missing billing.

Historical completed-course aggregates support the order of magnitude but are
not described as verified reading-mode samples. Their full audit and exclusions
remain in the local task evidence rather than publishing business traffic totals
in this public repository.

## Why prose-only reading time was replaced

An earlier draft estimated 10–30 hours per 1,000 credits by counting cleaned
Chinese/English prose and assuming reading speeds. That estimates only the time
to read the extracted text. It omits studying diagrams, thinking, exercises,
interaction and review. It is not equivalent to the course owner's 2.5-hour
learning duration.

For 2.5 hours, the earlier range implied 83.33–250 credits per completion. The
fully traced example used 25.24, so that range did **not** fit the supplied course
benchmark. The coefficient uses the documented course example, not an unsupported
universal range derived from one completion. The purchase footnote describes
estimates based on historical data for reference only, variable credit
consumption and higher credit usage in listening mode. Reading mode, the 1×
model, sample size and assumed duration remain in this methodology document.

## Comparison with the previous page

The previous production page explicitly assumed listening mode and a complete
course of ten 15-minute lessons, or 2.5 hours per learner session. Its 1,000-credit
allocation showed 5–15 learner sessions, equivalent to 12.5–37.5 cumulative
learning hours. The new approximately 100-hour reading example is therefore
2.67–8 times that old estimate, not less. This compares presentation assumptions;
it is not a controlled measurement of the improvement from switching modes.

| Credits | Previous listening estimate in hours | New reading example in hours |
| --- | ---: | ---: |
| 1,000 | 12.5–37.5 | About 100 |
| 50,000 | 625–1,875 | About 5,000 |
| 100,000 | 1,250–3,750 | About 10,000 |
| 220,000 | 2,750–8,250 | About 22,000 |

The live credit allocations and deployed web revision `b15e6e287` were rechecked
against this comparison. Credit serialization and display do not introduce an
additional factor of 100 or 1,000. The old learner figures were fixed by product
code domestically; the global formula was 5–15 sessions per 1,000 credits.

## Listening comparison

Listening adds speech synthesis to model usage. Use successful billable
request-level (`record_level=0`) TTS records only: segment rows would double
count consumption. In China, the sampled default voice is Tencent `large-model`,
charged at **0.0021604975 credits per output character**.

For the bounded September 1–20 sample, current-rate synthesis cost divided by
generated audio duration was **40.35 credits/audio hour**, excluding model usage.
This is calibration evidence, not a fixed per-hour price promised in the UI.
Audio duration is not measured listening time, and different voices and speaking
speeds can differ substantially. Do not multiply the course's 2.5-hour
learning duration by 40 as though every minute were synthesized speech.

Both pages use the same concise, nonnumeric listening explanation. The US
installation defaults to Volcengine Seed TTS 2.0 at 0.0101852361 credits/output
character; the China default-voice example must not be presented as a global
voice price. Its Qwen DeepSeek V4/V4.1 Flash routes were separately verified to
use the same three 1× model rates, but the named course remains a China example.

A prior paired same-block comparison yielded 2.73 times the model-only cost after
adding speech. This is not a universal reading-to-listening time multiplier:
reading and speaking speeds, partial audio generation, course mix and replay
caching differ. Matching replay can reuse a learner's existing generated audio;
this does not mean audio is shared free across learners.

## Catalog examples and display

| China product | Credits per allocation | Chinese reference display |
| --- | ---: | ---: |
| Trial | 1,000 | 约 6,000 分钟 |
| Monthly | 50 | 约 300 分钟 |
| Monthly Pro | 1,000 | 约 6,000 分钟 |
| Annual Lite | 50,000 | 约 30 万分钟 |
| Annual | 100,000 | 约 60 万分钟 |
| Annual Premium | 220,000 | 约 132 万分钟 |

Below 10,000 minutes, use standard locale number grouping. At 10,000 or more,
use locale compact number formatting with up to two decimal places. Chinese
adds a space before the compact magnitude and joins that magnitude directly to
the minute unit (for example, `约 30 万分钟`); other locales use their customary
forms, such as `300K` or `1.32M`. Only the number magnitude
changes; the duration unit always remains minutes.

The UI always calculates from the live catalog, including custom or edited
allocations. It does not multiply annual grants by 12 again. Existing validity
and grant schedules still apply. Positive estimates below one minute display
“less than 1 minute”; zero or invalid allocations do not promise learning time.
The global catalog validator accepts changed positive, finite credit allocations
while preserving its product identity, type, currency, price and interval checks.

The domestic comparison retains at least 180 pixels per plan column inside its
existing horizontal scroller, so the minute value and purchase controls
remain readable on a phone.

## Maintenance and verification

Recalibrate when rates, course content, model routing or the assumed completion
duration changes. Collect more complete reading samples and courses before
claiming a universal typical range. Update the shared coefficient, all translated
assumptions and this source document together. Never change billing rates to
make the estimate match a marketing claim.

Focused frontend regressions cover catalog changes, allocation scaling,
sub-minute/invalid values, locale formatting, explanatory copy and unchanged
checkout behavior. Generated i18n keys and repository knowledge indexes must
remain current. Verify desktop and mobile rendering before publishing changes.

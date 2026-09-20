---
title: Billing reading learning-hour estimates
status: implemented
owner_surface: shared
last_reviewed: 2026-09-20
canonical: true
---

# Billing reading learning-hour estimates

## Product contract

Plan comparisons show **approximately 100 hours of cumulative learning per
1,000 credits**, scaled from the catalog's `credit_amount`. This replaces fixed
learner counts. The main comparison shows only the learning-time label and
approximate hour value. The footnotes identify the **AI literacy course reference,
reading mode and a 1× model**, the course name and all assumptions.

The benchmark is the Chinese course **跟 AI 学 AI 通识** (Understanding AI with AI).
Its course owner supplied a typical completion duration of **2.5 hours**. One
fully traced reading-mode completion cost **25.24 credits** when repriced at
current 1× rates. This gives 99.05 hours per 1,000 credits, rounded to approximately
100 for the purchase comparison. The user explicitly selected this course-example
basis on 2026-09-20 after reviewing the sample limitations.

Hours add up across learners: ten learners studying for one hour represent ten
cumulative hours. This is a single-course example, not measured online time,
a universal course estimate or a guaranteed entitlement. Different courses,
models and interactions change consumption. Course creation, preview, debugging
and other credit uses reduce the balance available for learner delivery.
Promotional bonuses are not included in the recurring allocation estimate.

The shared implementation is `src/web/src/lib/billingLearningHours.ts`, consumed
by the domestic and global plan comparisons. Settlement, eligibility, purchase
actions and checkout analytics remain unchanged. No new user interaction is
introduced. An increase in purchase conversion has not yet been established.

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
published_reference = approximately 100 hours per 1,000 credits
plan_hours = catalog_credit_amount / 1000 × published_reference
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
benchmark. The purchase page now uses the explicitly named example, not an
unsupported universal range derived from one completion. The underlying sample
size and assumed duration remain visible in the footnote in all five locales.

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
generated audio duration was **40.35 credits/audio hour**. The domestic page
rounds this to **about 40 additional credits per audio hour**, excluding model
usage. Audio duration is not measured listening time, and different voices and
speaking speeds can differ substantially. Do not multiply the course's 2.5-hour
learning duration by 40 as though every minute were synthesized speech.

The global page uses a separate nonnumeric listening explanation. The US
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

| China product | Credits per allocation | Reference learning hours |
| --- | ---: | ---: |
| Trial | 1,000 | About 100 |
| Monthly | 50 | About 5 |
| Monthly Pro | 1,000 | About 100 |
| Annual Lite | 50,000 | About 5,000 |
| Annual | 100,000 | About 10,000 |
| Annual Premium | 220,000 | About 22,000 |

The UI always calculates from the live catalog, including custom or edited
allocations. It does not multiply annual grants by 12 again. Existing validity
and grant schedules still apply. Positive estimates below one hour display
“less than 1 hour”; zero or invalid allocations do not promise learning time.

The domestic comparison retains at least 180 pixels per plan column inside its
existing horizontal scroller, so the hour value and purchase controls
remain readable on a phone.

## Maintenance and verification

Recalibrate when rates, course content, model routing or the assumed completion
duration changes. Collect more complete reading samples and courses before
claiming a universal typical range. Update the shared coefficient, all translated
assumptions and this source document together. Never change billing rates to
make the estimate match a marketing claim.

Focused frontend regressions cover catalog changes, allocation scaling,
sub-hour/invalid values, locale formatting, explanatory copy and unchanged
checkout behavior. Generated i18n keys and repository knowledge indexes must
remain current. Verify desktop and mobile rendering before publishing changes.

---
title: MarkdownFlow Cache Usage Observations
status: active
owner_surface: learner
last_reviewed: 2026-10-08
canonical: true
---

# MarkdownFlow Cache Usage Observations

Provider prefix caching and the session's semantic-summary cache are separate.
The shared gateway still owns provider routing, billing and traces. The agent
preserves optional numeric cache observations alongside its existing diagnostic
request/input/output counters; it does not calculate prices or change billing.

## Provider prefix cache

The shared stream usage DTO retains optional raw `input_cache` metadata from the
provider, including explicit zero; it does not turn missing metadata into zero.
The existing billing conversion stays unchanged. Gateway usage follows the shared extractor's object/dictionary conventions:
`input_cache`, or nested `input_tokens_details` / `prompt_tokens_details` with
`cached_tokens`. A cache observation requires explicit nonnegative integer input
and cached-token counts, with cached tokens no greater than input tokens. Booleans,
missing fields and invalid counts do not establish coverage. An explicit zero
is a valid report; absent metadata is unknown. Cumulative stream snapshots replace
the previous snapshot, rather than being added together as independent requests.

| Diagnostic field | Meaning |
| --- | --- |
| `cache_read_tokens` | Cached input tokens retained by the SDK, including native adapters without complete coverage metadata. |
| `cache_reported_requests` | Completed requests with valid explicit gateway cache metadata. This counts reporting coverage, not cache hits. |
| `cache_reported_input_tokens` | Input tokens from precisely those reporting requests. |
| `cache_reported_read_tokens` | Cached tokens from precisely those reporting requests. |

Only the last two fields form a matching observed-subset token-cache fraction,
and only when the denominator is positive. Do not divide all cached tokens by a
partial coverage denominator or treat unknown requests as zero-hit requests.
Missing optional fields retain the legacy three-counter session shape. A genuine
zero report includes coverage, so it remains distinguishable from missing data.
Native SDK cache counts can survive without establishing a coverage denominator.

Usage survives ordinary serialization/reload and mixed supported/unsupported
requests. It follows existing session/checkpoint and rewind semantics. It describes
completed SDK results; failed, cancelled or post-finish-limit paths may lack complete
diagnostic usage even when the shared gateway recorded billable work. It is not
a lifetime, monotonic spend ledger.

## Semantic-summary cache

The [quality evaluator](markdownflow-memory-quality.md) records `summary_usage`
separately from teaching `usage`, using the production summary factory's completed
model responses. Successful long-history cases require one logical attempt,
a real summary and an unchanged cache after session reload. Reusing that cache
must not create a second summary request. Explicit injected summary failure makes
no provider call and reports an empty `summary_usage` dictionary. A real invalid
summary may still have completed request usage; failures can also incur partial
gateway usage outside this observer.

Admission, teaching and summary observations retain provider-cache coverage when
available. Summary requests are separately billed/traced under
`agent_memory_quality_teaching_summary`; normal classroom summary generations use
`agent_teaching_summary`. No prompts, remembered facts or responses are added to
the numeric counters or private evaluation report.

## Complete-course testing

Normal classroom teaching (`agent_lesson`), semantic summaries
(`agent_teaching_summary`) and memory admission (`agent_memory_admission`) share
the authenticated course and lesson usage context. The ledger retains the learner
identity and read/listen/classroom mode, while existing ownership resolution identifies the
course owner. Draft preview stays in the preview usage scene. Synthetic evaluator
requests have no classroom identity and are not a course-fee baseline.

Collect the private fixed-catalog report and correlate the selected course/lesson's
shared gateway accounting and traces, including teaching, admission/checker,
summary and failed requests. Keep unknown provider usage separate and record the
model/settings/runtime fingerprints. Compare real cache observations across
repeated sessions and changed memory rather than assuming a stable prefix implies
a provider cache hit. Use actual ledger prices and charges for lesson cost.
Small synthetic cases and one session round trip do not establish long-term cache
savings, complete teaching quality or human acceptance.

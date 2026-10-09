---
title: MarkdownFlow Memory Quality Evaluation
status: active
owner_surface: learner
last_reviewed: 2026-10-09
canonical: true
---

# MarkdownFlow Memory Quality Evaluation

The opt-in evaluator at `src/api/scripts/evaluate_mdf2_memory.py` supplies a
repeatable synthetic baseline for the current course model. Its twenty-six fixed
cases cover fourteen semantic admission decisions, six actual-engine recall
turns, four long-teaching-history journeys and two exercise-statistics reports.
This is model behavior evidence alongside existing deterministic storage
and host-isolation regressions; it does not replace human teaching-quality
acceptance, persisted cross-lesson acceptance or long-term cost observation.

## Cases and scoring

Admission calls the product's `make_request_check`, including its actual prompt,
structured decision and request limits. Positive cases cover explicit English,
Chinese and French requests and faithful exact-code storage. Negative cases cover
ordinary preferences, quoted examples, negation, forgetting, questions,
conditional requests, invented additional traits and policy-bypass instructions.
A provider error, absent response or invalid structured decision is an evaluation
error, never a passing negative case. Each case gets a fresh admission checker.

Recall runs the real engine with a 100-character initial memory budget to omit
long values. It checks exact recall, a current value superseding stale history,
a deleted value remaining unavailable despite a historical tool return, and an
oversized value returning `too_large` without a partial answer. Each case gets a
fresh synthetic session. Two additional changed/deleted cases include an answered
named question and a serialized session round trip. These synthetic reloads do not
replace storage-backed host tests. Passing requires a current recall tool result, exactly
one expected answer after a paired exact-key read, no conflicting relevant reads,
no stale or invented project code, finished teaching,
unchanged memory and preserved original history. An unpaused content-only turn
with visible non-whitespace content gets at most one host-style continuation to finish; all earlier output and failures
remain scored, so this is not an answer retry. A plausible answer without a
current tool read fails.

The lesson asks the project question without telling the model to call recall or
warning it about stale history; the runtime policy must supply that behavior.
The fixture deliberately uses stable machine-readable project codes. These checks
evaluate fact fidelity and tool use, not natural teaching style or a complete
language benchmark. The synthetic snapshots are already authorized inputs; they
do not independently prove the host's database authorization or course isolation.
Those remain covered by the real storage tests in `test_memory_*_integration.py`
and `tests/service/profile/`.

## Long-history cases

Four teaching cases combine an eligible older long assistant message, two recent
turns, the production semantic-summary factory, a JSON session round trip and
actual engine projection. They distinguish changed/deleted current learner memory
from a precise question about an original classroom example. The exact code is
inside the source, outside both excerpt edges. Historical answers require a paired
current-turn original page containing that code before learner output; a plausible
answer or current memory read alone fails. Current-fact answers retain the exact
recall-evidence requirement.

Three cases require a real, nonempty bounded semantic summary. A fourth explicitly
injects a summary failure to exercise cached excerpt fallback; it is not evidence
of an actual provider outage. Each case records one logical summary attempt and
requires the same derivative cache after serialization/reload, no additional
summary attempt, and the expected source-bound excerpt/summary in actual model
requests. Missing real summaries are evaluation errors even if an answer is correct.
All cases require unchanged memory, original history and finished teaching.

Teaching uses the same controlled 512-token/temperature-zero settings as recall.
Summary generation uses the production prompt and 256-token settings, with an
eight-second provider timeout/cooperative deadline and complete 40 KiB input
budget. These settings are reported separately. Teaching `usage` and completed
summary `summary_usage` are separate. Logical summary attempts remain counts,
including explicitly injected failure; actual summary generations are billed/traced
under `agent_memory_quality_teaching_summary`. They are not a cost ledger.
See [cache usage observations](markdownflow-cache-usage.md) for valid provider
coverage, unknown metadata, matching token denominators and complete-course testing.
Synthetic round trips establish cache/tool behavior, not database authorization,
complete natural teaching quality or long-term cache savings.

## Exercise-statistics cases

Two synthetic English cases resume eleven arithmetic questions after original
paired submissions, feedback and continue-button clicks. Three questions needed
one correction each. The cases place those corrections on different questions
while retaining identical totals; correct aggregate counts cannot hide swapped
first-pass results. The session is serialized and reloaded before the actual
engine produces its final report. No expected rows or totals are sent to the model.

The author requests one JSON object (plain or in a single Markdown JSON fence)
containing per-question first-result booleans,
attempt and hint counts, plus aggregate counts. Scoring rejects missing/duplicate
questions, duplicate JSON keys, invalid scalar types, wrong per-question assignments and inconsistent
totals. It also requires actual completion, unchanged memory and preserved original
history. A successful finish with wrong statistics remains a semantic failure.
Invalid report formatting fails checks; provider/engine errors remain evaluation
errors. The report stores checks and usage, never raw model output or attempts.

These controlled cases use temperature zero and a 2,048-token cap, separately
reported as `exercise_generation_settings`; other families retain their settings.
They use the existing 15-second gateway timeout/deadline and six-request limit,
with at most one host-style completion turn. They are evidence checks, not a
natural-course grading benchmark or deterministic enforcement of model output.
A natural-course report already contradicted preserved original attempts even
though its author required a matching ledger. This extension does not repair that
failure, add a grading ledger or broaden memory admission. Retain that failure
separately even if these simpler cases pass.

## Running

From `src/api` in the backend environment:

```bash
python scripts/evaluate_mdf2_memory.py --list
python scripts/evaluate_mdf2_memory.py --live \
  --course COURSE_BID --lesson ACCESSIBLE_LESSON_BID \
  --learner DEDICATED_TEMPORARY_LEARNER_BID \
  --repeat 3 --output /tmp/mdf2-memory-quality.json
```

Use an environment already enabled for 2.0 and an accessible published lesson.
The evaluator refuses a 1.0 deployment and resolves the model through the same
course-selection/access path as teaching. It supplies only synthetic inputs and
never loads real learner memory or calls the session/profile persistence path.
Existing shared-gateway usage, billing and tracing still occur, attributed to the
provided dedicated learner under `agent_memory_quality_admission`,
`agent_memory_quality_recall`, `agent_memory_quality_teaching`,
`agent_memory_quality_exercise` and the separate
`agent_memory_quality_teaching_summary` generation. The evaluator does not modify the engine switch.

`--case ID` may be repeated to diagnose selected cases; `--repeat` accepts 1–5,
defaulting to one. Recall deliberately uses controlled temperature 0 and a
512-token cap, recorded as recall_generation_settings, rather than the course
temperature and unbounded teaching output. The admission judge uses its actual
product settings. These are bounded fact/tool checks, not an identical-settings
production teaching benchmark. A subset report has `full_catalog=false` even when every selected
case passes. Each admission case has the product judge's one-request limit. Recall has
a six-request limit per turn and at most two turns including automatic completion. Gateway requests use a 15-second provider timeout and cooperative deadline
with SDK retries disabled; this is not a hard wall-clock deadline for an entire
case. The fixed suite runs sequentially to bound concurrent provider load.

The private, atomically written JSON report records denominators, repetitions,
per-case assertions, errors, UTC start/end times, elapsed times, usage where
available, course selection and resolved model, optional checkout source commit and hashes of the evaluator, fixture, judge prompt and runtime.
It contains no credentials, learner IDs, raw requests, responses or provider errors.
Usage is the judge/engine's diagnostic counters where available, with completed
summary responses reported separately. Optional cache coverage distinguishes a
valid reported zero from unknown metadata. These counters are not a billing or
cost ledger; use shared-gateway accounting/traces for those acceptance decisions.
The runtime image need not include Git: file fingerprints remain available.
A failed case remains in the report; it is never silently removed or converted
into a successful retry. Exit codes: 0 for a complete passing selected run,
1 for semantic/assertion failures, 2 for invocation/provider/response errors.

For a complete baseline, use the complete catalog with three repetitions and
retain the initial report. Diagnose failures with a separate selected-case report;
compare source fingerprints before combining evidence from different versions.

## Current evidence rule

With memory recall enabled, the system rule and tool description both require
current verification of learner saved facts, preferences and project details,
even without the word "remember". A learner question about a remembered fact requires
an exact current-turn read even when earlier teaching contains an answer. Earlier
recall results and the first memory block are historical evidence. A current
`unavailable` or `too_large` result must not be replaced by the historical value.
For prior exact-key reads, the engine also compares their latest results with
the current authorized snapshot. Changed, removed, excluded or compacted facts
receive a revalidation notice in current instructions and, when a current prompt
exists, beside that prompt in an explicitly marked host memory context. It names
at most 20 whole keys within 1,024 JSON characters; no values are copied into the
notice. A fresh matching read clears the dynamic instruction notice. Accepted
learner input and current-turn write authorization remain verbatim and exclude
host context. Original stored messages remain unchanged.
This addresses updates and deletions without rewriting stored teaching history
or changing the host's authorized snapshot.
Current-memory revalidation is scoped to current-fact questions. An explicit
question about what appeared in earlier teaching uses original historical evidence;
today's memory must not replace an earlier quote or example. Exact historical
codes, equations, quotations and decisions require `read_teaching` when projected,
even if a lossy overview appears to contain the answer. Historical reads neither
restore deleted memory nor authorize writes.
It requests a relevant read for memory questions, not an exhaustive memory scan.
This is model guidance, not deterministic output enforcement. Retain intermittent
violations as failed quality evidence; a passing run cannot erase an earlier failure.

## Release boundary

A passing suite does not complete the entire memory milestone or authorize a
production switch. System-registered profile fields remain global; ordinary course
variables, named answers and explicit remembered notes remain course-local. No
custom cross-course sharing is restored by this evaluator. Historical data and
engine 1.0 remain until their separate acceptance and retirement conditions hold.

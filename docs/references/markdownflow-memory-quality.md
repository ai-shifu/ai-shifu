---
title: MarkdownFlow Memory Quality Evaluation
status: active
owner_surface: learner
last_reviewed: 2026-10-10
canonical: true
---

# MarkdownFlow Memory Quality Evaluation

The opt-in evaluator at `src/api/scripts/evaluate_mdf2_memory.py` supplies a
repeatable synthetic baseline for the current course model. Its twenty-eight fixed
cases cover fourteen semantic admission decisions, six actual-engine recall
turns, four long-teaching-history journeys and four exercise-statistics reports.
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
Fixture responses stay below the teaching-excerpt threshold and no semantic
summarizer is configured. These are intentionally full-history statistics cases,
matching the observed natural failure's absence of teaching summaries. Enabling
the projection option does not establish that projection happened. The four
separate long-history cases cover summary/read behavior.

Two additional exercise cases place one older correction and hint in the middle
of an eligible long teaching part, outside both excerpt edges. One requires a
real production-factory semantic summary; the other explicitly injects a failure
and requires cached excerpt fallback, not a real provider-outage claim. Both warm
the derivative cache, serialize/reload the session, and observe source-bound
markers in actual engine requests. A projection flag alone is insufficient.
They require one summary attempt, no additional summary after reload, unchanged
original history and the same strict original-read/calculation/report checks.
A missing or invalid required summary is an evaluation error even when the final
statistics are correct. Summary usage remains separate from exercise usage.
These are selected synthetic statistics-after-compaction checks, not evidence
of a complete natural long-course or long-term fee acceptance.

The author requests one JSON object (plain or in a single Markdown JSON fence)
containing per-question first-result booleans,
attempt and hint counts, plus aggregate counts. Scoring rejects missing/duplicate
questions, duplicate JSON keys, invalid scalar types, wrong per-question assignments and inconsistent
totals. The evaluator now enables the product exercise tools and requires complete
original-evidence pages plus an evidence-correct calculation before any report
text. A correct report that skips those tools fails protocol acceptance. Calculator
labels may be the fixture numeric ID, exact original question prompt or exact
original teaching title; every reference must still belong to that same original
question. Wrong titles or swapping equally graded answers between questions fail.
It also requires actual completion, unchanged memory and preserved original
history. A successful finish with wrong statistics remains a semantic failure.
Invalid report formatting fails checks; provider/engine errors remain evaluation
errors. The report stores checks and usage, never raw model output or attempts.

These controlled cases use temperature zero and a 2,048-token cap, separately
reported as `exercise_generation_settings`; other families retain their settings.
They use the existing 15-second gateway timeout/deadline and twelve-request limit,
with at most one host-style completion turn. They are evidence checks, not a
natural-course grading benchmark or deterministic enforcement of model output.
The product now offers session-local original submission reads and a calculator
that validates exhaustive, unique references and chronological attempts. Counts
come from question rows, not model arithmetic. Following teaching stops at the
next user/continue or accepted-answer boundary and before the next interaction
call. It remains exact context, not an extracted grade; a combined text part may
also introduce the following interaction. Shared answer-group markers identify
simultaneously answered questions. No language heuristic splits that original text.
Known zero total hints establishes zero hints before the first answer. Semantic
grades, question grouping
and hint identification remain model judgments. Unknown hint counts remain null.
No profile or course memory is written, and no persistent grading ledger is added.
The synthetic scorer accepts only exact fixture IDs, prompts, teaching titles or
short arithmetic titles; it still independently checks each answer's original
question membership. Calculation diagnostics are fixed status enums, without
raw tool arguments, output or exception details.
Results are bounded to 8 KiB of UTF-8 JSON; over 200 accepted submissions, ambiguous
pairing or oversized reports are refused explicitly. The existing overall input
budget still applies; per-result bounds do not bound cumulative history.
Portable Engine hosts retain the old tool set unless they opt in. The AI-Shifu
lesson entry enables it for classroom and preview in read and listen modes.

The retained natural eleven-question failure was replayed without persistence.
The original runtime passed 0/3; an earlier reader-only prototype passed 1/3.
The first calculator prompt was skipped (1/3 final reports correct); a stronger
protocol then exposed the diagnostic six-request cap (two errors). With the
product twelve-request limit and final candidate, fresh replays passed 3/3 with
complete source reads, correct calculation, matching final rows/totals, no engine
errors and no memory writes. These are original-history replays, not three new
classroom journeys, independent human tests, or deterministic grading guarantees.
The evaluator initially rejected exact original prompt/title labels; their
normalization plus reference grouping rescores six unchanged captured outputs
6/6, with a subsequent fresh final-source selected CLI run passing 2/2. Earlier
failing reports remain retained privately, not relabeled as new passing runs.
The additional compacted exercise cases now cover summary success and injected
failure/cache fallback with selected synthetic evidence. Natural-course
statistics after semantic-summary compaction, other models/languages and
independent human acceptance remain separate items. Full-catalog repetitions on
the current course model are recorded below; they do not close those other items.

## Complete current-model baseline: October 10, 2026

The unchanged twenty-eight-case catalog passed three complete repetitions
(**84/84**, zero evaluation errors) on `ark/deepseek-v4-1-flash-260910`, from
01:24:00Z to 01:29:59Z. The evaluator and fixtures came from merged revision
`6bbae6ecc`, including the original-message/part binding added in `d7cf9ba6b`.
All twenty-eight report fingerprints match that checkout. Both ready sim API
replicas (`sim-6002c01`) match the twenty-five runtime fingerprints. Contributor
scripts ran from an isolated temporary directory, importing the unchanged
installed runtime; no candidate prompt or engine overrides were used.

| Case family | Fixed cases | Repetitions | Passing results |
| --- | --- | --- | --- |
| Semantic admission | 14 | 3 | 42/42 |
| Current-memory recall | 6 | 3 | 18/18 |
| Long teaching history | 4 | 3 | 12/12 |
| Exercise statistics | 4 | 3 | 12/12 |
| Total | 28 | 3 | 84/84 |

There were eighteen logical summary attempts: twelve completed provider requests
and six explicitly injected failures that make no summary-provider request.
Summary and excerpt evidence, serialized cache reuse, exact original reads and
per-question statistics passed the existing checks in each relevant repetition.
The observer rejects known references copied into later responses or wrong parts;
its eight offline position cases include four demonstrated pre-fix failures.

Read-only reconciliation found 252 actual gateway rows: 42 admission, 75 recall,
61 teaching, 62 exercise and 12 summary requests. Diagnostic request counts agree
with that ledger count, but the ledger independently establishes billing. Every
row is attributed to the dedicated learner, validated course/lesson and resolved
owner; no classroom progress/block IDs were fabricated. There are zero failed
rows or unsettled billable successes. Settled cost is **135.19 credits**, separate
from earlier natural-classroom and selected-case runs. This is one complete
synthetic evaluation cost, not a per-lesson price or long-term savings estimate.

The initial report, observational diagnostics and ledger evidence are retained
privately, with no real memory or classroom-session persistence. The isolated
remote directory was removed after evidence was copied and verified. This result
does not replace natural-course statistics after compaction, storage-backed
journeys, real Bot/knowledge-base/Workflow acceptance, other models/languages,
human teaching-quality feedback or long-term cost observation. Earlier failures
remain historical evidence; this passing run does not relabel them.

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
provided dedicated learner, validated course and published lesson under
`agent_memory_quality_admission`,
`agent_memory_quality_recall`, `agent_memory_quality_teaching`,
`agent_memory_quality_exercise` and the separate
`agent_memory_quality_teaching_summary` generation. Shared settlement resolves
that course's owner; normal billability and built-in-demo exemptions still apply.
Generation names distinguish these synthetic costs from natural classroom costs.
No classroom progress/block IDs or learning mode are fabricated. Earlier rows
created before course attribution was added remain unchanged; do not infer their
course from a learner ID alone. The evaluator does not modify the engine switch.

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

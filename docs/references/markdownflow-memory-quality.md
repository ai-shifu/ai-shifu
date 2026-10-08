---
title: MarkdownFlow Memory Quality Evaluation
status: active
owner_surface: learner
last_reviewed: 2026-10-08
canonical: true
---

# MarkdownFlow Memory Quality Evaluation

The opt-in evaluator at `src/api/scripts/evaluate_mdf2_memory.py` supplies a
repeatable synthetic baseline for the current course model. Its eighteen fixed
cases cover fourteen semantic admission decisions and four actual-engine recall
turns. This is model behavior evidence alongside existing deterministic storage
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
fresh synthetic session. Passing requires a current recall tool result, exactly
one expected answer, no stale or invented project code, finished teaching,
unchanged memory and preserved original history. An unpaused content-only turn
gets at most one host-style continuation to finish; all earlier output and failures
remain scored, so this is not an answer retry. A plausible answer without a
current tool read fails.

The fixture deliberately uses stable machine-readable project codes. These checks
evaluate fact fidelity and tool use, not natural teaching style or a complete
language benchmark. The synthetic snapshots are already authorized inputs; they
do not independently prove the host's database authorization or course isolation.
Those remain covered by the real storage tests in `test_memory_*_integration.py`
and `tests/service/profile/`.

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
provided dedicated learner under `agent_memory_quality_admission` or
`agent_memory_quality_recall`. The evaluator does not modify the engine switch.

`--case ID` may be repeated to diagnose selected cases; `--repeat` accepts 1–5,
defaulting to one. A subset report has `full_catalog=false` even when every selected
case passes. Each admission case has the product judge's one-request limit. Recall has
a six-request limit per turn and at most two turns including automatic completion. Gateway requests use a 15-second provider timeout and cooperative deadline
with SDK retries disabled; this is not a hard wall-clock deadline for an entire
case. The fixed suite runs sequentially to bound concurrent provider load.

The private, atomically written JSON report records denominators, repetitions,
per-case assertions, errors, UTC start/end times, elapsed times, usage where
available, course selection and resolved model, optional checkout source commit and hashes of the evaluator, fixture, judge prompt and runtime.
It contains no credentials, learner IDs, raw requests, responses or provider errors.
Usage is the judge/engine's diagnostic counters where available, not a billing or
cost ledger; use shared-gateway accounting/traces for those acceptance decisions.
The runtime image need not include Git: file fingerprints remain available.
A failed case remains in the report; it is never silently removed or converted
into a successful retry. Exit codes: 0 for a complete passing selected run,
1 for semantic/assertion failures, 2 for invocation/provider/response errors.

For tomorrow's test baseline, use the complete catalog with three repetitions and
retain the initial report. Diagnose failures with a separate selected-case report;
compare source fingerprints before combining evidence from different versions.

## Current evidence rule

With memory recall enabled, a learner question about a remembered fact requires
an exact current-turn read even when earlier teaching contains an answer. Earlier
recall results and the first memory block are historical evidence. A current
`unavailable` or `too_large` result must not be replaced by the historical value.
This addresses real-model baseline failures for updates and deletions without
rewriting stored teaching history or changing the host's authorized snapshot.
It adds a relevant read for memory questions, not an exhaustive memory scan.

## Release boundary

A passing suite does not complete the entire memory milestone or authorize a
production switch. System-registered profile fields remain global; ordinary course
variables, named answers and explicit remembered notes remain course-local. No
custom cross-course sharing is restored by this evaluator. Historical data and
engine 1.0 remain until their separate acceptance and retirement conditions hold.

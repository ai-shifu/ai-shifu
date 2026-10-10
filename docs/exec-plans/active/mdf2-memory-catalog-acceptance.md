# Validate the full memory catalog on the current course model

## Purpose / Big Picture

Earlier selected live checks validate individual memory and exercise changes,
but do not establish that all twenty-eight current cases still pass together.
Run the unchanged complete catalog three times on the current sim course model,
retain every result and reconcile all five gateway generation families. This
measures synthetic model behavior; natural courses, other models/languages,
real external providers, human teaching quality and long-term fees remain
separate acceptance requirements.

## Progress

- [x] 2026-10-10T01:24:48Z: Confirmed #3075 merged as 6bbae6ecc, final CI passed,
  and all independent opinions have original-thread replies. Archived its focused
  [compaction plan](../completed/mdf2-compacted-exercise-quality.md).
- [x] 2026-10-10T01:24:48Z: Both sim-6002c01 API replicas match all twenty-five
  runtime fingerprints used by the current evaluator. Staged evaluator scripts
  only in an isolated temporary directory; application files remain untouched.
- [x] 2026-10-10T01:31:22Z: Completed all eighty-four results: 84/84 pass,
  zero evaluation errors and all twenty-eight source fingerprints match 6bbae6ecc.
- [x] 2026-10-10T01:31:22Z: Reconciled all 252 gateway rows across five generation
  families, complete attribution, zero failures/unsettled successes and 135.19
  settled credits. Copied/verified private evidence before remote cleanup.
- [ ] 2026-10-10T01:31:22Z: Publish the documentation PR and inspect its CI/AI
  review before archiving this acceptance record.

## Surprises & Discoveries

The sim image intentionally omits contributor evaluation scripts. Copy only the
current scripts into a private temporary directory and import the unchanged
installed runtime through a symlink. Check actual runtime files on both replicas
before sending billed requests.

## Decision Log

- Use the existing opt-in evaluator, product admission checker, actual engine,
  course model selection and shared gateway. Do not add a second semantic judge.
- Keep synthetic sessions in memory and reuse the dedicated internal learner.
  Do not load or persist real memory or classroom sessions.
- Record all eighty-four results and all five generation families, including
  separately completed summaries and explicitly injected summary failures.
- Do not replace earlier failing evidence or infer natural teaching quality,
  other-model stability or long-term savings from a fixed synthetic catalog.

## Outcomes & Retrospective

The full current-model catalog passed 84/84 across three repetitions, with zero
evaluation errors. All twenty-eight report fingerprints match merged 6bbae6ecc;
both sim replicas match twenty-five runtime files. Eighteen logical summary
attempts comprise twelve completed provider requests and six injected failures.
All 252 actual gateway rows have complete attribution, zero failures and no
unsettled billable successes; cost is 135.19 credits. These synthetic results
close the expanded current-model catalog check only, not the memory/follow-up
milestones or natural/human acceptance. Evidence was preserved before cleanup. No classroom runtime, storage schema,
production configuration or 1.0 behavior changes are planned for this scope.

## Context and Orientation

The canonical evaluator contract is
[MarkdownFlow memory quality](../../references/markdownflow-memory-quality.md).
The CLI is `src/api/scripts/evaluate_mdf2_memory.py`; its catalog and exercise
runner are in `scripts/mdf2_memory_quality/`. Fourteen admission cases, six recall
cases, four long-teaching cases and four exercise cases make twenty-eight.
The previous [compaction plan](../completed/mdf2-compacted-exercise-quality.md)
records the selected two-case live baseline and positional-observer correction.

## Plan of Work

Verify source identity, run the unchanged catalog with `--repeat 3`, retain its
private report and observational diagnostics, inspect every failure, and query
the usage ledger read-only. Publish only counts, stable failure categories,
source revisions and acceptance limitations. Fix a demonstrated product defect
only with a focused regression and fresh validation.

## Concrete Steps

Run the opt-in CLI on an environment already enabled for 2.0 using its validated
published course, lesson and dedicated learner. Use no candidate prompt or
engine override. Compare the report's twenty-eight file hashes with the checked
out candidate. Scope read-only ledger queries by baseline ID, learner and the
five evaluation generation names. Preserve private evidence before removing
only the unique temporary evaluation directory. Run repository gates and publish
one focused PR; merging remains manual.

## Validation and Acceptance

Require eighty-four unique results covering all cases and repetitions, explicit
errors rather than passing refusals on provider failures, current exact recall
following updates/deletions, original teaching/exercise evidence, cache reuse,
correct report rows/totals and unchanged synthetic history/memory. Reconcile
course/lesson/owner attribution, absence of fabricated classroom IDs, failures
and unsettled billable successes. A failure stays a failure even if a later run
passes. No unit-test or selected-case result may be called full-catalog live
acceptance.

## Idempotence and Recovery

Do not blindly retry a paid run. Keep partial logs and reports on interruption;
settle and reconcile incurred requests before deciding a targeted follow-up.
Private files stay untracked with restrictive permissions. Cleanup deletes only
the named temporary evaluation directory, after copying evidence locally.

## Interfaces and Dependencies

Reuse the deployed runtime, existing model gateway and usage ledger. No new
endpoints, dependencies, analytics events, memory scopes or deployments.

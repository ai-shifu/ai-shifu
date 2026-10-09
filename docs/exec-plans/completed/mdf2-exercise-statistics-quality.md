# Evaluate exercise statistics against original attempts

## Purpose / Big Picture

A natural eleven-question sim lesson completed successfully but its final report
assigned an early corrected answer to the first-pass group and an unrelated
first-pass answer to the corrected group. The totals looked plausible while the
per-question table contradicted them. Add repeatable synthetic evidence checks
to the existing opt-in quality evaluator. This PR does not claim to repair the
model's natural-course report or authorize new learner memory.

## Progress

- [x] 2026-10-09T10:28:28Z: Preserved the private natural-course failure and
  confirmed original attempts and feedback survive in the stored session;
  no teaching summaries were generated in that lesson.
- [x] 2026-10-09T10:36:30Z: Added two synthetic resumed eleven-question cases,
  strict row/aggregate scoring and separately reported generation settings.
- [x] 2026-10-09T10:36:30Z: Focused offline tests pass (82). Disabling row evidence
  makes the swapped-question regression fail; restored the check afterward.
- [x] 2026-10-09T10:36:30Z: Retained the initial six format failures and a separate
  diagnostic showing a valid JSON Markdown fence. Added exact whole-output fence
  normalization without relaxing row checks. A new selected live run passes 6/6
  (two cases, three repetitions) on sim's ark/deepseek-v4-1-flash-260910.
- [x] 2026-10-09T10:42:56Z: Developer-tool check and full repository pre-commit
  gates pass. Published [PR #3068](https://github.com/ai-shifu/ai-shifu/pull/3068)
  with b9e79f33d; all live-report source fingerprints match that checkout.
- [x] 2026-10-09T12:40:00Z: Independent findings were replied to in their original
  discussions, final technical CI passed and #3068 merged as 4066bae4c. Archive
  this evaluator implementation; natural runtime repair continues in
  [the calculation plan](mdf2-exercise-statistics-calculation.md).

## Surprises & Discoveries

Complete history and a successful completion event do not establish accurate
final statistics. The author already requested a per-question ledger and matching
totals. Repeating that instruction is not a demonstrated runtime fix.
The classroom model wraps JSON in Markdown fences even when asked for one object.
An exact whole-output fence is harmless formatting; surrounding narrative,
multiple objects, duplicate keys and incorrect rows still fail.

## Decision Log

- Use synthetic English arithmetic records, never publish private course output.
- Compare every question and aggregate to independently built attempt evidence.
- Exercise the actual engine and serialized session reload, not a standalone
  mocked summary parser. FunctionModel tests validate the scorer, not model quality.
- Keep runtime prompts, memory admission, database schema and engine 1.0 unchanged.
- Keep natural-course failure, synthetic baseline, human feedback and external
  provider quality as separate evidence.
- Keep these statistics cases full-history: no eligible excerpts and no semantic
  summarizer. The observed natural failure also had no teaching summaries.
  Combined statistics-after-summary quality is a separate acceptance item, not
  implied by enabling the projection option or the existing long-history cases.

## Outcomes & Retrospective

The new scorer accepts correct original-evidence reports and rejects swapped
identities even when totals match. All 82 focused tests pass, including a mutation
check that fails with row scoring disabled. The selected synthetic live run passes
6/6 after Markdown normalization. The original six format failures and separate
diagnostic are retained privately, not overwritten or relabeled as passes.
A passing synthetic run cannot erase the observed natural-course failure.
That unresolved natural-course grading issue remains tracked by the workspace
current MDF status and natural-course acceptance record; this plan closes only
the repeatable evaluation extension. Repository gates passed and PR #3068 is
published. Final technical CI passed and all independent review opinions were replied to
in their original discussions before #3068 merged. Final CodeRabbit incremental
review was rate-limited, not substantive acceptance. Natural runtime repair and
its acceptance continue in the calculation plan, not this archived evaluator plan.

## Context and Orientation

The existing CLI is `src/api/scripts/evaluate_mdf2_memory.py`; its catalog is
`scripts/mdf2_memory_quality/cases.json`. The exercise fixture and scorer live in
`scripts/mdf2_memory_quality/exercise.py`. Shared offline evaluator tests live in
`tests/scripts/test_evaluate_mdf2_memory.py`; dedicated exercise scorer tests live in
`tests/scripts/test_mdf2_exercise_quality.py`. The workspace current MDF plan tracks
natural-course acceptance and the unresolved production-quality issue separately.

## Plan of Work

Add a statistics family with different corrected-question placements but equal
aggregate counts. Feed original paired interactions and feedback through a
serialized engine session. Require one JSON report, exact row identities and
types, evidence-matching per-question counts, derived totals, preserved history,
unchanged memory and actual completion.

## Concrete Steps

1. Implement the fixture and scorer beside the existing evaluation catalog.
2. Wire family selection, generation settings and source fingerprints into CLI.
3. Test correct, swapped, inconsistent, missing, duplicate and invalid reports.
4. Run the selected live cases only with a dedicated temporary learner and the
   existing gateway; retain every result without retrying away a failure.
5. Regenerate knowledge indexes, run developer tools and full pre-commit gates,
   commit using repository defaults, and open a GitHub main PR without merging.

## Validation and Acceptance

Offline tests prove plausible totals and a finish event cannot hide wrong rows,
invalid types, duplicate rows or errors. Live reports distinguish semantic failure
from provider/format errors and include source fingerprints and separate settings.
Reports contain no raw answers, prompts, learner identifiers or credentials.
This does not establish natural-course grading correctness or fix its failure.

## Idempotence and Recovery

Synthetic evaluation never persists sessions or profiles. Live gateway billing
still applies to the dedicated learner; do not run against existing learners.
Revert this PR to remove the evaluation extension only. Preserve private evidence
outside version control. No deployment, schema recovery or data reset is needed.

## Interfaces and Dependencies

Reuse Engine, Session, the shared GatewayModel, existing opt-in CLI and private
atomic report writer. No new learner endpoint, dependency, event or memory scope.

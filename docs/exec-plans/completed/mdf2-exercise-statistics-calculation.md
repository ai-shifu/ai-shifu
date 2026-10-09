# Calculate exercise statistics from original submissions

## Purpose / Big Picture

A retained natural eleven-question course reports contradictory per-question and
aggregate statistics despite preserving all original answers. Supply read-only
original evidence and arithmetic computed from evidence-bound model judgments.
Semantic grading remains a model responsibility, subject to independent evaluation.

## Progress

- [x] 2026-10-09T12:30:00Z: Confirmed #3070 merged and preserved natural baseline
  (0/3 correct) and read-only evidence prototype (1/3 correct). Neither is a fix.
- [x] 2026-10-09T12:40:00Z: Implemented bounded evidence reads, complete unique
  reference validation and arithmetic from chronological judgments. Unknown hint
  counts remain null; portable hosts keep the existing tools by default.
- [x] 2026-10-09T12:40:00Z: Learning/evaluator regression passes (3,006 plus four
  subtests, one expected skip); entry contracts pass (59). Changing first outcome
  to the latest correction makes the original-evidence regression fail. Final
  candidate natural-history replays pass 3/3 with original pages and calculations.
- [x] 2026-10-09T12:51:00Z: Final-source natural replays pass 3/3. Exact fixture
  prompt/teaching-title normalization preserves strict reference grouping. Six
  unchanged captured diagnostic outputs rescore 6/6; a new final CLI run passes
  both selected cases (2/2). Its eight requests are correctly scoped and settled;
  source fingerprints match the checkout. Earlier failing reports remain retained.
- [x] 2026-10-09T13:00:00Z: Published #3071 and deployed the first candidate to
  sim (`5940d7ad5`); main remains unmerged.
- [x] 2026-10-09T13:12:00Z: Addressed review boundaries and known-zero hints,
  restored the documented six-request recall limit, and added five engine cases.
  The learning/evaluator suite passes 3,011 cases plus four subtests, one skip;
  all 540 engine tests pass. Removing either boundary or zero-hint normalization
  makes its regression fail. Reviewed-source natural replays pass 3/3.
- [x] 2026-10-09T13:16:00Z: Captured a fresh synthetic failure: correct calculations
  used exact shortened arithmetic titles rejected by the fixture scorer. Added
  only those exact fixture labels (Q and Question prefixes) and a wrong-expression rejection; strict original
  reference grouping stays required. The two unchanged captured runs rescore 2/2;
  33 scorer regressions pass. A subsequent fresh selected CLI run passes 2/2; all
  28 source fingerprints match and eight correctly scoped requests settle. Reports expose only a diagnostic status enum.
- [x] 2026-10-09T13:29:00Z: Pushed review fix `31fd0d3cc`, replied to all four
  original inline findings and the linked docstring advisory, and verified sim
  integration `0f7aeeb09`. Its combined regression passes 3,034 cases plus four
  subtests, one skip. Both Ready API replicas match 53 runtime file hashes and
  each passes all 540 engine tests using isolated SQLite/FunctionModel. New
  example-learner HTTP and actual usage/block attribution pass.
- [x] 2026-10-09T13:29:00Z: The final functional head has all technical checks green.
  An initial unrelated live-startup test received another app's background call;
  five isolated local checks pass and the failed CI job passes on its first rerun.
  The original failure remains retained. Main remains open and unmerged.

## Surprises & Discoveries

The natural failure has no truncated teaching or semantic summaries. An evidence
reader alone improved rows but left contradictory totals in two of three replays.
The authored script already requests consistent counts, so repeating it is not proof.
The first calculator policy was skipped. Moving an explicit required protocol to
the end of composed instructions produced actual tool calls; the diagnostic
six-request limit then refused two runs after four source pages and calculation.
Use the unchanged product twelve-request limit for this multi-step workflow.
The new evaluator initially rejected original prompt/title labels despite correct
calculations. Normalize only the fixture ID, exact prompt and exact teaching title;
also validate each submitted reference belongs to its claimed original question.
Do not relax grades, counts, final JSON IDs or duplicate checks. Post-review
synthetic runs exposed a further exact arithmetic-title form (`Q1: 1 + 1`).
Retain both failed reports and the captured events; normalization also rejects
wrong expressions and still matches each answer reference to its original prompt.
Following teaching can mix feedback with a next-question introduction in one
original text part. Preserve that text and identify the following interaction
and simultaneous answer group instead of heuristically splitting semantic grades.

## Decision Log

- Derive evidence from original session messages; no new persistent ledger or
  variable, schema migration, cross-course scope, or permission to remember notes.
- Default portable hosts retain their existing tool contract.
- Validate unique, exhaustive references and chronological submissions. Preserve
  unverified and unanswered states; do not infer grades with language regexes.
- Bound complete UTF-8 JSON tool results. Keep full stored history unchanged.
- Keep 1.0 code and fallback intact; retirement remains inventory only.
- Stop following teaching at a new user/accepted-answer boundary or before a new
  interaction call, preserving exact earlier parts and intervening tool exchanges.
- Zero total hints proves zero hints before the first attempt; otherwise omitted
  hint counts remain unknown. Recall keeps six requests; exercise uses twelve.

## Outcomes & Retrospective

Reference coverage, exact page bounds, reload/deferred answers and arithmetic
regressions pass. The original natural-history final rows and totals now match
in three fresh replays using the real course model. Earlier skipped-tool and
request-cap failures remain retained. Reviewed-source natural replay passes 3/3 and the final selected synthetic CLI
passes 2/2 with all 28 source fingerprints matching. Sim runs the reviewed code,
including its separate Workflow increment, and all functional-head technical
checks pass. This closes the scoped evidence/calculation implementation. Human,
other-model/language, semantic-summary and long-term cost acceptance remain in
`docs/references/markdownflow-memory-quality.md` and the project acceptance queue.
The final archival commit changes documentation only; its CI is separate. No deterministic semantic-grading guarantee.

## Context and Orientation

Engine construction is in `engine/engine.py`; original messages survive request
projections and serialized Session reload. `lesson_entry.py` owns product wiring.
`engine/exercise_statistics.py` owns evidence extraction and arithmetic. The
synthetic quality evaluator and strict scorer are in
`scripts/mdf2_memory_quality/exercise.py`. Private natural history stays outside Git.

## Plan of Work

Add optional read-only tools, test evidence identity and exact JSON byte bounds,
then replay the retained failure with the actual gateway. Wire the product and
quality evaluator only if the candidate improves independently scored reports.

## Concrete Steps

1. Add evidence extraction from original paired interactions and current-run suffix.
2. Validate complete reference coverage and derive every aggregate from rows.
3. Test deferred resume, reload, rewind, malformed pairing and unknown references.
4. Run fresh live replays with scoped usage and preserve every failure.
5. Run developer tools and full pre-commit gates, open a main PR, then validate sim.

## Validation and Acceptance

Every engine FunctionModel test must pass. Evidence reads preserve original answers
and feedback even under teaching projection, Unicode and escaping. Invalid or
incomplete references never yield successful totals. Unknown grades stay unknown.
Natural replay scoring compares every row and aggregate to independently retained
original evidence; a completion event alone is insufficient. Tools cannot promise
the model will copy their result or grade correctly; measure final output too.

## Idempotence and Recovery

Tools are read-only and session-local. Rewind and reload derive evidence anew.
Revert the optional wiring to restore the previous tool set. Never reset shared
courses, persist replay sessions, change production configuration or delete 1.0.

## Interfaces and Dependencies

Reuse pydantic-ai tools, original typed messages and Engine Deps. Gateway usage
must retain learner/course/lesson attribution, separately named diagnostic
requests and existing settlement. No new package, endpoint or SSE event.

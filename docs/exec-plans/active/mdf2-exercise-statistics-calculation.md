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
  33 scorer regressions pass. Reports expose only a diagnostic status enum.
- [ ] 2026-10-09T13:16:00Z: Push review fixes, reply in every original discussion,
  verify the updated sim image and record final-head CI without merging main.

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
request-cap failures remain retained. Reviewed-source natural replay passes 3/3. The initial feature CI passed all
technical checks and sim has the initial image. Review-fix publication, original
thread replies, updated-image acceptance and final-head CI remain pending. No deterministic semantic-grading guarantee.

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

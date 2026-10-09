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
- [ ] 2026-10-09T12:30:00Z: Enable only after evidence supports the candidate, run
  repository gates, publish a focused PR and verify sim without merging main.

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
Do not relax grades, counts, final JSON IDs or duplicate checks.

## Decision Log

- Derive evidence from original session messages; no new persistent ledger or
  variable, schema migration, cross-course scope, or permission to remember notes.
- Default portable hosts retain their existing tool contract.
- Validate unique, exhaustive references and chronological submissions. Preserve
  unverified and unanswered states; do not infer grades with language regexes.
- Bound complete UTF-8 JSON tool results. Keep full stored history unchanged.
- Keep 1.0 code and fallback intact; retirement remains inventory only.

## Outcomes & Retrospective

Reference coverage, exact page bounds, reload/deferred answers and arithmetic
regressions pass. The original natural-history final rows and totals now match
in three fresh replays using the real course model. Earlier skipped-tool and
request-cap failures remain retained. Final-source natural replay and selected synthetic protocol checks pass. CI and
sim acceptance remain pending. No deterministic semantic-grading guarantee.

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

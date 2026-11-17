---
title: Local Interaction Criteria and Review
status: completed
owner_surface: backend
last_reviewed: 2026-11-17
canonical: false
---

# Local Interaction Criteria and Review

## Purpose / Big Picture

Developers can run distinct learner paths and see which criterion each engine
step met. A reviewer can inspect the exact question, teaching prose, and judge
decisions when semantic evaluation needs a human judgment.

## Progress

- [x] 2026-11-17 22:27 UTC: Curated 27 cases and verified smoke and full replay.
- [x] 2026-11-17 22:36 UTC: Added per-step criteria, aggregate counts, and review evidence to terminal and JSON output.
- [x] 2026-11-17 22:38 UTC: Verified the replays, ambiguous and conflicting scripted judgments, and all 3,409 MarkdownFlow and evaluator tests.

## Surprises & Discoveries

The previous report lists failed assertions. It cannot tell which other
assertions passed or which later steps were blocked by the failure. It also
skips the visible-question judge after a mechanical assertion fails.

## Decision Log

- 2026-11-18. Keep deterministic checks tied to the fixture and count their
  outcomes per assertion. Mark unreachable checks as unevaluated.
- 2026-11-18. Let the semantic judge abstain. Offer a second judge for live
  comparisons and surface disagreements with source evidence for review.

## Outcomes & Retrospective

The catalog covers control selection, free input, sequential teaching,
clarifications, revisions, and historical parser and tool recoveries.
All 27 replays matched their expectations, including two reproduced failures.
All 12 smoke cases matched their expectations. The scripted live tests
verified that a failed control and a disputed prose judgment both appear in
the results for the same step.

## Context and Orientation

The [interaction evaluator guide](../../../src/api/scripts/README.md#evaluate_mdf_interactionspy)
describes the CLI. The [coverage inventory](../../../src/api/scripts/mdf_interactions/README.md)
maps cases to learner paths and replay regressions.

## Plan of Work

Make the existing assertions produce explicit results. Add a semantic
abstention and optional judge comparison. Derive the case status and review
queue from these checks while preserving the learner path and existing fail
codes.

## Concrete Steps

1. Record and aggregate criterion decisions, including blocked steps.
2. Report uncertain or conflicting semantic judgments with their evidence.
3. Verify replay, configured judge routing, and report compatibility.

## Validation and Acceptance

Run the full and smoke replays and the evaluator pytest suite. Confirm that
uncertain or conflicting verdicts cannot count as passed, and that a mechanical
control failure can coexist with a passed prose check.

## Idempotence and Recovery

Each run uses a fresh session. Review items identify the case, repeat, step,
and criterion. Run the same case again to reproduce a decision or generate a
new baseline after switching report versions.

## Interfaces and Dependencies

The evaluator still uses the pinned backend engine and optional configured
provider models. The report version changes with the criteria format.

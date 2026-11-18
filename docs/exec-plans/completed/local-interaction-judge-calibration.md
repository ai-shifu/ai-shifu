---
title: Calibrate Local Interaction Judgments
status: completed
owner_surface: backend
last_reviewed: 2026-11-18
canonical: false
---

# Calibrate Local Interaction Judgments

## Purpose / Big Picture

Automatic results should agree with the reviewed learner experience when prose
conveys the same instructional step, asks through a direct instruction, or
asks the learner to answer an identifiable question shown in the previous step.
An instruction to answer a different question should still fail.

## Progress

- [x] 2026-11-18 12:01 UTC: Matched all four human judgments to recorded prose, controls, and fixture expectations.
- [x] 2026-11-18 12:13 UTC: Implemented the semantic checks and exposed their evidence in the review page.
- [x] 2026-11-18 12:23 UTC: Regraded the saved outputs with both live judges and passed the 47 local regression tests.

## Surprises & Discoveries

The storage instruction failed because exact text matching rejected equivalent
wording. The question judge received only one turn, so it could not resolve an
explicit reference to the original question after the learner asked for a date
format. Another response asked the learner to compare shapes instead of
explaining bending resistance. Its repeated control does not make the prose
question equivalent.

## Decision Log

- 2026-11-18. Use an opt-in semantic requirement for instructional meaning.
  Keep literal assertions for exact tokens and recorded replay text.
- 2026-11-18. Supply the previous visible question only when the same question
  and controls were shown in consecutive steps. Require the current prose to
  invite the learner to answer, and reject a different requested answer.

## Outcomes & Retrospective

Both live judges matched all four human decisions in the saved outputs. Across
57 prose judgments, the three intended corrections were the only verdict
changes. Five negative controls failed under both judges, including a reversed
instruction and a reference with no previous question. The evaluator and review
page expose the new meaning check and any previous question used in a decision.
A version 5 report from before fixture snapshots was rendered with its original
catalog.

## Context and Orientation

The [evaluator guide](../../../src/api/scripts/README.md#evaluate_mdf_interactionspy)
defines live and offline evaluation. The [catalog guide](../../../src/api/scripts/mdf_interactions/README.md)
describes the fixture and replay assertion types.

## Plan of Work

Reuse the existing bounded judge requests, verdict aggregation, and review
workflow. Extend the question judgment input with verified learner context and
add a meaning judgment for an authored instruction. Preserve evidence and
status for both checks in the JSON report and review page.

## Concrete Steps

1. Add the prose rubrics, the optional previous question, and the fixture check.
2. Connect the checks to criterion totals, review items, and the browser view.
3. Validate the recorded human decisions and guard cases with the real judges.

## Validation and Acceptance

The reviewed storage instruction, location choice, and return to the original
label question pass using both configured judges. The change of question in the
folded-sheet exercise fails under both judges. Test missing or changed context,
reversed instructions, literal replay checks, and the semantic review queue.

## Idempotence and Recovery

Saved reports and human annotations are the starting evidence. Repeat judgment
on the same prose to verify the new rubric. Disagreements still surface for
review with the precise input and both explanations.

## Interfaces and Dependencies

The evaluator uses the existing configured model gateway and bounded Pydantic AI
judges. The review generator still opens earlier version 5 reports. Updated judge
instructions and fixture fingerprints identify judgments under the new criteria.

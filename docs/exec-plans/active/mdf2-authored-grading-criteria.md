# Keep grading within authored answer criteria

## Purpose / Big Picture

Stop adding pass conditions absent from the current question's authored rubric,
while continuing to reject missing, contradictory or learner-redefined answers.
The preceding natural classroom required a peripheral-device point despite an
answer covering all five authored digital-computer characteristics. Preserve that
failure and its original grades; reporting fidelity does not prove grading fidelity.

## Progress

- [x] 2026-10-10: Verify #3095 merged as 186184dc8 and read the complete saved
  lesson, original answer and teacher feedback. The next question has different
  requirements; the cause of the observed drift is not proven to be compression.
- [x] 2026-10-10: Add runtime answer-criteria guidance and six opt-in synthetic
  cases with observable advance/retry checks through serialized engine sessions.
- [x] 2026-10-10: Local learning/script checks pass 3,254 tests and 50 subtests
  with three expected skips; developer-tool and all-files repository gates pass.
- [x] 2026-10-10: Both AI evaluator findings reproduce before correction;
  658 focused engine/quality checks pass and both original threads have replies.
- [x] 2026-10-10: Sim ca8e6ee2e matches all 54 runtime/resource hashes on two
  ready API replicas. Six real-model cases produce five passes and one failure:
  the teacher notices missing program control but supplies it and advances.
  Preserve all twelve actual requests (7.49 settled credits) and the failed report.
  Progress, sessions, variables and all 72 retained element rows remain identical. Trace listing times
  out; direct reads of the observed trace ID recover all twelve generations.
- [x] 2026-10-10: Clarify that teacher-supplied hints cannot replace an authored
  required learner correction; an SDK policy-delivery assertion fails first.
- [ ] 2026-10-10: Verify offline checks, real selected cases and a non-persisting
  replay of the actual pre-answer checkpoint on the corrected sim runtime.
- [ ] 2026-10-10: Publish a focused PR, deploy sim, document evidence and reply
  to each AI opinion. Leave human and fresh complete-course acceptance open.

## Surprises & Discoveries

AI review identifies two evaluator blind spots: the advancing fixture already
supplied optional digital codes, and bare internal question labels could count
as delivery. Both reproduce as failing offline checks. Add a minimal complete
answer without optional facts, retain a separate optional-addition control and
require full question prompts instead of labels before any paid candidate run.

The original answer satisfies program control, speed, precision, storage and
generality; optional digital-code details do not require another point. Peripheral
devices were absent from that question's required list. Hardware multithreading
is explicitly required by a later question and must not be relaxed. Neither
finding authorizes rewriting the failed classroom or its historical counts.

## Decision Log

- Extend the existing opt-in quality runner rather than create another gateway
  or persistence path. Keep all prompts and fixture answers synthetic and English.
- Keep author requirements authoritative, including applicable global rules;
  forbid learners and teacher hints from inventing or removing pass conditions.
- Treat prompt guidance as probabilistic. Offline doubles verify wiring/scoring;
  actual model outcomes supply bounded semantic evidence, never a guarantee.
- Retain all MarkdownFlow 1.0 code; retirement remains inventory only.

## Outcomes & Retrospective

Implementation is under validation. The prior natural failure is retained. Full
natural-course acceptance, human feedback and other providers/languages remain
open in the memory-quality reference and workspace status document.

## Context and Orientation

The vendored engine loads `engine/prompts/system.md` on construction and composes
instructions for each turn. `scripts/evaluate_mdf2_memory.py` routes selected
cases through the course gateway; `mdf2_memory_quality/grading.py` adds observable
question-boundary scoring without storing sessions or profiles.

## Plan of Work

Clarify answer criteria without extracting a language-specific rubric schema.
Add positive and negative controls, verify resumed sessions see the new policy,
then compare the corrected runtime against the private original checkpoint.
Keep evidence of every candidate failure and do not retry unchanged paid inputs.

## Concrete Steps

Use conda ai-shifu, run the engine and quality-runner tests, regenerate knowledge
indexes and run repository developer-tool/all-files gates before committing.
Push GitHub origin and open a PR for manual merge. Deploy the same correction to
sim, verify both replicas' source hashes and run selected cases with the existing
internal learner/course billing context. Keep private evidence at 700/600 modes.

## Validation and Acceptance

Require complete paraphrases to advance and missing/contradictory answers to
retry; a learner override must fail and an author's additional requirement must
remain required. Preserve original history/memory. The actual saved answer must
advance without requiring peripheral devices, without database/session writes,
errors or fabricated billing identifiers. Retain billed request attribution and
state exactly which checks are synthetic, replays or fresh classroom journeys.

## Idempotence and Recovery

Never overwrite failed evidence, reset learners or modify historical grades.
Sim and China production share a database. Use only read-only checkpoint queries;
replay in memory and use unique private artifacts. Revert the focused sim commit
if the candidate fails; do not edit production pods or widen budgets to obtain a pass.

## Interfaces and Dependencies

No migration, dependency upgrade, new gateway or public API change. The fixed
catalog gains a grading family; report fingerprints/settings and reference docs
change together. Existing session, interaction, billing and tracing contracts stay.

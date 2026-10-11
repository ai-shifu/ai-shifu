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
- [x] 2026-10-10: On sim 4c99a1f6d, five corrected-runtime controls pass;
  the learner-override case stops before answer submission because setup emits
  question text without interact. Preserve that incomplete six-case batch.
- [x] 2026-10-10: Add the host's single content-only setup continuation with
  failing-first tests, then run only the previously unsubmitted override case.
  It retries correctly. Six grading controls are covered across those runs,
  not a claim that one complete six-case batch passed. All 661 focused checks pass.
- [x] 2026-10-10: Restore the real turn-6, twelve-message checkpoint in memory
  and submit its exact original answer. It accepts the five authored points and
  advances to question 1-6 without an added peripheral requirement. One teaching
  and one summary request occur; original prefix and memory stay unchanged.
- [x] 2026-10-10: All 27 actual requests, including the two retained unsuccessful
  batches, settle for 17.29 credits with real course/lesson/owner attribution and
  no fabricated classroom IDs. Progress, sessions, variables and all 72 retained
  element rows remain identical to the read-only baseline.
- [x] 2026-10-11: Finish #3096 checks/review and final sim evaluator sync.
  Final source 9aead7c61 passes technical CI; both original AI findings and the
  separate review observations have original-thread replies. The user manually
  merges #3096 as ebccd9037.
- [x] 2026-10-11: Complete a separate new natural classroom after the subsequent
  interaction and report corrections (#3097 and #3098). All eleven authored
  questions, genuine corrections and the minimal five-point answer behave
  correctly; exact report counts and retained history pass. All 35 real requests
  settle 54.21 credits. The completed fresh-classroom plan records the full
  evidence and limitations; earlier failed classrooms and batches remain failed.

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

The original answer passes the corrected saved-checkpoint replay, and six
semantic controls are covered across a five-pass batch and the selected
previously unsubmitted case after correcting host-style setup continuation.
Neither unsuccessful aggregate batch is relabeled as passing. The original
natural failure and 17.29 credits of complete request evidence are retained. Full
broader course acceptance, human feedback and other providers/languages remain
open in the memory-quality reference and workspace status document. A separate
fresh eleven-question lesson now passes after #3098, with faithful question
order, authored criteria, learner corrections and final statistics; see
[the completed classroom plan](mdf2-fresh-grading-classroom.md). The two focused
plans are complete, while naturally compressed full lessons and wider coverage
remain open. No historical failure or grade is rewritten.

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

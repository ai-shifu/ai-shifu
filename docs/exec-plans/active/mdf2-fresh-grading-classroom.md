# Fresh classroom after authored grading corrections

## Purpose / Big Picture

Exercise a fresh eleven-question natural lesson through the learner HTTP path
after #3096. Saved-checkpoint replays and synthetic controls do not establish
that question delivery, grading, clarification, correction and the final report
work together in a new classroom. Keep all failed evidence and all legacy code.

## Progress

- [x] 2026-10-11: Confirm #3096 merged as ebccd9037. Sim already serves the
  corrected runtime; check both replicas against merged source before learning.
- [ ] 2026-10-11: Start a new internal test learner and complete the existing
  published eleven-question lesson without resetting or replaying its session.
- [x] 2026-10-11: The first fresh HTTP request fails before any answer: text-only
  `<interact ... />` is repeated across three turns and the repeat heuristic
  marks the lesson finished. Preserve all three settled requests (3.42 credits)
  with real progress/block attribution; no learner reset or historical repair.
- [x] 2026-10-11: Four SDK regressions fail before correction. Add bounded output
  validation, hide only standalone unexecuted tags and refuse finish while the
  question has not been created. All 591 engine checks and 3,277 learning/script
  checks plus 50 subtests pass, with three expected skips.
- [x] 2026-10-11: Reproduce and fix intervening-tool loss and custom-element
  false positives from AI review. Reconstruct the unfinished guard from saved
  history, stopping at an actual answered interaction. A separate saved-history
  regression fails before correction, and completion after a real answer remains
  allowed. Final learning/script checks pass 3,283 tests and 50 subtests with
  three expected skips; developer-tool/all-files gates pass.
- [ ] 2026-10-11: Review question order, authored answer criteria, clarification
  handling, retries and final report against actual learner-visible responses.
- [ ] 2026-10-11: Verify persisted history, real compression when present,
  request attribution and settled billing with read-only evidence.
- [ ] 2026-10-11: If a defect is found, reproduce it, implement one focused fix,
  validate locally and on sim, and open a PR for manual merge. Otherwise record
  the bounded acceptance without inventing unrelated code changes.

## Surprises & Discoveries

Production still serves the preceding UI release when this run starts. Sim's
existing deployment contains the merged grading correction, so identical runtime
code does not require another deployment or paid replay before a fresh lesson.

The first question is emitted as a self-closing XML-like text tag, although the
author wrote MarkdownFlow notation and never used that tag. The next two host
continuations repeat it without a tool call. The lesson is persistently finished
at turn three, with no pending interaction or submitted answer. Repetition is
not evidence of completion when the model never created the question.

## Decision Log

- Use the existing temporary-learner and learner HTTP/SSE path on sim, where
  billing and persistence are real. No payment, SMS, course edits or learner reset.
- This is one complete natural lesson, not a claim that every lesson in the
  course, every model or human acceptance has passed.
- Use the unchanged authored script and runtime limits. Never alter answers,
  historical grades or thresholds retrospectively to obtain passing evidence.
- Fix the observed missing-tool boundary in this PR. Do not parse XML attributes
  into tool calls or memories. A failed correction raises an error under the
  SDK's existing output-retry limit instead of reaching repeat-based completion.
- Recognition is limited to complete single-line standalone `<interact ...>`
  tags outside fenced/indented code, with exact authored literals preserved.
  Inline or multiline imitations are not covered by this correction.
- Carry remaining human, provider/language and long-term acceptance in the
  workspace status and memory-quality reference; 1.0 retirement is inventory only.

## Outcomes & Retrospective

The fresh classroom is retained as failed at the first question. Prior failed
classrooms remain failed; #3096's saved-answer replay does not replace them.
Candidate deployment and bounded actual-model validation remain pending.

## Context and Orientation

`agent/lesson_entry.py` orchestrates HTTP teaching turns; `run_agent.py` persists
session and learner-visible elements. The vendored engine's `system.md` supplies
authored grading guidance. Exercise history and statistics tools supply original
answers and computed totals for the final report. Private workspace helpers use
the existing HTTP interface and a read-only database account for verification.

## Plan of Work

Verify deployed runtime, start a new learner and inspect each response before
choosing the next answer. Include intentionally incorrect answers and knowledge
questions, then correct according to the actual authored criteria. Compare all
final report rows to actual inputs and feedback. Diagnose the first concrete
failure and keep any fix narrowly scoped.

## Concrete Steps

Use conda ai-shifu locally. Store raw prompts, identities, tokens, sessions,
traces and billing only in the private dated workspace evidence directory with
700/600 permissions. For changes, run focused failing-first tests, appropriate
engine/service checks, developer-tool checks and the all-files repository gate.
Push only GitHub origin. Deploy validated changes to sim and open a PR; do not
merge it automatically. Reply to every AI opinion in its original discussion.

## Validation and Acceptance

Observe all eleven authored questions in order, valid input controls, faithful
grading and retry boundaries, clarification excluded from answer counts and a
consistent final report with normal completion. Confirm retained HTTP content
matches persisted history, usage belongs to actual progress/blocks and settled
charges match the course owner. Report compression only when actual trace input
contains a summary bound to an original over-threshold teaching message.

## Idempotence and Recovery

Use unique evidence files, never overwrite failures or repeat an unchanged paid
probe to seek a pass. Sim and China production share storage. Database evidence
is read-only; normal test learning is the only intended persistence. Preserve
all existing learners, original sessions and unrelated local work.

## Interfaces and Dependencies

No planned dependency upgrade, schema migration, production configuration or
public API change. Determine any corrective interface changes only from observed
evidence and update all affected consumers together if necessary.

# Current course answers after a persisted lesson reload

## Purpose / Big Picture

Verify that an answer collected in one lesson does not hide a newer committed
course value when that lesson resumes. Exercise the actual host, profile rows,
session reload and exact recall together. Preserve historical conversation and
session-only working notes. This is the next focused persisted-memory acceptance
step after PR #3051, not completion of milestone 4 or authorization to remove 1.0.

## Progress

- [x] 2026-10-08 20:21 CST: Inspected course snapshot refresh and named-answer
  precedence. Existing tests cover new lessons and deletion separately.
- [x] 2026-10-08 20:27 CST: Reproduced the old session shadow in a real host
  regression. The deployed real-model recall baseline also failed the new
  answered/updated case in all three repetitions (15/18 recall results passed,
  zero provider errors): answered keys remained unavailable.
- [x] 2026-10-08 20:27 CST: Refresh existing named answers from the authorized
  course snapshot and lift recall exclusion after this lesson accepts its answer.
  Six storage-backed cases and one deferred-resume regression cover cross-lesson
  updates, exact long/empty values, deletion/recreation, save failure and rewind.
  79 focused checks pass; broader validation and real-model candidate are running.
- [x] 2026-10-08 20:29 CST: Learning/profile/evaluator coverage passed 2,834
  tests, one expected skip and four subtests. Repository gates passed. The real
  selected course model passed all 18 recall results (six cases, three repeats)
  using isolated candidate methods/prompts; deployed acceptance is still pending.
- [ ] Open a focused PR, verify sim and reply to independent AI review findings.
- [x] 2026-10-08 20:41 CST: PR #3052 is open. Initial sim `44772405d`
  (build 416 / Drone 5207; deployments 2016/2017) passed all 60 real-model
  results with zero errors. Both API replicas match thirteen runtime hashes;
  HTTP read, 2.64-second TTS backfill and listen completion passed.
- [x] 2026-10-08 20:45 CST: Fixed two accepted review findings: infer answered keys only from
  genuine host interaction results, and synchronize authorized same-turn user
  corrections with their accepted answer copies. Learning/profile/evaluator
  coverage passed 2,848 tests, one expected skip and four subtests. Seeded values,
  old session/deferred formats, malformed evidence and same-turn corrections are
  covered. Final deployment acceptance and original-thread replies remain pending.
- [ ] Await manual main merge and verify release selection.

## Surprises & Discoveries

Named interaction answers remain in `Session.memory` after the host persists them
as course variables. `Session.all_memory()` gives that dictionary precedence over
the freshly loaded `user_memory`. A storage-backed regression must establish
whether this masks an update; model-only synthetic snapshots cannot establish it.

## Decision Log

- Keep deleted keys excluded when the host regenerates historical input. A new
  explicit answer can be accepted normally; replay is not renewed permission.
  The pre-guard regression failed exactly this case (25 passed, one failed).

- Reuse the real host, profile staging and database session store. Substitute
  only the model and thread bridge in offline tests.
- Keep registered system fields global and ordinary answers course-local.
- Keep session-only working notes distinct from durable named answers.
- No schema, dependency, configuration or production-routing changes.
- Infer acceptance from uniquely paired successful typed interaction results and
  current deferred answers already persisted in old sessions. Reject ambiguous,
  failed, unasked and empty evidence. Do not add a competing serialized marker;
  checkpoint/history restoration already restores this evidence on rewind.

## Outcomes & Retrospective

The focused offline regression and broader coverage pass. Candidate real-model
recall improves from 15/18 to 18/18, with zero provider errors in either run.
Deployed acceptance is pending; candidate overrides are not deployment evidence. Long-term cost, human acceptance and
other milestone-4 journeys remain tracked outside this focused change.

## Context and Orientation

`run_agent._load_or_start` reloads the authorized course snapshot each turn.
`Engine.run_turn` places named answers in session memory; `run_agent._persist`
also stages them as durable course variables. `engine.recall` merges both scopes.
Existing `deleted_memory` and `nickname` helpers handle separate refresh contracts.

## Plan of Work

First demonstrate the shadowed current value through actual profile persistence
and lesson reload. Correct only the named-answer refresh, then prove exact recall,
history preservation and transaction behavior through combined host journeys.

## Concrete Steps

1. Run the focused storage-backed regression before changing runtime behavior.
2. Implement the smallest refresh consistent with named-answer ownership.
3. Run learning/profile and engine regressions with conda `ai-shifu`.
4. Stage intended Markdown, regenerate the knowledge index, run repository gates,
   commit with the repository identity and push only to GitHub origin.
5. Publish a PR, synchronize sim and record actual acceptance evidence.

## Validation and Acceptance

After a named answer changes in another lesson, a resumed old lesson must recall
the exact current value. A fresh unanswered question must still exclude the prior
course answer. Session-only notes and historical answers must survive unchanged.
Deleted values must remain unavailable; failed saves must not persist a partially
refreshed session. No read-only recall may add profile rows.

## Idempotence and Recovery

Tests create isolated SQLite learners/courses. Only dedicated internal sim learner
data may be written during live acceptance. Failed local changes are reversible;
retain failed evidence and do not replace historical reports with later passes.

## Interfaces and Dependencies

Use existing host snapshot refresh, session serialization and memory APIs. Keep
the portable engine's session-memory precedence unchanged.

# Restore draft classroom history and isolated restart

## Purpose / Big Picture

Draft classroom previews can resume a pending engine question while the browser restores no teaching. The history endpoint and catalog currently depend on published learner progress, which previews deliberately do not write. Restore the exact rendered draft elements in order and allow restarting a draft without resetting published learning.

## Progress

- [x] 2026-10-09 21:40 CST: Read-only investigation found teaching text before interactions in stored model responses, while preview history lookup uses published progress.
- [x] 2026-10-09 21:40 CST: Finished the preceding exercise statistics PR validation and review replies.
- [x] 2026-10-09 21:55 CST: Added preview presentation ownership, scoped history/status/reset and regression coverage.
- [x] 2026-10-09 22:03 CST: Local checks and repository gates passed; submitted main PR #3072 and integrated sim as 94a175386.
- [x] 2026-10-09 22:15 CST: Added regression fixes for anchored follow-ups, several deferred controls, the stable generation timestamp and scriptless fallback. All four regressions fail without their fixes and pass with them.
- [ ] 2026-10-09 22:15 CST: Finish full regression, reply to review findings after pushing, and verify the reviewed sim runtime.

## Surprises & Discoveries

The same user/lesson has separate preview and published engine keys but no separate presentation lookup. Preview elements already persist, with no learner progress/block record. Empty-history auto-continuation re-asks a pending interaction without replaying teaching. Catalog restart visibility depends on published progress. The two current script snapshots are identical; this evidence does not support a model-ordering fault.

Review identified that follow-ups have independent adapter runs and several deferred controls can share a block. Presentation ownership must retain both. A mutable session update time also hides draft edits while the engine retains its original script. The separately reported old-answer error is an explicit unsupported preview rewind, outside this history/restart fix.

## Decision Log

- Preserve exact adapter elements instead of reconstructing raw model text, which could expose filtered content or omit host presentation.
- Keep host presentation run ownership in the existing preview session JSON, outside the engine schema. No database migration, learner-progress rows, or 1.0 deletion. The durable contract is [Draft Classroom History](../../references/markdownflow-draft-classroom-history.md).
- Reserve a preview generation before a request starts; save only into that generation so an in-flight turn cannot undo a preview restart.
- Existing preview sessions without presentation ownership restart once on their next run. Unscoped historical elements cannot safely be assigned retroactively. Published history remains intact.
- Preview reset is explicit and permission checked. The published reset retains its legacy scope for existing clients; preview reset never changes published progress or sessions.
- Existing reset analytics excludes previews; preserve that eligibility contract while restoring the existing preview action.

## Outcomes & Retrospective

The real offline engine/adapter/database path restores teaching before the pending interaction,
retains accepted answer display and supports isolated restart and completion. Removing either
the history dispatch or stale-generation guard makes its regression fail. Learning/scorer
regression passed 2,963 tests and four subtests (one expected skip); final focused coverage,
including three additional compatibility/scope cases, passed 197 tests. Seven frontend suites
passed 27 tests and frontend lint passed. Type-check reports two existing admin test errors
(TS2683/TS2790); removing both frontend changes and running the same command reproduces the
exact same two errors on main. No unrelated admin test change is included. Repository gates,
Initial sim build 476 succeeded and both API replicas matched 58 runtime hashes.
The reviewed revision and its deployed regressions remain pending.

## Context and Orientation

`agent/session_store.py` owns durable engine sessions. `runscript_v2.py` owns the adapter and commits its elements before terminal DONE. `listen_elements.py` is the classroom history entry. `learn_funcs.py` builds catalog state and resets progress; `routes.py` enforces preview permissions. `src/web/src/api/lesson.ts` sends the restart request. Editor Debug uses a separate transient store and is outside this classroom fix.

## Plan of Work

Add a host-owned preview presentation module that reserves a generation, records exact run IDs and loads only active-generation elements for the authenticated user/course/lesson. Preserve its metadata during engine saves, and reject stale saves after reset. Route preview history and catalog status to this ownership. Send explicit preview reset scope through the frontend and enforce permission before discarding only that preview. Cover text-before-interaction restoration, multi-request ordering, pending replies, isolation, reset races and the one-time legacy recovery.

## Concrete Steps

Use conda `ai-shifu`; run focused pytest from `src/api`, focused frontend API/catalog tests, type-check/lint and the repository pre-commit gate. Stage plan documentation before regenerating knowledge indexes. Submit the branch to GitHub origin and attach its PR. Integrate only on sim with existing sim changes preserved.

## Validation and Acceptance

A draft preview with no published progress reloads the original teaching before its pending interaction, and repeated reloads do not regenerate teaching. Multiple draft answers retain chronological display order. Catalog enables restart for draft activity even without learner progress. Preview restart clears only its generation; late saves cannot resurrect it. Published learning remains unchanged. Preview permission is required. Existing 1.0 and editor Debug paths retain their behavior.

## Idempotence and Recovery

Restart retires the preview generation, leaving its old rows for diagnosis. A retry reserves or reuses the current generation. An unowned legacy draft is restarted rather than guessed into history. Failed requests do not advertise terminal success before element commit. Production investigation stays read-only; sim probes use dedicated test learners only.

## Interfaces and Dependencies

Use existing LearnAgentSession JSON, active keys, LearnGeneratedElement, ElementDTO normalization, shared UoW, existing stream framing and permission helpers. New optional host arguments must preserve direct runner/editor callers. No engine schema change or new external dependency.

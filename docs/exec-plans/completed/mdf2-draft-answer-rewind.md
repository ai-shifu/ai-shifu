# Edit earlier answers in draft classrooms

## Purpose / Big Picture

Draft classrooms expose the existing answer-edit and regenerate actions, but the backend refuses every preview reload anchor. Store preview turn checkpoints so an earlier answer can replace its subsequent teaching without resetting the entire draft or changing published learning.

## Progress

- [x] 2026-10-09 22:28 CST: Confirmed #3072 merged as bdde9c54a and inspected preview ownership, published rewind and classroom reload callers.
- [x] 2026-10-09 22:48 CST: Implement scoped preview planning, checkpoint persistence and atomic retirement; coordinate exact interaction anchors and preview analytics.
- [x] 2026-10-09 22:48 CST: Local learning/scorer regression: 3,018 passed, one expected skip, four subtests; frontend 90 passed, changed-file lint passed.
- [x] 2026-10-09 23:06 CST: Repository gates and hooks passed. Opened #3073, fixed both AI findings and replied in their original threads. Final sim e6d292685 / build 482 / Drone 5271 deployed; both API replicas match 59 hashes and pass 232 isolated tests. Chrome answer-edit and reload acceptance passed on the internal boundary course.

## Surprises & Discoveries

Preview presentation already owns exact run IDs and question IDs, but no turn checkpoints. Several questions can share a generated block; answering one differently must identify its actual interaction element and the turn that accepted that question, rather than blindly taking the first later block. Existing formal rewind supplies checkpoint/restore helpers. AI review also found that textual variable-name fallback could redirect the chosen interaction to teaching. Preserve an exact selected control before any fallback, and derive reload anchors directly from that control; the added regression fails without this correction. A second AI finding exposed that engine checkpoint answers are only unconsumed deferred answers. Preserve display values independently, removing only answers accepted by retired host turns; both separate-model-turn answer-edit and regeneration regressions fail before the fix.

## Decision Log

- Extend existing host presentation JSON with versioned turn records; reuse checkpoint and restore without adding learner progress, blocks, migrations or engine schema changes.
- Resolve anchors only within the authenticated user/course/lesson and active preview generation. Validate before reserving a new run. Retire superseded elements and presentation answers in the guarded session-save transaction.
- A current unanswered first pending question is a normal answer. Old history without the required checkpoint remains explicitly unavailable, with restart as recovery; never guess state or fall back to 1.0 for a reload.
- Send exact element anchors alongside existing block IDs. Track preview rewind attempts and terminal outcomes through the shared analytics wrapper, with no authored content or raw errors.
- Keep 1.0, formal rewind, existing billing and memory admission policies intact.

## Outcomes & Retrospective

Implemented scoped checkpoints and atomic retirement with exact frontend anchors and preview-specific analytics. Local regressions pass, including two questions per block, scoped anchors, stale plans, reset during model output, rollback, original-input replay and retired follow-ups. Backend mutation checks fail with the old preview guard or omitted retirement; the hook test fails with the old block-only anchor. Full frontend type-check reports only the two independently reproduced main baseline admin test errors (TS2683 and TS2790). PR #3073 is open with functional head b781942bc. Both original AI threads contain pushed fixes and validation. CodeRabbit reported its quota limit, so no substantive CodeRabbit approval is claimed. Final sim e6d292685 (sim-e6d2926), build 482 / Drone 5271, has two ready API replicas and one ready web replica. Each API matches 59 runtime hashes and passes 232 isolated SQLite/FunctionModel regressions. Chrome changed the first answer from option A to B, then changed the later multiple-choice answer from apple to banana; after reload both the earlier B selection and new banana selection remain, with preceding teaching and one closing paragraph. The browser proof is retained privately in the task workspace. HTTP health is 200. At archival, the functional head has passed all completed technical checks; runtime-harness is still running. This is focused natural-model browser acceptance, not full-course or independent human acceptance. Production remains untouched by this PR. Sim retains its existing Workflow integration. Main merge remains the user’s decision.

## Context and Orientation

`agent/preview_history.py` owns draft presentation. `agent/rewind.py` owns shared checkpoints and formal rewind. `agent/lesson_entry.py` resolves requests, `agent/run_agent.py` stages saves, and `runscript_v2.py` reserves generations and persists rendered elements. The classroom hook supplies reload anchors and stream lifecycle. The canonical draft-history reference records the durable contract.

## Plan of Work

Record each preview turn checkpoint and inputs in presentation metadata. Plan answer edits from the checkpoint whose first pending question is the selected control, and regeneration from the target block checkpoint. Restore with the existing engine path; atomically retire the superseded suffix and update presentation answers only when the guarded session save succeeds. Preserve owned earlier teaching and follow-ups. Wire exact UI anchors and bounded preview-specific analytics.

## Concrete Steps

Use conda ai-shifu for Python. Run focused draft/formal rewind and runner tests, then full learning/scorer coverage. Run classroom hook/analytics tests, lint and type-check with documented baseline comparison. Stage docs and regenerate knowledge indexes. Run developer tool verification and full pre-commit gate before commits. Push origin, create a main PR, reply to every AI finding, integrate sim and verify its actual runtime with isolated SQLite/FunctionModel tests.

## Validation and Acceptance

Editing an old draft answer restores the selected question, keeps its preceding teaching, displays the new answer and excludes superseded teaching and follow-ups after reload. Several controls sharing a block retain individual answers. Regeneration reuses original turn input. Published progress/session remains unchanged. Wrong user/course/lesson, stale generation and missing checkpoints are rejected without changing visible history. Reset and save failures cannot partially retire history. Preview analytics emits one start and one terminal result per initiated rewind, excludes ordinary/formal runs, and cannot block teaching when tracking fails.

## Idempotence and Recovery

Retired rows remain available for diagnosis but are excluded from active presentation. Failed save rolls back retirement with the session. A reset invalidates the entire generation, rejecting late writes. Old checkpoints are not synthesized from model output; restart creates usable new checkpoints.

## Interfaces and Dependencies

Use existing LearnAgentSession JSON, LearnGeneratedElement, RewindPlan/checkpoint helpers, transaction owner, SSE messages and tracking. No new external dependency or 1.0 deletion.

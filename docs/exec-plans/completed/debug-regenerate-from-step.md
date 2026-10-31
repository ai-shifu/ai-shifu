# Regenerate editor Debug from a selected step

## Purpose / Big Picture

The editor Debug regenerate button currently restarts the entire lesson even
though its callback identifies the selected content element. Preserve completed
steps before that element's engine turn, restore the turn's conversation and
memory, and regenerate that turn and its successors through the normal flow.

## Progress

- [x] 2026-10-31 CST: Inspected frontend callbacks, Debug cache, runtime rewind,
  and adjacent regression tests; created a branch from current remote main.
- [x] 2026-10-31 CST: Add isolated Debug turn checkpoints and anchored requests.
- [x] 2026-10-31 CST: Preserve the frontend prefix, restore memory, and track
  accepted regeneration requests and outcomes.
- [x] 2026-10-31 CST: Pass 453 focused backend and 145 frontend regressions,
  frontend type-check and lint, Ruff, harness, architecture and UoW checks.
- [x] 2026-10-31 CST: Complete the repository-wide pre-commit gate; prepare
  the independent feature branch for review without merging or deploying.
- [x] 2026-10-31 CST: Adapt the feature to main `9226669f2` after #3264 merged,
  retaining its file and API naming. Pass 453 backend and 245 frontend tests,
  frontend type-check and all 21 repository-wide checks.

## Surprises & Discoveries

The previous `useDebugSession.regenerateContent` handler received an element ID
but restarted the entire lesson instead of using that ID.
Debug sessions retain an expiring engine session without persisted turn blocks;
classroom rewind cannot be reused directly without Debug checkpoint storage.
Several rendered elements can share one generated block and checkpoint.
Independent review found that automatic continuation could reapply discarded
answers and reset the restored output language; continuation now resumes saved
Debug memory. Real SSE clean closure uses `readystatechange`, and a state-backed
streaming flag keeps the UI ready to accept the next answer.

## Decision Log

- Keep the existing preview endpoint and optional `reload_generated_block_bid`
  contract, with the same Debug session ID and script. Store checkpoint metadata
  only in the existing isolated Debug cache; no database migration.
- Apply the feature on top of the merged Debug naming refactor (#3264).
  Internal `DebugRunParams` uses `reloadGeneratedBlockBid`; only the request
  payload uses `reload_generated_block_bid`. Preserve the current inline
  regenerate/audio/copy action row from #3263.
- Restore from the selected generated block's beginning, removing all sibling
  elements and later blocks. Preserve earlier block output and helper rows.
- Emit `debug_variables` with restored memory before replacement elements so
  the frontend drops answers belonging to discarded steps.
- Preserve explicit whole-lesson restart when no element is supplied and when
  the draft script changes. Reject unknown or expired anchored state.
- Add a separate Debug analytics family rather than changing the existing
  classroom rewind population; its durable contract lives in
  `docs/references/frontend-product-analytics.md`.

## Outcomes & Retrospective

Backend checkpoints, frontend prefix retention, request-scoped anchors,
restored variables, analytics and late-request ownership are implemented.
Focused tests include real offline FunctionModel generation and original-input
replay, not only constructed checkpoint metadata. All 21 repository-wide
pre-commit checks passed, including Ruff, frontend lint/format, translations,
knowledge harness, architecture and UoW boundaries. Frontend type-check passed;
The current rebased feature passes 453 backend and 245 frontend tests. Backend
code and tests remain identical to the original feature commit; frontend changes
adapt the existing cases to the current names without adding behavior. Lint
retains existing warnings outside this change; touched frontend files have no
warnings. No merge, deployment or
live-model browser acceptance was performed.

## Context and Orientation

`src/web/src/components/lesson-debug/use-debug-session.tsx` owns editor Debug
streams and regeneration. `debug-request-params.ts` resolves the first rendered
item of a generated block. `DebugPanel.tsx` supplies per-element action-row
callbacks. Shared request types live in `src/web/src/types/debug-session.d.ts`;
`debug-regenerate-tracking.ts` owns accepted-attempt and outcome tracking.
Backend Debug state lives in
`src/api/flaskr/service/learn/agent/debug_session.py`; `lesson_entry.py` and
`run_agent.py` orchestrate the existing engine and adapter. Classroom rewind
helpers in `agent/rewind.py` describe checkpoints and replay inputs.

## Plan of Work

Extend Debug cache state to retain turn checkpoints and original inputs,
validate anchored requests, restore the engine before replacement generation,
and retire its cached suffix only when the replacement saves successfully.
Extend the hook request contract and preserve its prefix on anchored refresh.
Consume restored variables and keep stale streams and TTS isolated. Add
regressions and best-effort analytics through the existing shared tracker.

## Concrete Steps

Run focused Jest preview suites, focused backend Debug/rewind tests, frontend
type-check and lint, repository harness and architecture boundary checks.
Regenerate knowledge inventories after adding this plan. Run the development
tool doctor and repository pre-commit gate before any commit.

## Validation and Acceptance

An unchanged draft can regenerate a selected content step without rerunning
earlier turns. Its original input and preceding context remain available;
discarded future answers disappear from both engine memory and visible Debug
variables. Regeneration can pause for a new answer or complete, then continue
without replaying the old anchor. Unknown or expired anchors cannot silently
start a new session. Full restart and edited-script behavior remain covered.
Analytics records one accepted attempt and one terminal outcome, excludes
blocked clicks, omits private content and cannot break generation.

## Idempotence and Recovery

Checkpoints belong to the existing author/course/lesson/run cache identity.
Expired or incompatible state fails closed. A full Debug restart creates a new
run ID. Late SSE/TTS callbacks cannot update a replacement run. No published
learner history or formal-learning session is modified.
Cache request tokens and a short write lock prevent a stopped host from
overwriting a newer request's session or checkpoint suffix.

## Interfaces and Dependencies

Use existing `PlaygroundPreviewRequest`, `DebugSessionStore`, checkpoint and
restore helpers, preview element adapter and shared tracking. New request
fields are optional; existing unanchored requests retain their behavior. No
new package dependency or engine-library change is required.

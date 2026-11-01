# Regenerate editor Debug from a selected step

## Purpose / Big Picture

Historical implementation record: the current editor Debug frontend retires
content regeneration and Retry in the
[removal plan](remove-debug-content-regeneration.md). Backend checkpoint and
reload compatibility remains; this plan does not describe current UI controls.

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
- [x] 2026-10-31 CST: Verify the stopped-save review report against the actual
  two-stage planner; add a regression proving the runtime retires the racing
  suffix after claiming the request, without changing correct production logic.
- [x] 2026-10-31 CST: Add a reliable retry entry after failed/stopped generation,
  including uncertain failures after backend state has already saved.
- [x] 2026-10-31 CST: Verify both review conclusions with deterministic tests:
  375 backend and 181 frontend cases pass, including real provider failure,
  repeated retries, reset/script boundaries and analytics isolation.
- [x] 2026-11-01 CST: Rebase onto main `5d752a5e1`, keeping its frontend
  naming changes and existing regeneration regressions.
- [x] 2026-11-01 CST: Bind Debug locking and state to one strict Redis provider
  when configured, retaining an explicit process-local development mode.
- [x] 2026-11-01 CST: Add localized temporary-unavailability errors and verify
  outages, recovery, request ownership and frontend retry behavior.
- [x] 2026-11-01 CST: Pass 493 related backend tests and 212 frontend tests,
  frontend type-check, translation parity and usage validation.
- [x] 2026-11-01 CST: Complete all 21 repository-wide checks; synchronize
  the tracked plan path before regenerating its knowledge indexes.

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
Review found that truncating rows before regeneration makes the selected target
inaccessible on failure. Lack of output does not prove that replacement state
was not saved; restoring old rows would risk displaying discarded answers as
current. A separate retry target and narrowly scoped backend mapping handle
both pre-save and uncertain post-save failures.
Redis lock construction is lazy: a connection error can occur in `acquire()`.
The shared fallback provider independently chooses a backend for each data call,
so replacing a failed Redis lock with a local lock could protect Redis writes
with only a process-local mutex after recovery. The existing verification-code
flow already selects strict Redis when configured.

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
- Keep a retry target and preserved prefix for the current Debug session,
  independently of visible replacement rows. Retry the same logical target
  through the existing request. Resolve only its current first replacement
  block after a save; never make unrelated retired suffix anchors valid.
- Add a separate Debug analytics family rather than changing the existing
  classroom rewind population; its durable contract lives in
  `docs/references/frontend-product-analytics.md`.
- Bind each Debug store's lock, request token and state to the same provider.
  Configured Redis is a consistency dependency: failure is reported explicitly,
  including a failure during save or lock release. Never switch to local data
  during a configured-Redis outage. Without Redis, retain process-local Debug.
- Use `server.learn.debugServiceUnavailable` / code `4023` for temporary cache
  failures. Keep it distinct from an expired session or an invalid rewind.
  Capture its request-language message before streaming and preserve its code
  in the existing error event; frontend recovery keeps the current retry target.

## Outcomes & Retrospective

Backend checkpoints, frontend prefix retention, request-scoped anchors,
restored variables, analytics and late-request ownership are implemented.
Focused tests include real offline FunctionModel generation and original-input
replay, not only constructed checkpoint metadata. Review follow-up adds a
retry control and one cached logical-target mapping so uncertain failures can
retry without restoring discarded rows or answers. A real provider exception
proves that even a bare error can save replacement state. A separate regression
verifies that the existing post-claim runtime planner retires a racing old turn;
that report required no production concurrency change.

The rebased feature previously passed 453 backend and 245 frontend tests.
The review follow-up passes 375 relevant backend and 181 frontend tests, plus
frontend type-check. The repository-wide pre-commit gate covers Ruff, frontend
lint/format, translations, knowledge harness, architecture and UoW boundaries.
Lint retains existing warnings outside this change. PR CI and review status
are verified live after each push. No merge, deployment or live-model browser
acceptance was performed.

The Redis follow-up binds Debug state and locks to one backend and translates
cache/lock failures to a localized, retryable business error. Its 493 backend
tests include an actual deferred Redis lock connection error, pre-save and
post-save failures, recovery, cancellation, request ownership, shared-cache
compatibility and SSE ordering/language. Its 212 frontend tests include all
eight translated error messages and recovery through the existing retry action.
Frontend type-check and translation validation pass. Current-head GitHub CI and
review convergence are tracked in [PR #3262](https://github.com/ai-shifu/ai-shifu/pull/3262)
after the local implementation and verification are committed.

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

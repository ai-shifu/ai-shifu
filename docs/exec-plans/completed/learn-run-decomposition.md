# ExecPlan: Learn /run Chain Decomposition (B6)

## Purpose / Big Picture

`flaskr/service/learn/context_v2.py` (3,728 lines) hosts the /run SSE
runtime. `RunScriptContextV2` is 2,393 lines and its `run_inner` method alone
is 1,056 lines mixing outline-state resolution, DB persistence (20 mid-flow
flushes), SSE event construction, MDF/LLM streaming, and TTS lifecycle. This
plan decomposes it into four collaborators under `flaskr/service/learn/run/`
while keeping the SSE contract byte-identical (golden harness) — and the
result doubles as the specification for the Go port (Phase 3 Wave 5 of
`backend-overhaul-master.md`).

## Progress

- [x] 2026-07-03 19:05 CST: Design captured from the class skeleton; batch
  strategy decided (three incremental extraction PRs, no parallel-path flag —
  see Decision Log).
- [x] 2026-07-03: PR1 emitter extraction implemented on
  `aichy/optimization-260703`: `flaskr/service/learn/run/emitter.py`
  (`RunEventEmitter`) owns the nine emitter-cluster methods; the context
  keeps same-named thin delegating wrappers (test seams preserved). New
  delegation/seam/payload tests in
  `tests/service/learn/run/test_run_emitter.py`. Learn suite 290 passed
  (277 + 13 new), golden 11 passed with fixtures byte-identical, full suite
  1,931 passed (1,918 + 13), uow/boundary/harness checks green.
- [x] 2026-07-03: PR2 recorder extraction implemented on
  `aichy/optimization-260703`: `flaskr/service/learn/run/recorder.py`
  (`RunRecorder`) owns /run persistence with one `unit_of_work()` per step
  (progress placeholders, pointer flips, generated-block saves, post-stream
  block finalize, transitional ask-path commit). All ~20 mid-flow
  `db.session.flush()` sites migrated or converted to documented stage-only
  sites; full audit table below ("PR2 audit table"). New failure-path tests
  in `tests/service/learn/run/test_run_recorder.py`. Learn suite 295 passed
  (290 + 5 new), golden 11 passed with fixtures byte-identical, full suite
  1,936 passed (1,931 + 5), uow ratchet 155 unchanged, boundary + harness
  checks green, ruff clean.
- [x] 2026-07-03 23:40 CST: PR3 state extraction + phase decomposition:
  `flaskr/service/learn/run/state.py` (`RunStateResolver`, pure reads, lazy
  cached property, cross-method dispatch through context wrappers preserving
  the instance-patch seams); `run_inner` decomposed into 14 `_phase_*`
  generator methods with `_RunStepState` threading the shared locals —
  adversarial review verified the phase extraction line-by-line as pure
  motion (yields, loop exits, TTS closures byte-identical). check_risk
  self-commit NOTE added at the check_text call site. Includes the
  out-of-scope-but-reviewed leaf-bid placeholder fix (separate session; see
  Decision Log) with 4 regression tests. Boundary baseline updated for the
  three relocated pre-existing shifu imports carried by `state.py`. Learn
  suite 310 passed; golden 11 byte-identical; full suite 1,940 passed.
- [x] 2026-07-03 (B7): the end-to-end disconnect test deferred from PR3
  landed as `tests/service/learn/run/test_run_disconnect_e2e.py` (2 tests).
  It drives real generator `.close()` on `run_script_inner` (the generator
  the production wrapper closes at `runscript_v2.py` producer `finally`),
  reusing the golden harness fixtures (deterministic fake LLM + seeded
  published shifu). Mid-stream close: the staged streamed-block row is
  discarded (no durable empty generated block, no partial content), while
  committed recorder steps (progress placeholders, finalized preserved
  block) survive; a re-run resumes from the last finalized block and
  regenerates the interrupted block exactly once. Sensitivity was proven by
  mutation: flipping the `except GeneratorExit` rollback to a commit makes
  the test fail. Driving `run_script` itself was rejected because its
  producer thread free-runs against the fast fake LLM, making a
  deterministic mid-stream disconnect impossible from outside the
  generator (see Decision Log).

## Surprises & Discoveries

- PR1: tests build contexts via `RunScriptContextV2.__new__` (bypassing
  `__init__`), so the emitter is created lazily through a cached
  `_event_emitter` property instead of in `__init__`.
- PR1: tests monkey-patch emitter methods as *instance attributes* on the
  context (`ctx._emit_lesson_feedback_interaction = ...`), so the emitter
  dispatches cross-method calls back through the context wrappers
  (`ctx._emit_*`) rather than calling its own methods directly. PR3 must
  keep (or deliberately retire) these seams.
- PR1: methods in the emitter cluster that still carry DB writes (moved
  intact; PR2 pulls the writes into the recorder):
  `render_outline_updates` (progress-record status/block_position flips +
  4 `db.session.flush()` sites), `emit_next_chapter_interaction` and
  `emit_lesson_feedback_interaction` (generated-block insert + flush),
  `ensure_current_attend_for_gate_interaction` (creates a
  `LearnProgressRecord` when missing + flush),
  `emit_current_progress_gate_interaction` (generated-block insert + flush).
- PR1: inline `RunMarkdownFlowDTO` construction still inside `run_inner`
  (inventory for PR3; not moved because each is fused with streaming/
  persistence logic, at post-PR1 line numbers of `context_v2.py`):
  interaction re-emit on input-required 2466 and 2518; interaction pause
  2570; content replay 2658; break 2667; interaction replay 2693;
  VARIABLE_UPDATE after profile save 2739; streamed content 2796 + break
  2802; interaction after LLM output 2848; tail-gate interaction 2920;
  streamed content event (TTS path) 2995; break after stream 3189.
  Preview-side constructions (`_iter_preview_generated_events` 992/998,
  `_preview_events_from_result` 1047, `_make_preview_content_event` 1077)
  belong to `RunScriptPreviewContextV2` and are out of scope.
- PR2: committing the streamed content block *before* streaming (a durable
  "block-init step") would break resume semantics: the `generated_blocks`
  context query and the `existing_content_block` duplicate guard in
  `run_inner` do not filter on `generated_content != ""`, so a durable empty
  row left by a mid-stream disconnect would be replayed into the LLM context
  and could make the duplicate guard skip regeneration entirely. The block
  is therefore *staged* (session add + flush, no uow) and becomes durable
  only in the post-stream `finalize_streamed_block` step — mid-stream
  disconnect semantics are byte-identical to pre-PR2.
- PR2: `BreakException` was the worst instance of the dirty-row class: the
  producer's `except BreakException: db.session.commit()` in
  `runscript_v2.py` would commit whatever half-step state the flush sites
  had accumulated. With per-step boundaries the session between steps holds
  at most staged stream rows, so that commit can no longer persist a torn
  step. (The exception is currently never raised — legacy handler.)
- PR2: `_get_current_attend`'s placeholder loop relied on autoflush to
  dedupe: a row created for the target outline earlier in the parent-path
  loop was visible to later same-bid queries. With staging, the loop now
  checks the staged list explicitly before creating (behavior preserved).
- PR2: `retry_on_deadlock` is applied to NO recorder step: a step commit
  also makes rider writes durable (profile saves, TTS sidecar rows,
  check-text logs are flushed by collaborators between steps), and a
  deadlock retry re-runs only the recorder method, silently dropping those
  riders after the rollback. Revisit in PR3 when the recorder owns all /run
  writes.

## PR2 audit table

Every pre-PR2 write/flush site in the /run chain, its new boundary, and the
durability/failure-semantics change. "Outer commit" = the producer commits
in `runscript_v2.run_script_inner` (L383 reload / L402 loop end / L408
BreakException), which remain in place and now only cover stream-staged
rows and not-yet-migrated collaborator writes. Pre-PR2, ALL sites below
were durable only at the outer commit, and any failure rolled back the
entire run while flushed rows sat dirty in the session (committable by the
BreakException handler).

| # | Old site (pre-PR2) | New boundary | Durability timing | Failure semantics |
|---|---|---|---|---|
| 1 | `_get_current_attend` placeholder loop: add+flush per created row | context stages rows; one `save_new_progress_records` step for the batch | outer commit -> step commit at creation | partial placeholder rows impossible: batch rolls back whole |
| 2 | `render_outline_updates` leaf/IN_PROGRESS same-attend: mutate, yield, flush | `update_progress_pointer` step, then yield | outer commit -> step commit (now *before* the SSE event instead of after) | failed flip no longer emits the outline event first; step rolls back whole |
| 3 | `render_outline_updates` leaf NOT_STARTED/LOCKED promote: mutate+flush, yield | `update_progress_pointer` step, then yield | outer commit -> step commit | step rolls back whole |
| 4 | `render_outline_updates` leaf COMPLETED: mutate+flush, yield | `update_progress_pointer` step, then yield | outer commit -> step commit | step rolls back whole |
| 5 | `render_outline_updates` node IN_PROGRESS/NOT_STARTED: mutate+flush, yield | `update_progress_pointer` step, then yield | outer commit -> step commit | step rolls back whole |
| 6 | `render_outline_updates` node COMPLETED: mutate+flush, yield | `update_progress_pointer` step, then yield | outer commit -> step commit | step rolls back whole |
| 7 | `run_inner` flush after first `_render_outline_updates` | removed (flips already committed per step; re-read follows) | n/a | n/a |
| 8 | `run_inner` flush after `_render_outline_updates(new_chapter=True)` in the script-None branch | removed | n/a | n/a |
| 9 | `run_inner` flush after `_render_outline_updates(new_chapter=True)` in the position>=len branch | removed | n/a | n/a |
| 10 | ask path `db.session.flush()` after ask stream completes | `commit_pending_step` (transitional: ask writes still live in `handle_input_ask`) | outer commit (microseconds later) -> step commit at same post-stream point | unchanged for mid-stream disconnect (flush was already post-stream) |
| 11 | input realign to pending interaction: attend position/status + flush | `update_progress_pointer` step | outer commit -> step commit | step rolls back whole |
| 12 | non-interaction input fallthrough: status + flush | `update_progress_pointer` step | outer commit -> step commit | step rolls back whole |
| 13 | pay-gate unpaid: `_persist_generated_block_for_events` + trailing flush | persist helper delegates to `save_generated_block` step; trailing flush removed | outer commit -> step commit before the INTERACTION event | gate row commit precedes the event; failure emits nothing durable |
| 14 | pay-gate paid skip: position += 1 + flush | `update_progress_pointer` step | outer commit -> step commit | step rolls back whole |
| 15 | login-gate logged-in skip: position += 1 + flush | `update_progress_pointer` step | outer commit -> step commit | step rolls back whole |
| 16 | login-gate not-logged: persist + trailing flush | same as #13 | outer commit -> step commit | same as #13 |
| 17 | INPUT no-cached-block interaction render: persist (add+flush) | `save_generated_block` step (after the COMPLETE render returns) | outer commit -> step commit | step rolls back whole; no uow spans the LLM call |
| 18 | student input record: mutations across a COMPLETE render, `status=1`, flush | mutations unchanged; `save_generated_block` step after the render | outer commit -> step commit | accumulated mutations commit or roll back atomically |
| 19 | post-check-text re-render (has_content): mutations + persist | `save_generated_block` step | outer commit -> step commit | step rolls back whole |
| 20 | no-variable advance: status+position + flush | `update_progress_pointer` step | outer commit -> step commit | step rolls back whole |
| 21 | variables-saved advance: status+position + flush | `update_progress_pointer` step (profile rows saved by `save_user_profiles` ride into this commit) | outer commit -> step commit; profile rows durable earlier too | flip + profile rows commit together; failure rolls both back |
| 22 | validation-error block init: add + flush (before error stream) | STAGE ONLY (kept add+flush, no uow, documented) | unchanged: durable only at the post-stream save (#23) | mid-stream disconnect still discards the row via producer rollback |
| 23 | validation-error block finalize: content + add + flush | `save_generated_block` step after the error stream | outer commit -> step commit | init+content commit atomically |
| 24 | error-path interaction re-init: add + flush (before COMPLETE render) | STAGE ONLY (kept add+flush, no uow, documented) | unchanged: durable only at #25 | a failed render leaves no durable half-initialized row |
| 25 | error-path interaction persist after render | `save_generated_block` step | outer commit -> step commit | step rolls back whole |
| 26 | error-path tail `attend.status = IN_PROGRESS` (no flush) | `update_progress_pointer` step | outer commit -> step commit | previously dangling pending write; now an explicit step |
| 27 | OUTPUT interaction pay/login skip: position += 1 + flush (x2) | `update_progress_pointer` steps | outer commit -> step commit | step rolls back whole |
| 28 | OUTPUT interaction persist after COMPLETE render | `save_generated_block` step (via persist helper) | outer commit -> step commit | step rolls back whole |
| 29 | OUTPUT interaction tail `attend.status = IN_PROGRESS` (no flush) | `update_progress_pointer` step | outer commit -> step commit | previously dangling pending write; now an explicit step |
| 30 | duplicated fixed-output skip: status+position + flush | `update_progress_pointer` step | outer commit -> step commit | step rolls back whole |
| 31 | content block init: `_persist_generated_block_for_events` (add+flush) BEFORE the LLM stream | STAGE ONLY (inline add+flush, no uow, documented) | unchanged: durable only at #32 | mid-stream disconnect discards the staged row (producer rollback) -> re-run regenerates the block, byte-identical to pre-PR2 |
| 32 | content block finalize: content + add + attend flip + flush AFTER the stream | `finalize_streamed_block` step (content + cursor atomically; pending TTS/listen-element sidecar rows ride along) | outer commit (end of whole run) -> step commit right after BREAK; a multi-block run is now durable block-by-block | no reader can see a streamed block without its cursor flip; disconnect *between* blocks now resumes from the last finalized block instead of regenerating the whole segment |
| 33 | completion tail: render + tail interactions + trailing flush | flips/inserts are recorder steps inside the emitter; trailing flush removed | outer commit -> per-step commits | each tail insert/flip isolated |
| 34 | `emit_next_chapter_interaction`: add + flush | `save_generated_block` step | outer commit -> step commit | step rolls back whole |
| 35 | `emit_lesson_feedback_interaction`: add + flush | `save_generated_block` step | outer commit -> step commit | step rolls back whole |
| 36 | `ensure_current_attend_for_gate_interaction`: add + flush | `save_new_progress_records` step | outer commit -> step commit | step rolls back whole |
| 37 | `emit_current_progress_gate_interaction`: add + flush | `save_generated_block` step | outer commit -> step commit | gate rows in the Paid/NotLogin exception path now survive independently of the failed run body |

Streaming-outside-uow proof: every `unit_of_work()` of the /run chain lives
in `recorder.py`, and every recorder method is a plain (non-generator)
function that opens and closes its uow within one synchronous call — no
`yield` can suspend inside a step, and `run_inner` only calls recorder
methods before a stream starts or after it has fully completed (BREAK
emitted / COMPLETE returned). `grep -n "unit_of_work" flaskr/service/learn/`
returns only `run/recorder.py`.

## Decision Log

- 2026-07-03: The master plan sketched a config-flag parallel path. REJECTED
  in favor of three golden-guarded incremental extraction PRs: a parallel
  rewrite of a 1,056-line `run_inner` is a big-bang inside a batch that the
  4-scenario golden corpus cannot fully discriminate, while each extraction
  PR is independently revertable and keeps one source of truth. The flag
  would also double maintenance for the whole window.
- SSE events are constructed in exactly one place after PR1 (the emitter);
  event names/payload shapes are FROZEN per `learn/AGENTS.md`.
- 2026-07-03 (PR2 review): durability-first ordering ACCEPTED for outline
  progress updates. `update_progress_pointer` commits before the
  OUTLINE_ITEM_UPDATE event is queued, so a concurrent outline-tree GET can
  observe the advanced state slightly before the same client's SSE stream
  shows it. Pre-PR2 had the inverse anomaly (event visible while the row
  was still non-durable and could vanish on rollback); durable-then-notify
  matches the `uow.on_commit` doctrine adopted in B4 and is the semantics
  the Go port will implement. Event payload bytes are unchanged
  (golden-verified).
- 2026-07-03 (PR2 review): the mid-stream-disconnect recorder test models
  the producer's add/flush/rollback sequence at session level; an
  end-to-end test driving generator `.close()` through `run_script_inner`
  is a PR3 follow-up. Review also flagged two pre-existing issues out of
  PR2 scope: `check_risk/funcs.py:33` commits raw (reachable from inside
  the /run generator; account for it in PR3's "recorder owns all /run
  writes" goal) and the `_get_current_attend` placeholder loop stamps every
  ancestor row with the LEAF's outline bid (`context_v2.py:1745`,
  pre-existing; tracked separately).
- 2026-07-03 (leaf-bid placeholder fix): the placeholder loop now stamps
  `item.bid` (each ancestor's own bid) instead of the leaf's;
  `tests/service/learn/test_get_current_attend_placeholders.py` drives the
  multi-ancestor loop against a real session (prior suites monkeypatched
  `_get_current_attend`). Read-side check found no reader depending on the
  wrong value: the extra rows were NOT_STARTED leaf-bid duplicates that the
  main query orders last, while missing ancestor rows degrade
  `get_course_learn_record` aggregation, `reset_learn_record`, and feedback
  progress-record resolution — all of which expect per-node rows. Prod data
  (read replica, v2-era `created_at >= 2025-09-30`): duplicate non-reset
  `(user, leaf)` groups exist and 6,366 leaf rows lack a same-user parent
  record; backfill/cleanup of historical rows is a separate decision, the
  code fix only stops new corruption. PR3 review addendum: the widest-blast
  exposure is the mainline `/run` hot path itself —
  `RunEventEmitter.render_outline_updates` calls `_get_current_attend` with
  ANCESTOR bids on nearly every chapter/unit transition, which pre-fix could
  re-enter the placeholder-creation branch on every transition (no row ever
  existed under the ancestor's own bid); a regression test for this direct
  ancestor-call shape now exists
  (`test_direct_ancestor_call_stamps_own_bids`).

- 2026-07-03 (B7): the disconnect e2e drives `run_script_inner` directly
  instead of `run_script`. The production `res.close()` in the producer
  thread's `finally` closes exactly this generator, so the semantics under
  test are identical; the thread/SimpleQueue wrapper in `run_script` cannot
  be paused deterministically mid-stream from the consumer side (the
  producer free-runs against the fast fake LLM), so an outer-level test
  would race. No production seam was added.

## Outcomes & Retrospective

- Delivered across three extraction PRs plus the B7 tail: the /run runtime
  is four collaborators under `flaskr/service/learn/run/` — `emitter.py`
  (sole SSE constructor), `recorder.py` (one `unit_of_work()` per step; the
  flush-then-fail dirty-row class is gone), `state.py` (pure reads) — and
  `run_inner` decomposed into 14 named `_phase_*` generators on the
  `RunScriptContextV2` facade. SSE events stayed byte-identical to the
  golden fixtures through every PR.
- Test growth: learn suite 277 -> 312 (emitter payloads, recorder failure
  paths, leaf-bid placeholder regressions, the B7 disconnect e2e); full
  suite 1,918 -> 1,942.
- The incremental-extraction strategy (vs the master plan's config-flag
  parallel path) held up: every PR was independently revertable, reviewable
  line-by-line as pure motion, and there was never a second source of truth.
- What made it hard: tests build contexts via `__new__` and monkeypatch
  collaborator methods as instance attributes, so the extractions had to
  preserve context-level dispatch seams; pysqlite's lazy-BEGIN savepoint
  behavior (discovered in B4c) shaped how failure-path tests are written.
- Left for later, tracked elsewhere: `RunScriptPreviewContextV2` decompose
  (evaluate separately), `check_risk/funcs.py:33` raw commit reachable from
  the /run generator, `retry_on_deadlock` for recorder steps once the
  recorder owns all /run writes, and backfill/cleanup of historical
  leaf-bid placeholder rows in production data.
- This decomposition is the specification for the Go port (Phase 3 Wave 5
  of `backend-overhaul-master.md`).

## Context and Orientation

`RunScriptContextV2` method clusters (line ranges at commit 203b198a):

- **Emitter cluster (→ PR1)**: `_render_outline_updates` (1965),
  `_emit_next_chapter_interaction` (2053),
  `_emit_lesson_feedback_interaction` (2105),
  `_is_access_gate_blocking_interaction` (2158),
  `_maybe_emit_feedback_after_access_gate` (2172),
  `_emit_feedback_after_exception_gate` (2185),
  `_ensure_current_attend_for_gate_interaction` (2224),
  `_emit_current_progress_gate_interaction` (2260),
  `_emit_completion_tail_interactions` (2295). All construct
  `RunElementSSEMessageDTO`-family events.
- **State cluster (→ PR3)**: `_get_current_attend` (1681, also writes —
  split read/write in PR2/PR3), `_is_leaf_outline_item` (1746),
  `_get_current_outline_block_count` (1756), `_get_next_outline_item`
  (1805), `_has_next_outline_item` (1937), `_is_current_outline_completed`
  (1951), `_get_outline_struct` (2351), `_get_outline_row_id` (2365),
  `_get_run_script_info*` (2379/2405).
- **Recorder targets (→ PR2)**: the ~20 `db.session.flush()` sites inside
  `run_inner` and `_get_current_attend`; generated-block persistence via
  `utils_v2.init_generated_block`; progress-record status flips. Each step
  becomes one `unit_of_work()` (from `flaskr/dao/uow.py`), so a mid-step
  failure rolls the step back whole instead of leaving flushed dirty rows.
- **Orchestrator (stays, slims down)**: `run` (3490), `run_inner` (2432,
  1,056 lines — decompose into named phase methods in PR3), `reload` (3583),
  TTS lifecycle (`_try_create_tts_processor` 1497,
  `_finalize_stream_tts_processor`, `_teardown_stream_tts_state`),
  `_iter_stream_result_with_idle_callback` (1617), langfuse helpers.
- NOT in scope: `runscript_v2.py` thread/queue/Redis-lock mechanics (they
  are rewritten once, in Go); `RunScriptPreviewContextV2` (625 lines,
  separate surface — evaluate after PR3); `RUNLLMProvider`;
  `MdflowContextV2`.

## Plan of Work

- **PR1 — emitter**: new `flaskr/service/learn/run/emitter.py` owning every
  SSE event constructor from the emitter cluster. The context keeps thin
  delegating wrappers (same method names) so `run_inner` diffs stay minimal
  in this PR. Any event construction inline in `run_inner` moves behind an
  emitter method too (inventory them while extracting).
- **PR2 — recorder**: new `flaskr/service/learn/run/recorder.py` owning
  progress-record writes, generated-block init/update/finalize, and history
  rows. One `unit_of_work()` per logical step; audit table mapping each old
  flush site to its new boundary (B4-style, including failure-semantics
  changes). This PR deliberately changes mid-step failure behavior from
  "dirty flushed rows" to "step rolls back whole" — document each site.
- **PR3 — state + orchestrator**: new `flaskr/service/learn/run/state.py`
  with a `RunState` object (pure reads: outline position, block cursor,
  completion). `run_inner` decomposes into named phases (resolve state →
  process input → stream blocks → emit transitions → completion tail)
  calling state/recorder/emitter. `RunScriptContextV2` remains the public
  facade during the release cycle.

## Concrete Steps

Per PR: implement → `pytest tests/service/learn/ -q` (277 baseline) →
`pytest tests/golden/ -q` byte-identity → full suite (1,918 baseline) →
uow ratchet + boundary + harness checks → commit.

## Validation and Acceptance

- Golden SSE transcripts byte-identical after every PR (the contract gate).
- Full suite green; learn suite green; new unit tests for emitter payloads
  (PR1), recorder failure paths (PR2, B4-style), and pure-state fixtures
  (PR3).
- Manual dev-env pass after PR3: fresh lesson, continue, interaction, ask,
  abort/resume via the task workspace scripts.

## Idempotence and Recovery

Each PR is a revert-clean unit; no schema changes anywhere. If a PR lands
broken, revert it — the previous PR's state is fully functional.

## Interfaces and Dependencies

- `flaskr/dao/uow.py` (`unit_of_work`, `on_commit`) from B4.
- Golden harness `src/api/tests/golden/` from Phase 0.
- SSE contract: `RunElementSSEMessageDTO` family in `learn_dtos.py`, frozen.
- Consumers unchanged: `runscript_v2.py` keeps calling
  `RunScriptContextV2.run()`.

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
- [ ] PR1: emitter extraction (`learn/run/emitter.py`).
- [ ] PR2: recorder extraction (`learn/run/recorder.py`) with per-step
  `unit_of_work()`; fixes the flush-then-fail dirty-row class.
- [ ] PR3: state extraction (`learn/run/state.py`) + `run_inner` phase
  decomposition into the orchestrator.

## Surprises & Discoveries

(fill as work proceeds)

## Decision Log

- 2026-07-03: The master plan sketched a config-flag parallel path. REJECTED
  in favor of three golden-guarded incremental extraction PRs: a parallel
  rewrite of a 1,056-line `run_inner` is a big-bang inside a batch that the
  4-scenario golden corpus cannot fully discriminate, while each extraction
  PR is independently revertable and keeps one source of truth. The flag
  would also double maintenance for the whole window.
- SSE events are constructed in exactly one place after PR1 (the emitter);
  event names/payload shapes are FROZEN per `learn/AGENTS.md`.

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

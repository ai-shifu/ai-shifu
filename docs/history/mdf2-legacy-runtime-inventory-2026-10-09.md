# MarkdownFlow 1.0 runtime inventory — 2026-10-09

This is a point-in-time dependency inventory against main `9057bb429`, not a
removal plan. The approved scope is **inventory only**. Keep both engines,
fallbacks, shared storage, configuration, and rollback capability unchanged.
Any future deletion or extraction requires a separate decision and current
consumer verification. Enabling 2.0 everywhere does not make these dependencies
unused. The inventory does not include the unmerged Workflow increment #3064.

## Reachable entry paths

Paths below are relative to `src/api/flaskr/service/learn/` unless stated otherwise.

| Trigger | Current call path | Preservation requirement |
| --- | --- | --- |
| Ordinary teaching with `FLOW_ENGINE_V2_ENABLED=true` and a teachable script | `routes.py` → `runscript_v2.run_script` → `_lesson_events` → `agent.lesson_entry.agent_lesson_events` | The 2.0 engine still uses the shared host, element adapter, SSE framing, TTS, and persistence. |
| Deployment flag disabled | `_lesson_events` → `run_script_inner` → `context_v2.RunScriptContextV2` | Retain the functioning 1.0 teaching fallback. |
| 2.0 selected, but lesson resolution raises `LessonNotTeachable` | `_lesson_events` catches it and invokes `run_script_inner` for an ordinary request | This remains reachable even with the deployment flag enabled. `_resolve` raises for a missing course-bound outline or an empty required script. The adapter restores per-update persistence for 1.0. |
| Rewind requested and script unavailable | `_lesson_events` reports `agentRewindUnavailable` | Preserve refusal: falling back would leave the 2.0 session and displayed history on different branches. |
| Follow-up question (`INPUT_TYPE_ASK`) | `_teaches_with_agent` returns false → shared context → `handle_input_ask.py` | ASK remains a sidecar with its own semaphore, even during 2.0 teaching. Its legacy host does not mean course-memory/provider context can be removed. |
| Editor preview with flag enabled and a valid nonempty `debug_session_id` | `routes.py` → `agent.debug_session.stream_debug_preview` | Preserve session-based 2.0 preview. |
| Editor preview without a debug session, or with flag disabled | `routes.py` → `RunScriptPreviewContextV2.stream_preview` | The route deliberately supports older editor bundles and emits `preview_engine=1.0`. Full deployment enablement does not eliminate this path. |

Capacity refusals and input-budget errors have their own error handling; they
are not permission to silently reroute through 1.0. These are source-reachable
paths, not measured production traffic shares. No production log sampling was
performed for this inventory.

## Module responsibilities

| Surface | Classification | Current consumers / reason to retain |
| --- | --- | --- |
| `runscript_v2.py` | Shared host plus engine selection | Routes for both engines; stream lifecycle, locks, cancellation, session cleanup, metering, terminal ordering, and the ASK path. The filename is not an ownership boundary. |
| `context_v2.py` | Mixed legacy execution and shared compatibility | `RunScriptContextV2`, `RunScriptPreviewContextV2`, ASK delegation, and shared `run/state.py` / `run/emitter.py` imports. Do not remove the whole module as a legacy executor. |
| `utils_v2.py` | Shared helpers | Imported by agent lesson recording, follow-up context, ASK, Live follow-ups, text checks, the context, and the emitter. |
| `agent/routing.py` | Active deployment routing | Reads `FLOW_ENGINE_V2_ENABLED`; still used by routes, runscript, context, and follow-up context. The old course-ID allowlist is no longer the routing mechanism. |
| `agent/legacy_protocol.py` | Active 2.0 protocol bridge | Converts agent events to the existing learner interaction/element protocol. Its name does not make it obsolete. |
| `listen_elements.py` and `listen_element_*` | Shared history / stream / persistence | Both engines feed the element infrastructure. Backfill, playback, TTS readiness, and persisted interaction anchors remain coupled to it. |
| `legacy_record_builder.py` / `listen_element_legacy.py` | Historical compatibility, still consumed | Existing history and listen helpers import them. A lack of newly generated 1.0 content would not prove old learners no longer need them. |
| `handle_input_ask.py`, `follow_up_context.py`, and provider adapters | Shared follow-up path | Current-course memory, anchor history, provider dispatch, usage attribution, and privacy protections remain in force. See the [current follow-up contract](../references/follow-up-classroom-context.md). |

Do not infer dead code from static imports alone. At startup,
[`app.py`](../../src/api/app.py) invokes
[`load_plugins_from_dir`](../../src/api/flaskr/framework/plugin/load_plugin.py).
The loader recursively imports Python service modules (with its documented
directory/file exclusions) and invokes injected registration functions. Dynamic
registration, lazy imports, old records, and frontend consumers all matter.

## Persistence and protocol consumers

| Data / contract | Evidence in current source | Consequence |
| --- | --- | --- |
| `learn_generated_blocks` | `agent/lesson_record.py:stage_turn_block` creates the host learning block; `agent/rewind.py` reads blocks and stored turn metadata. | This is current 2.0 storage, not a 1.0-only table. History, follow-ups, usage attribution, dashboards, and admin readers also consume it. |
| `learn_generated_elements` | Element run persistence writes final 2.0 elements; `agent/rewind.py` resolves element anchors to blocks. | Keep history, interaction submission, replay, rewind, and audio binding intact. Intermediate 1.0 snapshots and final 2.0 rows need separate retention reasoning. |
| `learn_progress_records` and `block_position` | `agent/lesson_record.py` writes `block_position=0`; `record_next_lesson_interaction` passes the stored position to host navigation. | Different engine semantics do not establish that the column is unused. Progress, completion, next-lesson unlocking, and compatibility still depend on this model. |
| `learn_agent_sessions` | Agent session store / rewind checkpoint state | Supplements existing host records; it does not replace generated blocks and elements or automatically convert historical 1.0 records. |
| `learn_generated_audios` | `service/tts/models.py:LearnGeneratedAudio` stores `generated_block_bid` and `progress_record_bid`; `audio_record_utils.py` constructs these records. | Audio storage is outside the learning model module. Preserve TTS, subtitles, readiness events, and block associations. |
| Draft / published `flow_engine` columns | `service/shifu/models.py` still defines, copies, and compares them; `shifu_publish_funcs.py` copies the draft value at publication. | Runtime routing ignores these course fields, but that does not authorize deleting their ORM/publish/serialization or schema dependencies. |
| SSE elements and terminal / outline updates | `runscript_v2.py`, listen adapter, learner chat hook | Keep interaction round trips, completion, retry behavior, final persistence before terminal DONE, and audio readiness. A new engine still serves the existing browser protocol. |

Representative frontend consumer:
[`useChatLogicHook.tsx`](../../src/web/src/app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx).
Shared persistence also has dashboard, teacher analytics, admin, billing, and
Live consumers. This inventory is not an exhaustive field-level migration audit.
No table size, retention, or migration mechanism is inferred from old snapshots.

## Reproduction and validation

Run from the repository root in the project Python environment:

```bash
python src/api/scripts/inventory/import_graph.py
rg -n 'LessonNotTeachable|run_script_inner|INPUT_TYPE_ASK' src/api/flaskr/service/learn/runscript_v2.py
rg -n 'debug_session_id|preview_engine|stream_preview' src/api/flaskr/service/learn/routes.py
rg -n 'LearnGeneratedBlock|LearnGeneratedElement' src/api/flaskr/service/learn/agent
rg -n 'block_position|stage_turn_block' src/api/flaskr/service/learn/agent/lesson_record.py
```

The existing import inventory reports 502 project modules, 426 roots (396
plugin-scanned service modules), and 501 reachable modules at this revision.
Those counts describe static import reachability, not executed functions or safe
deletion candidates. The tool includes function-local imports and models plugin
scan roots. The remaining unreachable module is outside this learning inventory.

Existing boundary regressions pass **46 tests**:

```bash
cd src/api
python -m pytest tests/service/learn/test_lesson_routing.py tests/service/learn/test_runscript_inner_boundaries.py -q
```

They cover enabled/disabled routing, ASK sidecar dispatch, no-script fallback,
rewind refusal, fallback persistence, and durability before the terminal event.
This validates existing boundaries; it is not full retirement acceptance or
proof that a later deletion is safe. Repository documentation checks must also
pass when publishing this inventory.

## Questions for a separately approved future change

1. How much real traffic still uses no-script fallback and old-bundle preview?
2. Which context/helper responsibilities can be separated while preserving ASK,
   existing history, TTS, metering, permissions, and old clients?
3. What learner-visible behavior replaces each fallback if retirement is later
   requested? Who accepts that behavior and the rollback tradeoff?
4. What is the complete field-level consumer and historical retention audit,
   including deployment-specific migration, backup, and recovery requirements?

These are investigation questions, not an authorized implementation sequence.
Natural-course quality, independent human feedback, external-provider quality,
and long-term memory/cost acceptance remain separate from this inventory.

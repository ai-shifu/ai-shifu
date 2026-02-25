# LiteLLM Upgrade and Standards Alignment Tasks

Updated: 2026-02-25
Source design: `docs/litellm-upgrade-standards-alignment-design.md`

## Phase 0 - Planning and Baseline

- [x] Create design doc for LiteLLM upgrade, key alignment, and model mapping alignment.
- [x] Identify current non-standard env keys and model prefixes in backend runtime code.
- [x] Verify official LiteLLM latest stable version and provider naming/key conventions.

## Phase 1 - Dependency and Config Contract

- [x] Upgrade `litellm` in `src/api/requirements.txt` to latest stable (`1.81.11`).
- [x] Add LiteLLM-standard env keys in `src/api/flaskr/common/config.py` (`DASHSCOPE_*`, `ZAI_*`, `VOLCENGINE_*`, `DEEPSEEK_API_BASE`).
- [x] Add backward-compatible fallback resolution from legacy keys (`QWEN_*`, `BIGMODEL_API_KEY`, `GLM_API_KEY`, `ARK_API_KEY`, `DEEPSEEK_API_URL`).
- [x] Update config validation rules for "at least one LLM key configured" to include new standard keys.
- [ ] Regenerate env examples with `python scripts/generate_env_examples.py`.

## Phase 2 - LiteLLM Invocation and Model Canonicalization

- [ ] Refactor `src/api/flaskr/api/llm/__init__.py` provider configs to LiteLLM-standard provider naming.
- [ ] Introduce canonical model normalization (`qwen/* -> dashscope/*`, `glm/* -> zai/*`, `ark/* -> volcengine/*`, etc.).
- [ ] Update provider resolution and alias map so both canonical and legacy model IDs resolve correctly.
- [ ] Ensure `/api/llm/model-list` returns canonical LiteLLM-style model IDs.
- [ ] Keep transitional warnings for legacy model IDs and legacy env keys.

## Phase 3 - Script and Test Alignment

- [ ] Update `src/api/scripts/generate_mdflow_context_results.py` to new keys/model conventions with legacy fallback.
- [ ] Update LLM unit tests (`src/api/tests/test_llm.py`, `src/api/tests/test_openai.py`) if affected by canonical model naming.
- [ ] Update configuration integration tests (`src/api/tests/common/test_config_integration.py`) for new key set and fallbacks.
- [ ] Update learning flow tests that assert old prefixes (for example `ark/*`) to canonical prefixes.

## Phase 4 - Verification and Quality Gate

- [ ] Run targeted backend tests for llm/config/learn modules.
- [ ] Run `pre-commit run -a`.
- [ ] Confirm no regression in model selection, default model resolution, and allowlist filtering.
- [ ] Document rollout notes for deployment env migration (legacy -> standard keys).

---

# Listen Mode Refactor Tasks

Updated: 2026-02-20
Source plan: `docs/listen-mode-overall-refactor-execution-plan.md`

## Phase 0 - Stabilize and Instrument

- [x] Wire `onQueueError` from `useQueueManager` into `useListenMode` and surface timeout/error reasons.
- [x] Remove no-op effect in `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/ListenModeRenderer.tsx`.
- [x] Route listen runtime events through a unified in-hook event queue before orchestrator dispatch.
- [x] Add structured logger for listen runtime events (`unitId`, `event`, `fromState`, `toState`, `page`).
- [x] Add one Chrome test log capture template for listen mode debugging.

## Phase 1 - Domain and Parse Extraction

- [ ] Create `src/cook-web/src/c-utils/listen-domain/events.ts`.
- [ ] Create `src/cook-web/src/c-utils/listen-domain/state.ts`.
- [ ] Create `src/cook-web/src/c-utils/listen-domain/reducer.ts`.
- [ ] Create `src/cook-web/src/c-utils/listen-domain/unit-id.ts`.
- [ ] Extract timeline construction from `useListenMode.ts` into `src/cook-web/src/c-utils/listen-parse/timeline-mapper.ts`.
- [ ] Keep one canonical segment pipeline for visual/table split and remove duplicate split logic.
- [ ] Add unit tests for parser/timeline on table-heavy, mixed visual, and multi-position audio content.

## Phase 2 - Orchestrator Shadow Mode

- [ ] Implement `src/cook-web/src/c-utils/listen-runtime/orchestrator.ts`.
- [ ] Implement `src/cook-web/src/c-utils/listen-runtime/queue-driver.ts`.
- [ ] Feed existing queue/audio/interaction events into orchestrator shadow reducer.
- [ ] Add parity logs comparing legacy runtime decision vs orchestrator decision.
- [ ] Define and track parity KPI (target: >=99%).

## Phase 3 - Progression Cutover

- [ ] Route `play/pause/prev/next` to orchestrator commands only.
- [ ] Route `audio ended/error` transitions to orchestrator commands only.
- [x] Remove dual start-index path and keep one entry strategy.
- [ ] Remove direct runtime index guessing from renderer.
- [ ] Verify autoplay after reset, interaction submit, and auto-next.

## Phase 4 - Cleanup and Simplification

- [ ] Split `useListenMode.ts` into focused hooks (`deck`, `runtime`, `interactions`).
- [ ] Remove unused queue actions from `use-queue-manager.ts` runtime contract.
- [ ] Evaluate runtime deprecation/removal of `enqueueAudio` in queue manager API.
- [ ] Consolidate watchdog logic into one `watchdog-policy.ts`.
- [ ] Replace raw `console.*` in queue manager with typed logger or remove.
- [ ] Drive listen runtime eslint warnings to zero.

## Self-Test Checklist (Chrome)

- [ ] Open `http://localhost:8080/c/5c07d6654e55493abdc5c10054d38941?listen=true`.
- [ ] Click reset before starting playback.
- [ ] Compare non-listen vs listen mode visual output parity.
- [ ] Verify audio autoplay starts without manual retry.
- [ ] Verify table pages render correctly and page switching is stable.
- [ ] Verify multi-visual content units display in correct order.

## Exit Criteria

- [ ] No P1/P2 autoplay defects in listen mode.
- [ ] No known table-render mismatch defects in listen mode.
- [ ] No unrecoverable queue stalls in Chrome self-test.
- [ ] Legacy path can be disabled behind feature flag without behavior regression.

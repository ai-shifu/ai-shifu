# LiteLLM Upgrade and Standards Alignment Design

Updated: 2026-02-25
Status: Implemented

## 1. Goal

Align AI-Shifu's LLM integration with LiteLLM's latest stable release and recommended provider conventions:

1. Upgrade `litellm` to the latest stable version.
2. Standardize provider configuration keys to LiteLLM-recommended names.
3. Standardize model naming/calls to LiteLLM-recommended provider prefixes.

## 2. Current State (Repository Baseline)

- Dependency pin: `litellm==1.80.11` in `src/api/requirements.txt`.
- LLM provider wiring is centralized in `src/api/flaskr/api/llm/__init__.py`.
- Current non-standard aliases are widely used:
  - Env keys: `QWEN_API_KEY`, `QWEN_API_URL`, `BIGMODEL_API_KEY`, `ARK_API_KEY`.
  - Model prefixes: `qwen/`, `glm/`, `ark/`.
  - Bare model names: `deepseek-chat`, `gemini-*` (without provider prefix).

## 3. External Baseline (LiteLLM Official, verified 2026-02-25)

- Latest stable package on PyPI: `1.81.11` (released 2026-02-13 UTC).
  A newer pre-release exists: `1.81.12rc1` (released 2026-02-24 UTC).
- Provider naming and key conventions used in official docs:
  - Qwen via Dashscope: `dashscope/<model>`, `DASHSCOPE_API_KEY`, optional `DASHSCOPE_API_BASE`.
  - DeepSeek: `deepseek/<model>`, `DEEPSEEK_API_KEY`.
  - Gemini: `gemini/<model>`, `GEMINI_API_KEY`.
  - Z.AI (Zhipu): `zai/<model>`, `ZAI_API_KEY`.
  - Volcengine: `volcengine/<model>`, `VOLCENGINE_API_KEY`.

## 4. Gap Analysis

| Area | Current | Target (LiteLLM-aligned) |
|---|---|---|
| LiteLLM version | `1.80.11` | `1.81.11` (stable) |
| Qwen key | `QWEN_API_KEY` | `DASHSCOPE_API_KEY` |
| Qwen base | `QWEN_API_URL` | `DASHSCOPE_API_BASE` |
| Qwen model prefix | `qwen/` | `dashscope/` |
| Zhipu key | `BIGMODEL_API_KEY`/`GLM_API_KEY` | `ZAI_API_KEY` |
| Zhipu model prefix | `glm/` | `zai/` |
| Volcengine key | `ARK_API_KEY` | `VOLCENGINE_API_KEY` |
| Volcengine model prefix | `ark/` | `volcengine/` |
| DeepSeek model format | `deepseek-chat` | `deepseek/deepseek-chat` |
| Gemini model format | `gemini-*` | `gemini/gemini-*` |

## 5. Design Decisions

### 5.1 Dependency policy

- Upgrade to latest stable (`1.81.11`), not RC.
- Keep pinning exact version in `requirements.txt` for reproducibility.

### 5.2 Configuration policy

- Introduce LiteLLM-standard env keys in `flaskr/common/config.py`:
  - `DASHSCOPE_API_KEY`, `DASHSCOPE_API_BASE`
  - `ZAI_API_KEY`, `ZAI_API_BASE`
  - `VOLCENGINE_API_KEY`, `VOLCENGINE_API_BASE`
  - `DEEPSEEK_API_BASE` (normalized naming for base override)
- Keep backward compatibility by fallback resolution:
  - `DASHSCOPE_API_KEY <- QWEN_API_KEY`
  - `DASHSCOPE_API_BASE <- QWEN_API_URL`
  - `ZAI_API_KEY <- BIGMODEL_API_KEY <- GLM_API_KEY`
  - `VOLCENGINE_API_KEY <- ARK_API_KEY`
  - `DEEPSEEK_API_BASE <- DEEPSEEK_API_URL`
- Emit startup warnings when legacy keys are used.

### 5.3 Model naming policy

- Define canonical model IDs that follow LiteLLM docs:
  - `dashscope/*`, `deepseek/*`, `gemini/*`, `zai/*`, `volcengine/*`
- Maintain legacy input compatibility through alias normalization before routing:
  - `qwen/* -> dashscope/*`
  - `glm/* -> zai/*`
  - `ark/* -> volcengine/*`
  - `deepseek-chat -> deepseek/deepseek-chat`
  - `gemini-* -> gemini/gemini-*`
- API responses (`/api/llm/model-list`) should return canonical IDs.

### 5.4 Invocation policy

- Update LiteLLM invocation path to use canonical model IDs internally.
- Keep provider-specific param injection only where still required (for custom base URLs or provider-specific optional args).

### 5.5 Scope boundaries

- In scope:
  - `src/api/flaskr/api/llm/__init__.py`
  - `src/api/flaskr/common/config.py`
  - `src/api/scripts/generate_mdflow_context_results.py`
  - LLM/config tests and env example generation.
- Out of scope (this iteration):
  - Dify-specific flow changes.
  - ERNIE provider redesign.
  - One-time DB backfill migration for historical model names (runtime alias compatibility covers behavior).

## 6. Implementation Plan

### Phase A: Compatibility-first refactor

1. Add new standard env keys and fallback resolution helpers.
2. Keep old keys as deprecated aliases.
3. Implement canonical model normalization + alias map.
4. Switch provider configs and model listing to canonical IDs.

### Phase B: Validation and tooling

1. Update config validation (`at least one LLM key` logic) to include new keys.
2. Regenerate env examples via `python scripts/generate_env_examples.py`.
3. Update scripts/tests expecting old key/model formats.

### Phase C: Operational cleanup

1. Add deprecation warnings in logs for old keys/model IDs.
2. Document migration guidance for deployment `.env` files.

## 7. Risks and Mitigations

- Risk: Existing deployment only sets legacy keys.
  Mitigation: fallback chain preserves behavior; warn instead of break.
- Risk: Existing course/default model values use old aliases.
  Mitigation: runtime canonicalization before `get_litellm_params_and_model`.
- Risk: allowlist mismatch (`LLM_ALLOWED_MODELS`) after canonical switch.
  Mitigation: normalize configured allowlist entries before matching.

## 8. Acceptance Criteria

1. `litellm` pin is upgraded to latest stable.
2. Standard keys are accepted and work without legacy aliases.
3. Legacy keys/models still work during transition with warnings.
4. `/api/llm/model-list` returns canonical LiteLLM-style model IDs.
5. Existing LLM tests pass with updated expected values.

## 9. Reference Sources

- PyPI package metadata (`litellm`): https://pypi.org/pypi/litellm/json
- LiteLLM Providers index: https://docs.litellm.ai/docs/providers
- LiteLLM Dashscope (Qwen): https://docs.litellm.ai/docs/providers/dashscope
- LiteLLM DeepSeek: https://docs.litellm.ai/docs/providers/deepseek
- LiteLLM Gemini (Google AI Studio): https://docs.litellm.ai/docs/providers/gemini
- LiteLLM Z.AI: https://docs.litellm.ai/docs/providers/z_ai
- LiteLLM Volcengine: https://docs.litellm.ai/docs/providers/volcengine

## 10. Rollout Notes

### 10.1 Environment variable migration

Prefer these standard keys in deployment env files:

- `DASHSCOPE_API_KEY` (legacy fallback: `QWEN_API_KEY`)
- `DASHSCOPE_API_BASE` (legacy fallback: `QWEN_API_URL`)
- `ZAI_API_KEY` (legacy fallback: `BIGMODEL_API_KEY`, `GLM_API_KEY`)
- `ZAI_API_BASE`
- `VOLCENGINE_API_KEY` (legacy fallback: `ARK_API_KEY`)
- `VOLCENGINE_API_BASE`
- `DEEPSEEK_API_BASE` (legacy fallback: `DEEPSEEK_API_URL`)

### 10.2 Model ID migration

Canonical model IDs returned by `/api/llm/model-list` are now:

- `dashscope/*` (legacy accepted: `qwen/*`)
- `zai/*` (legacy accepted: `glm/*`)
- `volcengine/*` (legacy accepted: `ark/*`)
- `deepseek/*` (legacy accepted: bare `deepseek-chat` style)
- `gemini/*` (legacy accepted: bare `gemini-*` style)

### 10.3 Operational behavior

- Legacy keys and legacy model IDs remain compatible in runtime.
- Backend logs emit migration warnings when legacy keys or model IDs are used.
- Existing persisted legacy model values do not require DB migration in this iteration.

---
title: Route text models by LiteLLM's rules
status: active
owner_surface: backend
last_reviewed: 2026-11-20
---

# Route text models by LiteLLM's rules

## Purpose / Big Picture

A new operator should only need LiteLLM's documentation: set `LLM_MODEL_1_ID`
to a LiteLLM model ID such as `dashscope/qwen-max`,
`anthropic/claude-sonnet-4-5` or `openrouter/openai/gpt-4o`, and set that
provider's LiteLLM environment variables. Any provider LiteLLM supports then
works without AI-Shifu code changes.

Earlier AI-Shifu variable names and model prefixes keep working for a
compatibility period, isolated in one module that can be deleted without
touching anything else.

## Progress

- [x] 2026-11-20 10:00 UTC: Audit provider configs, env declarations, startup
  validation, model slots, Gemini Live/TTS reads, billing identity and
  LiteLLM 1.109.1 provider names and env lookups.
- [x] 2026-11-20 13:00 UTC: Replace the provider table with LiteLLM routing in
  `flaskr/common/llm_routing.py`; register Qianfan and SiliconFlow with
  LiteLLM; isolate legacy handling in `flaskr/common/legacy_llm_compat.py`.
- [x] 2026-11-20 14:00 UTC: Rename LLM rate providers by migration
  `a3c5e7f9b1d2`; let settlement fall back to the provider the usage model
  resolves to.
- [x] 2026-11-20 15:00 UTC: Migrate tests, add routing, compat, settlement and
  migration coverage, update docs and `docker/.env.example.full`.
- [ ] Verify with real provider credentials in a test environment, including
  one Qianfan and one SiliconFlow model.
- [ ] End the compatibility period: delete `legacy_llm_compat.py`,
  `tests/test_legacy_llm_compat.py`, its uses in `llm_routing.py` and the
  "Upgrading to LiteLLM model configuration" section of `INSTALL_MANUAL.md`.

## Surprises & Discoveries

- LiteLLM 1.109.1 `openai_like` serves embeddings only; `completion()` rejects
  it. It cannot carry an OpenAI-compatible chat provider.
- LiteLLM 1.109.1 has a native `bigmodel` provider (`BIGMODEL_API_KEY`,
  `BIGMODEL_API_BASE`, default `open.bigmodel.cn`), so the legacy `glm/`
  prefix maps there; `zai` is Zhipu's international endpoint.
- Neither Qianfan nor SiliconFlow ships in LiteLLM 1.109.1, 1.110.2 or `main`.
  Upstream requests stalled without review (BerriAI/litellm#8263, #12888,
  #15589, #27299); BerriAI/litellm#29332 (SiliconFlow) and #49777 (Qianfan)
  are open. LiteLLM's JSON provider registry accepts the same entry shape
  those proposals add, so AI-Shifu registers them at import.
- `litellm.get_llm_provider` prints a provider-list banner on every miss, and
  cannot infer some bare registry names such as `deepseek-chat`. Routing
  checks the provider list or the registry entry's `litellm_provider` first.
- `litellm.validate_environment` reports nothing for `bigmodel` and `zai`;
  routing checks their key variables directly.
- Bare `gemini-*` IDs resolve to Vertex AI in LiteLLM. Compat rewrites them to
  `gemini/` so existing slots stay on the Gemini API key.
- LiteLLM's DeepSeek default base is `https://api.deepseek.com/beta`; the old
  AI-Shifu default was `https://api.deepseek.com`. Deployments that need the
  stable base set `DEEPSEEK_API_BASE`.
- Settlement looks up rates by the provider stored on each usage record, so
  records written before the rename would miss renamed rates.

## Decision Log

- LiteLLM's provider name is the routing, billing and usage identity. Rate rows
  are renamed `qwen`->`dashscope`, `glm`->`bigmodel`, `ark`->`volcengine`,
  `ernie_v2`->`qianfan`, `silicon`->`siliconflow` (user decision,
  2026-11-20). Historical usage records keep their stored provider.
- Qianfan and SiliconFlow are registered LiteLLM providers named as upstream
  proposes (`qianfan`, `siliconflow`; `QIANFAN_API_KEY`,
  `SILICONFLOW_API_KEY`). Registration skips any name LiteLLM already ships, so
  a LiteLLM upgrade that adds them takes over automatically (user decision,
  2026-11-20, after `openai_like` proved chat-incapable).
- AI-Shifu never passes API keys or base URLs to LiteLLM except values that
  only legacy variables supply. Compat never writes `os.environ`.
- No per-provider `/models` discovery. Only Gemini discovery remains, because
  Gemini Live and capability filtering need `supportedGenerationMethods`.
- Startup requires `LLM_MODEL_1_ID` to be routable with its provider's
  credentials present, instead of "any one known key is set".
- Settlement accepts the provider the usage model resolves to as a fallback
  identity, so in-flight and replayed pre-rename records still match.

## Outcomes & Retrospective

Routing, compat, billing rename and docs are complete and covered offline; the
full backend suite passes. Deployed verification with real credentials and
the end of the compatibility period remain.

## Context and Orientation

- `src/api/flaskr/common/llm_routing.py`: `resolve_route(model)` returns an
  `LLMRoute(provider, model, api_base, missing_credentials, credentials)` or
  `None`; `register_extra_providers()`; `env_value(name)`. Free of Flask and
  database imports because startup validation uses it.
- `src/api/flaskr/common/legacy_llm_compat.py`: legacy model prefixes, bare-name
  rewrites, legacy env names and deprecation warnings. Only `llm_routing.py`
  imports it.
- `src/api/flaskr/api/llm/__init__.py`: `get_litellm_params_and_model`,
  request policies keyed by LiteLLM provider names, Gemini discovery.
- `src/api/flaskr/common/config.py`: LiteLLM-named env declarations and the
  model 1 startup check.
- `src/api/flaskr/service/billing/charges.py`: settlement provider fallback.
- `src/api/migrations/versions/a3c5e7f9b1d2_rename_llm_rate_providers_to_litellm.py`.

## Plan of Work

Implemented as described in Progress. Remaining work is deployment
verification and, later, deleting the compat layer.

## Concrete Steps

```bash
cd src/api && python -m pytest -q tests/test_llm_routing.py \
  tests/test_legacy_llm_compat.py tests/test_llm.py \
  tests/migrations/test_litellm_rate_provider_migration.py
cd src/api && python scripts/generate_env_examples.py
```

## Validation and Acceptance

- `openrouter/anthropic/claude-sonnet-4.5` with `OPENROUTER_API_KEY` starts
  the service and reaches LiteLLM on `openrouter`; without the key startup
  fails naming `OPENROUTER_API_KEY`.
- `siliconflow/...` and `qianfan/...` reach `/chat/completions` with their
  LiteLLM-named keys (covered against a local server).
- An existing `.env` with `QWEN_API_KEY` and `LLM_MODEL_1_ID=qwen/qwen-max`
  keeps working and logs deprecation warnings naming `DASHSCOPE_API_KEY` and
  `dashscope/qwen-max`.
- A usage record stored with provider `qwen` settles against a `dashscope`
  rate.

## Idempotence and Recovery

The migration skips rows whose renamed identity already exists and is safe to
rerun; downgrade renames back with the same guard. Reverting the code without
downgrading leaves rates under LiteLLM names, which the old code would not
match, so roll back code and migration together.

## Interfaces and Dependencies

LiteLLM 1.109.1: `provider_list`, `model_cost`, `get_llm_provider`,
`validate_environment`, and the private `JSONProviderRegistry._providers`
(guarded by `tests/test_llm_routing.py`). Removed: `ProviderConfig`,
`ProviderState`, `PROVIDER_STATES`, `MODEL_ALIAS_MAP`,
`LITELLM_PROVIDER_CONFIGS`, `LLM_PROVIDER_API_KEY_ENVS`.

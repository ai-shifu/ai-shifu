# Follow-up (Ask) Model Exposure + Provider Config Design

## 1. Background

The current ask runtime already supports dedicated ask LLM fields in backend models (`ask_llm`, `ask_llm_temperature`, `ask_llm_system_prompt`, `ask_enabled_status`), and these fields are consumed in `handle_input_ask`.

Current gaps:

1. Ask model settings are not exposed in Shifu settings UI.
2. Shifu detail DTO/API do not expose or accept ask-specific settings.
3. Ask cannot be configured to use external knowledge providers (Dify, Coze) in a unified way.

## 2. Design Decision

Use a **hybrid** approach:

1. Keep existing ask LLM fields unchanged for compatibility and fallback.
2. Add **one common field**: `ask_provider_config`.
3. Put provider routing mode inside `ask_provider_config` (not a separate DB field):
   - `provider_only`
   - `provider_then_llm`
4. Use provider-specific `json_schema` (similar to TTS config) to drive both frontend form rendering and backend validation.

## 3. Goals and Non-Goals

### 3.1 Goals

1. Expose ask model settings in Shifu settings.
2. Introduce provider-driven ask configuration through one generic field.
3. Support Dify/Coze/Volcengine Knowledge Base/LLM with a unified runtime interface.
4. Keep backward compatibility for existing ask behavior.

### 3.2 Non-Goals

1. Rebuild full generic RAG for all flows.
2. Add provider secret input UI in this phase.
3. Redesign lesson-level authoring experience in this phase.

## 4. Data Model Design

### 4.1 Keep existing fields

No semantic change for:

1. `ask_enabled_status`
2. `ask_llm`
3. `ask_llm_temperature`
4. `ask_llm_system_prompt`

### 4.2 Add common provider config field

Add to `DraftShifu` and `PublishedShifu`:

1. `ask_provider_config` (JSON or `TEXT` storing JSON, default `{}`)

Recommended normalized shape:

```json
{
  "provider": "llm|dify|coze|volc_knowledge",
  "mode": "provider_only|provider_then_llm",
  "config": {}
}
```

Notes:

1. `mode` lives in `ask_provider_config` as requested.
2. `config` is provider-specific payload validated by provider schema.
3. Provider connection values (for example `api_key`) are stored per shifu in this field.

### 4.3 Provider secret strategy

Provider connection settings are persisted at shifu level inside
`ask_provider_config.config`:

1. Dify: `base_url`, `api_key`
2. Coze: `base_url`, `api_key`, `bot_id` (plus optional fields)
3. Volcengine Knowledge Base: `account_id`, `ak`, `sk`, `collection_name` (plus optional fields)

Notes:

1. Ask provider runtime does not read Dify/Coze/Volcengine credentials from `.env`.
2. Volcengine Knowledge Base request signing uses internal SigV4 logic in adapter code (no dedicated Volcengine SDK dependency required for ask provider routing).
3. Existing global env keys can remain for other legacy flows, but are not used by ask provider routing.

## 5. Schema-Driven Config (TTS-like)

Introduce ask-provider metadata endpoint (similar to TTS config pattern):

1. `GET /api/shifu/ask/config`

Returned data contains:

1. Provider list
2. Default values
3. `json_schema` for each provider config
4. Optional UI hints (`title`, `description`, field order)
5. Sensitive fields can use schema format hints (for example `api_key` with `format: password`) for masked inputs

Backend validation path:

1. Parse `ask_provider_config`
2. Resolve `provider`
3. Validate `mode` enum
4. Validate `config` against selected provider `json_schema`

## 6. API Contract Changes

### 6.1 Shifu detail response

Extend `ShifuDetailDto` with:

1. `ask_enabled_status`
2. `ask_model` (`ask_llm`)
3. `ask_temperature` (`ask_llm_temperature`)
4. `ask_system_prompt` (`ask_llm_system_prompt`)
5. `ask_provider_config` (JSON object)

### 6.2 Shifu detail save request

Extend `POST /api/shifu/shifus/{shifu_bid}/detail` payload with same ask fields.

Validation rules:

1. `ask_temperature`: `0.0 - 2.0`
2. `ask_provider_config.provider`: supported enum
3. `ask_provider_config.mode`: `provider_only|provider_then_llm`
4. `ask_provider_config.config`: valid against selected provider schema

### 6.3 Backward compatibility

If `ask_provider_config` is missing or empty:

1. Provider defaults to `llm`
2. Existing ask behavior remains unchanged

## 7. Frontend Design

Update `src/cook-web/src/components/shifu-setting/ShifuSetting.tsx`:

1. Add ask section fields:
   - Ask enable status
   - Ask model
   - Ask temperature
   - Ask system prompt
2. Add provider section driven by `/api/shifu/ask/config`:
   - Provider selector
   - Mode selector (stored in `ask_provider_config.mode`)
   - Dynamic provider form rendered from `json_schema`
3. Save all provider settings into one object field: `ask_provider_config`.

i18n:

1. Add keys in `src/i18n/en-US/modules/shifu-setting.json`
2. Add keys in `src/i18n/zh-CN/modules/shifu-setting.json`

## 8. Ask Runtime Routing

### 8.1 Follow-up info extension

Extend `FollowUpInfo` to include:

1. `ask_provider_config`

### 8.2 Routing behavior

Runtime routing by `ask_provider_config.provider`:

1. `llm`: built-in `llm` provider adapter path
2. `dify|coze|volc_knowledge`: external provider adapter paths

Mode handling by `ask_provider_config.mode`:

1. `provider_only`: provider failure returns provider error
2. `provider_then_llm`: provider failure/empty response falls back to `ask_llm`

### 8.3 Full decoupling (handler architecture)

Ask runtime handlers are fully decoupled by provider:

1. Keep a dedicated adapter file per provider (`llm`, `dify`, `coze`, `volc_knowledge`).
2. Route only through one registry entrypoint (`stream_ask_provider_response`).
3. Inject runtime-only dependencies (for example `chat_llm` stream factory) via adapter runtime context, not hardcoded branches in `handle_input_ask`.
4. Ensure fallback to `llm` still goes through the same provider adapter chain.

## 9. Observability

Add logs and trace metadata:

1. provider
2. mode
3. fallback reason
4. provider latency/error code

Metering:

1. Keep existing token metering for LLM path
2. Add request/latency metrics for provider path

## 10. Security and Reliability

1. Provider connection fields are managed per shifu in `ask_provider_config`.
2. Keep existing risk check for user ask input.
3. Enforce provider timeout and error handling.
4. Respect mode:
   - `provider_only`: fail fast with i18n error
   - `provider_then_llm`: transparent fallback

## 11. Migration Plan

1. Add DB migration for `ask_provider_config` in Shifu draft/published tables.
2. Extend DTO and save/load mapping.
3. Add ask config metadata endpoint and schema registry.
4. Implement provider adapters + runtime routing.
5. Update frontend with schema-driven form.

Feature flag:

1. Add `ASK_PROVIDER_ENABLED` (default `false`)
2. If disabled, force `provider=llm`

## 12. Test Plan

### 12.1 Backend

1. DTO and persistence tests for `ask_provider_config`
2. Schema validation tests (provider/mode/config)
3. Routing tests:
   - `provider=llm`
   - `provider=dify|coze|volc_knowledge` + `provider_only`
   - `provider_then_llm` fallback

### 12.2 Frontend

1. Ask config endpoint load + dynamic form rendering
2. Form save payload correctness (`ask_provider_config`)
3. i18n display tests

### 12.3 End-to-end

1. Ask with `provider=llm`
2. Ask with external provider success
3. Provider failure with fallback mode
4. Provider failure in provider-only mode

## 13. Open Questions

1. Should outline-level ask override also support provider config in phase-1?
2. Do we need a schema version key inside `ask_provider_config` for future migration?
3. Should `provider=llm` explicitly require `mode`, or allow implicit default?

# Follow-up Ask: Model Exposure + Third-Party KB Support

## Documentation

- [x] Create design document for ask model exposure and third-party KB integration (`docs/follow-up-model-and-kb-design.md`).
- [x] Create executable task breakdown with done/todo status.

## Backend: Data Model and Migration

- [x] Add `ask_provider_config` column to `DraftShifu` and `PublishedShifu` (JSON or TEXT JSON).
- [x] Set default empty object for `ask_provider_config` and handle legacy null values.
- [x] Generate and review Alembic migration for `ask_provider_config`.
- [x] Ensure model clone/eq/json helpers include new fields.

## Backend: DTO and Route Contract

- [x] Extend `ShifuDetailDto` to expose ask model fields (`ask_enabled_status`, `ask_model`, `ask_temperature`, `ask_system_prompt`).
- [x] Extend `ShifuDetailDto` to expose `ask_provider_config`.
- [x] Update `get_shifu_draft_info` response mapping for all ask fields.
- [x] Update `save_shifu_draft_info` signature and persistence for all ask fields.
- [x] Update `save_shifu_detail_api` request parsing + validation for ask fields + `ask_provider_config`.
- [x] Update swagger docs for `GET/POST /api/shifu/shifus/{shifu_bid}/detail`.

## Backend: Publish and Import/Export

- [x] Ensure draft -> published copy path includes `ask_provider_config`.
- [x] Extend shifu import/export payload to include `ask_provider_config`.
- [x] Add backward-compatible defaults when imported data does not contain new fields.

## Backend: Ask Runtime Routing

- [x] Extend `FollowUpInfo` to carry `ask_provider_config`.
- [x] Add ask provider schema registry (provider list + json_schema + defaults).
- [x] Add ask config metadata API (`GET /api/shifu/ask/config`) similar to TTS config style.
- [x] Add provider adapter interface for ask KB streaming.
- [x] Implement Dify ask provider adapter.
- [x] Implement Coze ask provider adapter.
- [x] Implement Volcengine Knowledge Base ask provider adapter.
- [x] Replace Volcengine SDK-based signing with internal SigV4 implementation in `volc_knowledge` adapter.
- [x] Fully decouple ask provider handlers (split by provider module and include `llm` as default provider adapter).
- [x] Add routing in `handle_input_ask` by `ask_provider_config.provider`.
- [x] Support mode in `ask_provider_config.mode`:
- [x] `provider_only`
- [x] `provider_then_llm` fallback to ask_llm
- [x] Preserve existing ask persistence and SSE output format.
- [x] Add timeout and fallback handling with i18n error messages.

## Backend: Configuration and Security

- [x] Keep Dify/Coze/Volcengine Knowledge Base connection settings in shifu-level `ask_provider_config` (not required from `.env` in ask runtime).
- [x] Add `ASK_PROVIDER_ENABLED` feature flag and default to disabled.
- [x] Ensure ask provider runtime reads provider connection fields from `ask_provider_config.config`.

## Frontend: Shifu Settings UI

- [x] Extend Shifu setting form schema to include ask model fields.
- [x] Add UI controls for ask mode/model/temperature/system prompt.
- [x] Add provider selector + mode selector and dynamic provider form by json_schema.
- [x] Render sensitive ask provider fields (for example `api_key`) as password inputs via schema format.
- [x] Map API response -> form initial values for `ask_provider_config`.
- [x] Map form submit -> API payload for `ask_provider_config`.
- [x] Add frontend validation driven by provider schema.

## i18n

- [x] Add `en-US` translation keys for new ask/provider settings labels and hints.
- [x] Add `zh-CN` translation keys for new ask/provider settings labels and hints.
- [x] Run translation validation scripts and fix missing keys/usages.

## Testing

- [x] Add backend tests for shifu detail save/get with `ask_provider_config`.
- [x] Add backend tests for ask routing by `provider` and `mode`.
- [x] Add provider adapter unit tests (success/timeout/error).
- [x] Add frontend tests for Shifu settings ask/provider schema-driven form behavior.
- [x] Run relevant test suites and confirm pass.

## Quality Gates

- [x] Run `pre-commit run`.
- [x] Run backend targeted tests under `src/api/tests/service/shifu` and `src/api/tests/service/learn`.
- [x] Run frontend lint/type-check for `src/cook-web`.
Status note: `npm run lint` passes (warnings only). `npx tsc --noEmit` passes after restoring local dependency `swr` and excluding local untracked `src/c-utils/listen-parse/*` during the check.

## Rollout

- [ ] Enable behind feature flag in non-production environment.
- [ ] Perform manual verification for Dify/Coze/Volcengine Knowledge Base one by one.
- [ ] Collect logs/metrics for provider distribution and fallback rate.
- [ ] Enable in production after acceptance.

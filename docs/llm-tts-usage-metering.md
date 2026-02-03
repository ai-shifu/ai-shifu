# Unified LLM & TTS Usage Metering

## Goals
- Persist per-invocation usage for LLM (token counts) and TTS (text length + audio duration) in a single, queryable table.
- Support billing aggregation by user, shifu, course/session, and time window.
- Keep recording best-effort and non-blocking for production flows.

## Non-Goals
- Full billing pipeline (pricing, invoices, refunds) and UI.
- Retroactive backfill of historical usage (optional follow-up).

## Current Code Paths (Observed)
- LLM streaming is centralized in `src/api/flaskr/api/llm/__init__.py` (`invoke_llm`, `chat_llm`).
  - LiteLLM returns usage via `res.usage` when `stream_options.include_usage` is enabled.
  - Dify streaming has no usage payload.
- TTS providers return `TTSResult` (`duration_ms`, `word_count`) in `src/api/flaskr/api/tts/*`.
- TTS orchestration lives in:
  - `src/api/flaskr/service/learn/learn_funcs.py`
  - `src/api/flaskr/service/tts/streaming_tts.py`
  - `src/api/flaskr/service/tts/pipeline.py`

## Proposed Data Model

### Table: `billing_usage_records`
Single table for both LLM and TTS usage. The schema is intentionally wide to keep billing queries simple and fast.

Core identifiers
- `id` BIGINT PK
- `usage_bid` String(36), indexed, unique business identifier
- `usage_type` SmallInteger (1=LLM, 2=TTS)
- `record_level` SmallInteger (0=request, 1=segment)
- `parent_usage_bid` String(36), indexed (group segment records under a request)
- `usage_scene` SmallInteger (0=debug, 1=preview, 2=production)

Context fields (all indexed)
- `user_bid` String(36)
- `shifu_bid` String(36)
- `outline_item_bid` String(36)
- `progress_record_bid` String(36)
- `generated_block_bid` String(36)
- `audio_bid` String(36)
- `request_id` String(64) (from `X-Request-ID`)
- `trace_id` String(64) (Langfuse trace id if available)

Provider fields
- `provider` String(32)
- `model` String(100)
- `is_stream` SmallInteger

Usage metrics (unified naming for input/output/total)
- LLM: `input`, `output`, `total` represent tokens
- TTS: `input`, `output`, `total` represent chars (input/output/total)
- TTS extras: `word_count`, `duration_ms`
- Shared: `latency_ms`, `segment_index`, `segment_count`

Lifecycle & metadata
- `billable` SmallInteger (0/1)
- `status` SmallInteger (0=success, 1=failed)
- `error_message` Text
- `metadata` JSON (temperature, voice settings, usage_source, etc.)
- `deleted` SmallInteger
- `created_at`, `updated_at`

Recommended indexes
- `(user_bid, created_at)`
- `(shifu_bid, created_at)`
- `(usage_type, created_at)`
- `(request_id)`

## Recording Flow

### LLM
Where
- `invoke_llm` and `chat_llm` in `src/api/flaskr/api/llm/__init__.py`.

How
- Capture `ModelUsage` after the stream completes.
- Record one `billing_usage_records` row per LLM invocation.
- For Dify (no usage), write `input=0`, `output=0`, and set `metadata.usage_source="missing"`.

Notes
- Ensure `stream_options={"include_usage": True}` is enabled for both `invoke_llm` and `chat_llm`.
- Set `billable=0` for preview/editor/debug flows.

### TTS
Where
- Per-provider calls are made via `synthesize_text()` in TTS flows:
  - `learn_funcs.py` (generated block audio + preview)
  - `streaming_tts.py` (streamed segments)
  - `pipeline.py` (long text pipeline)

How
- Record per segment (each `synthesize_text` call) with `record_level=segment`.
- Create an optional parent request record with `record_level=request`, storing totals:
  - `input` = len(cleaned_text)
  - `duration_ms` = total duration across segments
  - `segment_count` = number of segments

Notes
- Use `TTSResult.word_count` as provider-reported word count (may be `len(text)` in some providers).
- Always store `input` derived from the cleaned text for consistency.
- Preview flows set `billable=0`.

## Usage Recorder Service
Introduce a small service module to centralize writes and keep call sites clean.

Suggested module
- `src/api/flaskr/service/metering/`

Core API
- `record_llm_usage(app, context, usage, metadata)`
- `record_tts_usage(app, context, metrics, metadata)`

Behavior
- Best-effort write; never raise to caller.
- Optional async mode (queue + background thread) if write latency is a concern.

## Billing Aggregation (Examples)
- Per-user daily usage:
  - SUM `total` (LLM, tokens)
  - SUM `input` / `duration_ms` (TTS, chars)
- Per-shifu usage window for creator billing.

Pricing can be layered later via:
- Config-based pricing rules, or
- A `billing_pricing_rules` table keyed by provider/model.

## Rollout Plan (High Level)
1. Add `billing_usage_records` model + migration.
2. Add `metering` service with `UsageContext` and record helpers.
3. Instrument LLM flows.
4. Instrument TTS flows (segment + request totals).
5. Add tests (unit + integration).
6. Add reporting endpoints/queries for finance.

# Listen Mode Duplication Audit (Backend AV/TTS)

Updated: 2026-02-23

## 1. Scope

This document audits duplicated and overlapping implementation in backend Listen Mode / AV TTS flow.

Primary scope:

- `src/api/flaskr/service/learn/learn_funcs.py`
- `src/api/flaskr/service/learn/routes.py`
- `src/api/flaskr/service/learn/context_v2.py`
- `src/api/flaskr/service/tts/streaming_tts.py`
- `src/api/flaskr/service/tts/pipeline.py`
- `src/api/flaskr/service/tts/boundary_strategies.py`

## 2. What Has Already Been Deduplicated

The following major duplication has already been cleaned:

1. Unified SSE payload line formatting via `_to_sse_data_line` in `src/api/flaskr/service/learn/routes.py:49`.
2. Unified TTS usage metadata/recording helpers in `src/api/flaskr/service/learn/learn_funcs.py:750`, `src/api/flaskr/service/learn/learn_funcs.py:762`, `src/api/flaskr/service/learn/learn_funcs.py:797`.
3. Unified audio event builders in `src/api/flaskr/service/learn/learn_funcs.py:834`, `src/api/flaskr/service/learn/learn_funcs.py:863`.
4. Unified stream segment loop in `src/api/flaskr/service/learn/learn_funcs.py:891` and reused by AV/non-AV/preview paths.
5. Removed dead preview finalize APIs from `AVStreamingTTSProcessor` and `StreamingTTSProcessor`.
6. Consolidated visual-kind constant sets in `src/api/flaskr/service/tts/streaming_tts.py:85`.
7. Consolidated close-tag search helper `_find_close_end` in `src/api/flaskr/service/tts/boundary_strategies.py:30`.

## 3. Execution Status (2026-02-23)

All planned items in DUP-01 ~ DUP-07 have been implemented.

## DUP-01 (P0) Resolved: Audio Persistence Payload Duplication

- Implemented shared audio record helper:
  - `src/api/flaskr/service/tts/audio_record_utils.py:21`
  - `src/api/flaskr/service/tts/audio_record_utils.py:64`
- Replaced duplicated persistence paths:
  - `src/api/flaskr/service/learn/learn_funcs.py:817`
  - `src/api/flaskr/service/tts/streaming_tts.py:547`

## DUP-02 (P0) Resolved: AV Boundary Detection Logic

- Added unified boundary scanner:
  - `src/api/flaskr/service/tts/pipeline.py:337`
- Reused in contract generation:
  - `src/api/flaskr/service/tts/pipeline.py:477`
- Reused in runtime streaming processor:
  - `src/api/flaskr/service/tts/streaming_tts.py:962`

## DUP-03 (P1) Resolved: Repeated SSE Generator Wrappers

- Added shared SSE stream wrapper:
  - `src/api/flaskr/service/learn/routes.py:54`
- Applied to preview, generated-block TTS, and preview TTS routes:
  - `src/api/flaskr/service/learn/routes.py:368`
  - `src/api/flaskr/service/learn/routes.py:638`
  - `src/api/flaskr/service/learn/routes.py:693`

## DUP-04 (P1) Resolved: `UsageContext` Construction

- Added shared context builder:
  - `src/api/flaskr/service/learn/learn_funcs.py:766`
- Applied in AV/non-AV/preview streaming flows:
  - `src/api/flaskr/service/learn/learn_funcs.py:1183`
  - `src/api/flaskr/service/learn/learn_funcs.py:1276`
  - `src/api/flaskr/service/learn/learn_funcs.py:1385`

## DUP-05 (P2) Resolved: TTS Stream Finalization Flow

- Added shared stream finalize helper:
  - `src/api/flaskr/service/learn/learn_funcs.py:791`
- Applied in AV/non-AV/preview flows:
  - `src/api/flaskr/service/learn/learn_funcs.py:1216`
  - `src/api/flaskr/service/learn/learn_funcs.py:1312`
  - `src/api/flaskr/service/learn/learn_funcs.py:1418`

## DUP-06 (P2) Resolved: Slide DTO Construction Overlap

- Added unified slide factory/registry helpers:
  - `src/api/flaskr/service/tts/streaming_tts.py:737`
  - `src/api/flaskr/service/tts/streaming_tts.py:765`
- Reused by visual head/finalized/fallback slide paths.

## DUP-07 (P2) Resolved: Repeated TTS Error Mapping

- Added shared error mapping wrapper:
  - `src/api/flaskr/service/learn/learn_funcs.py:841`
- Applied in AV/non-AV/preview flows:
  - `src/api/flaskr/service/learn/learn_funcs.py:1257`
  - `src/api/flaskr/service/learn/learn_funcs.py:1350`
  - `src/api/flaskr/service/learn/learn_funcs.py:1452`

## 4. Constraints to Keep During Refactor

1. Do not change SSE event contracts (`audio_segment`, `audio_complete`, `new_slide`) shape.
2. Preserve AV `position` semantics and ordering.
3. Preserve preview endpoint behavior that emits `PreviewSSEMessageType.ERROR` instead of raising raw exceptions.
4. Preserve DB commit semantics where streaming path intentionally uses `flush` before outer commit.
5. Preserve slide-binding invariant: only positions that emitted audio events should force finalized slide emission.

## 5. Recommended Execution Order

1. DUP-01 and DUP-02 first (highest regression-prevention value).
2. DUP-03 and DUP-04 next (low-risk structure cleanup).
3. DUP-05 to DUP-07 last (medium/low impact, readability and maintainability gains).

## 6. Acceptance Criteria for This Audit

1. Every duplication item has concrete file anchors.
2. Each item includes risk and consolidation direction.
3. Priority order is explicit so implementation can proceed incrementally.

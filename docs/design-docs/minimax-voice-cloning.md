---
title: MiniMax Voice Cloning
status: proposed
owner_surface: shared
last_reviewed: 2026-06-18
canonical: true
---

# MiniMax Voice Cloning

## Background

AI-Shifu already supports per-course TTS settings through
`tts_provider`, `tts_model`, `tts_voice_id`, `tts_speed`, `tts_pitch`, and
`tts_emotion` on draft and published Shifu records. Runtime synthesis already
passes `tts_voice_id` into the MiniMax `voice_setting.voice_id` field through
`src/api/flaskr/api/tts/minimax_provider.py`, so cloned MiniMax voices can use
the existing preview, streaming, listen-mode, generated-audio persistence, and
metering paths once a valid custom `voice_id` reaches the TTS provider.

The current product gap is creation and selection of cloned voices. The current
backend and frontend treat MiniMax voices as a fixed list exposed by provider
config, and `validate_tts_settings_strict` rejects a MiniMax `voice_id` that is
not in that fixed list. The Shifu setting UI also resets unknown voice IDs to
the first built-in voice when TTS is enabled.

MiniMax's voice cloning workflow has three provider calls:

1. Upload source audio to `/v1/files/upload` with `purpose=voice_clone`.
2. Optionally upload prompt audio to `/v1/files/upload` with
   `purpose=prompt_audio`.
3. Call `/v1/voice_clone` with `file_id`, a custom `voice_id`, optional
   `clone_prompt`, preview `text`, and preview `model`.

The cloned `voice_id` is then used directly by MiniMax T2A requests.

## Goals

- Let course authors create a MiniMax cloned voice from the Shifu setting TTS
  area without leaving AI-Shifu.
- Make in-browser live recording the primary source-audio path, with file
  upload as a fallback.
- Require creator credit admission and credit deduction for billable voice
  clone attempts.
- Let authors select a cloned MiniMax voice for a course and save it as
  `tts_voice_id`.
- Keep existing TTS runtime, preview, segmentation, storage, subtitle, and
  usage-recording behavior unchanged.
- Support manually entering an existing MiniMax custom `voice_id` for cases
  where the voice was created outside AI-Shifu.
- Persist enough local metadata to show cloned voices, diagnose failures, avoid
  duplicate custom IDs, and prevent accidental local deletion.
- Keep recorded and uploaded source audio under existing storage/resource
  conventions.

## Non-Goals

- First version does not clone voices for providers other than MiniMax.
- First version does not automatically delete remote MiniMax voices; local
  deletion is soft delete only.
- First version does not build an operator-wide voice marketplace.
- First version does not provide waveform editing, noise preview editing, or
  multi-take splicing. Authors can record again, replace the take, or upload a
  prepared file.
- First version does not change runtime TTS billing semantics. Voice clone
  creation is a separate authoring operation with its own credit admission,
  reservation, and settlement path.
- First version does not introduce a separate TTS playback path.

## Recommended Design

Add a MiniMax cloned-voice asset layer in the backend and expose it to the
existing Shifu setting frontend. The asset layer owns upload, clone, metadata,
listing, and deletion. Existing TTS settings continue to own runtime selection.
Voice clone creation should be asynchronous: the HTTP request validates input,
reserves credits when billing applies, creates a queued row, enqueues a worker,
and returns a job/voice status for the frontend to poll.

This keeps responsibilities clear:

- `flaskr/api/tts/minimax_provider.py` remains the TTS synthesis provider.
- New `flaskr/service/tts/minimax_voice_clone.py` owns MiniMax voice-clone API
  calls and provider-specific validation.
- New async worker orchestration owns recording normalization, local audio
  storage, MiniMax uploads, clone creation, and status transitions.
- Existing creator billing owns credit admission, reservation, capture, and
  release; the TTS service must not mutate wallet balances directly.
- New Shifu TTS routes expose creator-facing cloned voice management.
- Shifu draft/publish records continue to store the selected `tts_voice_id`.
- The frontend merges built-in MiniMax voices with the current author's cloned
  voices and preserves custom voice IDs when saving and previewing.

## Backend Components

### MiniMax Voice Clone Client

Create `src/api/flaskr/service/tts/minimax_voice_clone.py`.

Responsibilities:

- Validate MiniMax API configuration using `MINIMAX_API_KEY` and optional
  `MINIMAX_GROUP_ID`.
- Validate source audio file extension, size, declared content type, and
  duration before calling MiniMax.
- Normalize browser-recorded audio into a MiniMax-supported format before
  provider upload.
- Upload source audio with `purpose=voice_clone`.
- Upload prompt audio with `purpose=prompt_audio` when supplied.
- Call `/v1/voice_clone`.
- Normalize MiniMax responses into internal dataclasses.
- Format provider errors with status code, message, and trace ID when available.

Use `requests` directly, matching the existing MiniMax TTS provider style. Keep
timeouts explicit:

- file upload: `(10, 120)`
- clone request: `(10, 120)`

MiniMax endpoints should be configurable by constants but default to the public
API host already used by the provider:

- `https://api.minimaxi.com/v1/files/upload`
- `https://api.minimaxi.com/v1/voice_clone`

If the project later standardizes on `api.minimax.io`, the constant can be
changed without touching route or persistence code.

### Async Clone Orchestration

Voice clone creation should not run to completion inside the creator-facing
HTTP request. Source audio may need browser-format decoding, ffmpeg
transcoding, object storage, two MiniMax file uploads, and the MiniMax clone
request. Those operations are too slow and failure-prone for a single blocking
settings request.

Add an async task such as `tts.minimax_clone_voice`.

Submission flow:

1. Validate auth, Shifu edit permission, request shape, local voice ID format,
   declared content type, extension, and upload size.
2. Estimate the credit charge and run billing admission without mutating the
   wallet.
3. Generate `voice_bid`, store the raw uploaded/recorded audio in private
   temporary storage, and create `TTSMiniMaxClonedVoice` with `status=queued`.
4. Reserve credits when billing is enabled and the configured clone rate is
   greater than zero.
5. Enqueue `tts.minimax_clone_voice` with `voice_bid`.
6. Return `202 Accepted` with the voice/job DTO.

Worker flow:

1. Load the row by `voice_bid` and acquire a per-voice lock.
2. Move `queued` or retryable `failed` rows to `processing`.
3. Decode the raw source/prompt audio, enforce duration limits, export
   normalized `wav`, and store the normalized audio as the clone source of
   record.
4. Delete temporary raw audio when normalization has succeeded or the job has
   reached a final failed state.
5. Upload the normalized source and prompt audio to MiniMax.
6. Call `/v1/voice_clone`.
7. On MiniMax success, persist MiniMax IDs and preview metadata, then capture
   the reserved credit charge.
8. Move the row to `status=ready` only after billing capture succeeds, or to
   `status=billing_pending` while capture is retrying.
9. On provider or normalization failure, persist `status=failed`, store the
   safe error summary, and release any reserved credits.
10. On retryable infrastructure failure before a final result, leave the row
   retryable without duplicating the reservation.

Use idempotency keys based on `voice_bid`, for example:

- `voice_clone:<voice_bid>:reserve`
- `voice_clone:<voice_bid>:capture`
- `voice_clone:<voice_bid>:release`

This makes worker retries safe and prevents double billing if the same task is
delivered more than once.

### Recording Normalization

Live recording should use the browser `MediaRecorder` API. Browser output is
usually `audio/webm;codecs=opus` in Chromium-based browsers and can be
`audio/mp4` or `audio/wav` in Safari-like environments. MiniMax clone upload
only accepts `mp3`, `m4a`, and `wav`, so the backend must normalize recordings
before provider upload.

Use the existing `pydub` dependency and ffmpeg-backed decoding inside the async
worker, matching the audio-processing assumptions already present in
`service/tts/audio_utils.py`. The clone service should:

- Accept uploaded source blobs with these input extensions:
  `mp3`, `m4a`, `wav`, `webm`, `ogg`, `mp4`.
- Decode the input with `pydub.AudioSegment.from_file`.
- Measure duration from the decoded audio and enforce MiniMax limits locally.
- Export normalized source audio as `wav` for MiniMax upload.
- Export normalized prompt audio as `wav` when prompt audio is supplied from
  browser recording.
- Mark the job failed if decoding/transcoding fails, with a safe `status_msg`
  that asks the user to record again or upload `mp3`, `m4a`, or `wav`.

Store the normalized audio as the clone source of record. The raw browser blob
or direct upload should be retained only as a temporary private object while the
async worker is pending or processing, because it may be provider-specific and
is not directly usable by MiniMax. Persist a `source_capture_method` value so
operators can distinguish `recording` from `upload`.

### Credit Deduction

Voice cloning is an authoring-time TTS-provider operation, not runtime lesson
audio. Reuse creator billing primitives instead of adding a separate wallet
path under TTS.

Recommended billing mapping:

- `usage_type`: `BILL_USAGE_TYPE_TTS`
- `usage_scene`: `BILL_USAGE_SCENE_PREVIEW`
- `provider`: `minimax`
- `model`: `voice_clone`
- `billing_metric`: `BILLING_METRIC_TTS_REQUEST_COUNT`
- `unit_size`: `1`

This lets operators configure a fixed credit price through `CreditUsageRate`
without changing the runtime TTS charge model. The default seed may remain
zero; production pricing should be an explicit rate row for
`provider=minimax`, `model=voice_clone`, and preview scene.

Add a focused billing helper set in `service/billing`, rather than mutating
wallet tables from TTS code:

- `reserve_operation_credits(app, creator_bid, amount, operation_type,
  operation_bid, metadata)`: moves available credits to reserved credits across
  consumable buckets using the same bucket order as settlement and writes a
  `CREDIT_LEDGER_ENTRY_TYPE_HOLD` ledger row.
- `capture_reserved_operation_credits(app, reservation_bid, usage_bid,
  metadata)`: converts the reservation into a consume ledger row, increments
  consumed credits, refreshes wallet snapshots, and records the usage metadata.
- `release_reserved_operation_credits(app, reservation_bid, reason)`: moves
  reserved credits back to available credits and writes a
  `CREDIT_LEDGER_ENTRY_TYPE_RELEASE` ledger row.

The clone route should call `admit_creator_usage` first so disabled billing,
inactive subscriptions, and empty wallets follow the existing creator-billing
rules. Then it should estimate the fixed clone charge from `CreditUsageRate`.
If the estimated charge is zero, no reservation is created. If the estimate is
positive and available consumable credits are insufficient, the route fails
before enqueueing the clone task.

On successful clone, create a `BillUsageRecord` for observability and reporting
with `extra.usage_source=minimax_voice_clone`, `extra.voice_bid`, and the
MiniMax `extra_info`. Capture the reservation against that `usage_bid`. Do not
also enqueue the normal `billing.settle_usage` task for this record; otherwise
the same clone operation could be charged twice. A small metering helper such
as `record_tts_voice_clone_usage(..., enqueue_settlement=False)` keeps this
explicit.

On failed clone, release the reservation. If the task fails before it can
determine provider outcome, retry with the same reservation. If retries are
exhausted, mark the row failed and release the reservation.

### Data Model

Add a new model in `src/api/flaskr/service/tts/models.py`:

`TTSMiniMaxClonedVoice`

Fields:

- `id`: numeric primary key.
- `voice_bid`: generated business ID, indexed.
- `owner_user_bid`: creator user business ID, indexed.
- `shifu_bid`: optional course business ID used when a cloned voice is created
  from a specific Shifu setting screen; indexed.
- `voice_id`: MiniMax custom voice ID, indexed.
- `display_name`: author-facing name.
- `source_resource_bid`: local resource ID for normalized source audio.
- `prompt_resource_bid`: optional local resource ID for normalized prompt
  audio.
- `source_temp_resource_bid`: temporary local resource ID for raw submitted
  source audio, cleared after worker finalization when cleanup succeeds.
- `prompt_temp_resource_bid`: temporary local resource ID for raw submitted
  prompt audio, cleared after worker finalization when cleanup succeeds.
- `source_capture_method`: `recording` or `upload`.
- `source_original_filename`: original uploaded or recorded filename.
- `source_original_content_type`: browser or upload content type.
- `source_duration_ms`: normalized source duration.
- `prompt_duration_ms`: normalized prompt duration when present.
- `minimax_file_id`: MiniMax source file ID.
- `minimax_prompt_file_id`: optional MiniMax prompt file ID.
- `billing_reservation_bid`: optional reservation business ID.
- `clone_usage_bid`: optional `BillUsageRecord.usage_bid` created after a
  successful clone.
- `estimated_credits`: fixed charge estimated at submission time.
- `charged_credits`: actual credits captured after success.
- `billing_status`: `not_required`, `reserved`, `charged`, `released`, or
  `failed`.
- `attempt_count`: worker attempt count.
- `started_at`: timestamp when the current worker attempt started.
- `completed_at`: timestamp when the clone reached `ready` or final `failed`.
- `prompt_text`: transcript for prompt audio when supplied.
- `preview_text`: clone preview text sent to MiniMax.
- `preview_model`: model used for clone preview, default `speech-2.8-turbo`.
- `preview_audio_url`: MiniMax `demo_audio` URL when returned.
- `language_boost`: optional MiniMax language boost value.
- `accuracy`: ASR validation threshold when `text_validation` is used.
- `text_validation`: optional expected transcript for MiniMax ASR validation.
- `need_noise_reduction`: boolean.
- `need_volume_normalization`: boolean.
- `aigc_watermark`: boolean, default false.
- `status`: `queued`, `processing`, `billing_pending`, `ready`, `failed`,
  `deleted`.
- `status_code`: MiniMax business status code when present.
- `status_msg`: MiniMax status message or local failure reason.
- `input_sensitive`: boolean nullable.
- `input_sensitive_type`: integer nullable.
- `extra_info`: JSON text for MiniMax preview metadata.
- `deleted`: small integer flag.
- `created_at`, `created_user_bid`, `updated_at`, `updated_user_bid`.

Indexes:

- `voice_bid`
- `owner_user_bid + deleted + created_at`
- `owner_user_bid + voice_id + deleted`
- `shifu_bid + deleted + created_at`

Do not add hard foreign keys; this follows the repository's business-key
relationship convention.

`voice_id` is globally unique in MiniMax for the configured account. Enforce
local uniqueness among non-deleted rows. If DB portability makes partial unique
indexes awkward, enforce the duplicate check in service code and use a normal
index.

### Local Audio Storage

Use the existing storage abstraction, but do not reuse the image-only Shifu
avatar upload helper because it guesses image content types.

Add a focused helper in the new voice-clone service:

- Generate a resource ID using the existing UUID style.
- Store raw submitted audio only as a temporary private object while the async
  worker is queued or processing, with keys such as
  `tts-voice-clone/raw/source/<voice_bid>.<ext>` and
  `tts-voice-clone/raw/prompt/<voice_bid>.<ext>`.
- Store normalized audio under `courses` profile with object keys such as
  `tts-voice-clone/source/<resource_id>.wav` and
  `tts-voice-clone/prompt/<resource_id>.wav`.
- Persist a `Resource` row with `type=0`, matching current loose resource
  conventions, unless a dedicated audio resource type is introduced later.
- Use content type from extension:
  - `mp3`: `audio/mpeg`
  - `m4a`: `audio/mp4`
  - `wav`: `audio/wav`
  - normalized browser recordings: `audio/wav`

The worker should pass the normalized audio bytes to MiniMax from the same
artifact it stores through the resource abstraction. This avoids
stream-position bugs between storage and provider upload and guarantees the
file extension sent to MiniMax matches the actual bytes. Raw temporary objects
should be removed after the worker creates normalized audio or reaches final
failure.

### Validation

Backend validation is the source of truth.

Source audio:

- Accepted direct-upload extensions: `mp3`, `m4a`, `wav`.
- Accepted live-recording/browser blob extensions before normalization:
  `webm`, `ogg`, `mp4`, `wav`.
- Maximum size: 20 MB.
- Duration must be 10 seconds to 5 minutes, measured after decoding.
- Decoding must fail before MiniMax upload if pydub/ffmpeg cannot read the
  input.
- Because decoding happens in the async worker, the submission route performs
  only extension, content type, and size checks; duration validation is
  authoritative in the worker and releases any reserved credits on failure.

Prompt audio:

- Accepted direct-upload extensions: `mp3`, `m4a`, `wav`.
- Accepted live-recording/browser blob extensions before normalization:
  `webm`, `ogg`, `mp4`, `wav`.
- Maximum size: 20 MB.
- Duration must be less than 8 seconds, measured after decoding.
- `prompt_text` is required when prompt audio is supplied.
- Because decoding happens in the async worker, prompt duration validation is
  authoritative in the worker and releases any reserved credits on failure.

Voice ID:

- Length 8 to 256.
- Starts with an English letter.
- Contains only letters, digits, `-`, and `_`.
- Does not end in `-` or `_`.
- Must not duplicate an active local cloned voice for this MiniMax account.

TTS settings:

- Keep strict validation for provider, model, speed, pitch, and emotion.
- For MiniMax only, allow a `voice_id` that is not in `MINIMAX_VOICES` if it
  matches the MiniMax custom voice ID format.
- Other providers continue to require their configured voice list.
- Existing cloned voice rows should be preferred for display and ownership, but
  a valid MiniMax custom `voice_id` may be saved even if no local row exists.

### Creator Routes

Add routes under the existing Shifu service route group:

`GET /api/shifu/tts/minimax/voices`

- Requires a creator-authenticated user.
- Query params:
  - `shifu_bid` optional.
  - `include_global=true|false`, default true.
- Returns cloned voice rows owned by the current user. Include `queued`,
  `processing`, `billing_pending`, `ready`, and `failed` rows so the settings
  UI can show progress and errors. Deleted rows are excluded.

`POST /api/shifu/tts/minimax/voices/clone`

- Requires edit permission when `shifu_bid` is supplied; otherwise requires a
  creator-authenticated user.
- Multipart fields:
  - `source_audio`: required file. This can be a live recording blob or a
    direct audio upload.
  - `prompt_audio`: optional file.
  - `source_capture_method`: `recording` or `upload`, default `upload`.
  - `display_name`: required string.
  - `voice_id`: optional custom ID. If omitted, generate a stable ID such as
    `AiShifu_<short_user>_<timestamp>_<suffix>`.
  - `shifu_bid`: optional.
  - `prompt_text`: required when `prompt_audio` is present.
  - `preview_text`: optional, default a short bilingual preview sentence.
  - `preview_model`: optional, default `speech-2.8-turbo`.
  - `language_boost`: optional, default `auto`.
  - `text_validation`: optional.
  - `accuracy`: optional, default `0.7`.
  - `need_noise_reduction`: optional boolean.
  - `need_volume_normalization`: optional boolean.
- Validates input, stores raw audio in private temporary storage, checks billing
  admission, reserves credits when required, creates a local row with status
  `queued`, and enqueues the async clone task.
- Returns `202 Accepted`.
- Returns:
  - `voice_bid`
  - `voice_id`
  - `display_name`
  - `status`
  - `billing_status`
  - `estimated_credits`
  - `charged_credits`
  - `preview_audio_url`
  - `extra_info`
  - `status_msg`

`GET /api/shifu/tts/minimax/voices/<voice_bid>`

- Requires owner.
- Returns the current cloned voice/job DTO for polling.
- Ready rows include `preview_audio_url`, `extra_info`, and `charged_credits`.
- Failed rows include a safe `status_msg` and `billing_status=released` when a
  reservation was released.

`POST /api/shifu/tts/minimax/voices/<voice_bid>/retry`

- Optional v1 endpoint; the UI can omit this if retry is not productized.
- Requires owner and `status=failed`.
- Revalidates billing admission, creates or reuses a reservation, sets
  `status=queued`, increments retry metadata, and enqueues the worker.

`DELETE /api/shifu/tts/minimax/voices/<voice_bid>`

- Requires owner.
- Soft deletes the local row.
- Refuses deletion if the voice is currently selected by an active draft or
  published Shifu owned by the user, unless `force=true` is provided. Even with
  force, only local selection metadata changes; the MiniMax remote voice is not
  deleted in v1.

`POST /api/shifu/tts/minimax/voices/validate-id`

- Requires creator-authenticated user.
- Body: `voice_id`.
- Returns whether the ID is locally available and whether it matches MiniMax's
  format.
- This is optional for UI responsiveness; the clone endpoint still performs the
  authoritative check.

`GET /api/shifu/tts/minimax/voices/clone-cost`

- Requires creator-authenticated user.
- Query params:
  - `shifu_bid` optional, used for creator ownership/admission context.
- Returns the current estimated fixed clone charge, available credits, whether
  billing is enabled, and whether the current creator can submit a clone job.
- This endpoint is advisory for UI copy and button state; the clone endpoint
  still performs the authoritative billing admission and reservation.

### DTO Shape

Return cloned voices using a small DTO:

```json
{
  "voice_bid": "voice_8f4c2a6b91d4",
  "voice_id": "AiShifu_abcd_20260618_x1",
  "display_name": "Teacher Zhang",
  "provider": "minimax",
  "status": "ready",
  "billing_status": "charged",
  "estimated_credits": "3.0000000000",
  "charged_credits": "3.0000000000",
  "preview_audio_url": "https://...",
  "shifu_bid": "shifu_7d2c91a4b8e0",
  "created_at": "2026-06-18T12:00:00Z"
}
```

The `/api/shifu/tts/config` provider config should remain mostly static. It may
add capability flags for MiniMax:

```json
{
  "supports_custom_voice_id": true,
  "supports_voice_cloning": true
}
```

Do not put user-owned cloned voice rows into the public config response.

## Frontend Design

Update `src/cook-web/src/components/shifu-setting/ShifuSetting.tsx` and keep
strings in shared i18n JSON.

### State

Add state for:

- cloned voice list
- clone dialog open/closed
- clone upload progress/loading
- active clone job status and polling timer
- custom voice ID input
- selected voice source: built-in, cloned, or manual
- source recording state: idle, recording, recorded, uploading, failed
- source recording duration and blob URL
- prompt recording state and duration when prompt audio is enabled

Fetch cloned voices when:

- the settings sheet opens,
- TTS is enabled,
- resolved provider is `minimax`.

### Voice Selection

For MiniMax, replace the single fixed voice select with a voice picker that
contains:

- built-in voices from provider config,
- current user's cloned voices from `GET /tts/minimax/voices`,
- manual custom ID option.

When the saved `tts_voice_id` is not in built-in voices and not in cloned
voices, show it as a manual custom voice instead of resetting it.

For non-MiniMax providers, keep the existing fixed select behavior.

### Clone Dialog

The clone dialog lives inside the TTS section and contains:

- display name input,
- optional custom voice ID input,
- required source audio capture with two modes:
  - record in browser,
  - upload existing audio,
- optional prompt audio capture with the same record/upload modes,
- prompt text input shown when prompt audio exists,
- preview text input,
- preview model select using MiniMax model options,
- noise reduction and volume normalization toggles,
- estimated credit cost and available credit state when billing is enabled,
- create button,
- preview audio link/player after success.

Recording behavior:

- Use `navigator.mediaDevices.getUserMedia({ audio: true })` and
  `MediaRecorder`.
- Prefer `audio/webm;codecs=opus` when supported, then fall back to
  `audio/mp4`, then the browser default.
- Show a timer while recording.
- Source recording cannot be submitted before 10 seconds.
- Source recording auto-stops at 5 minutes.
- Prompt recording auto-stops at 8 seconds.
- Authors can play back the recorded take, discard it, and record again before
  submission.
- If microphone permission is denied or unsupported, keep the upload fallback
  available.
- Send the recorded blob as `source_audio` or `prompt_audio` in the clone
  multipart request, with `source_capture_method=recording`.

After clone submission:

- show the row as `queued` or `processing`,
- poll `GET /tts/minimax/voices/<voice_bid>` while the dialog is open,
- keep the row visible in the cloned voice list if the dialog is closed,
- disable selecting the new voice until `status=ready`,
- show a clear failure state with retry when retry is enabled.

After the async job reaches `ready`:

- append the returned voice to the cloned voice list,
- set `tts_voice_id` to the new `voice_id`,
- keep current MiniMax model/speed/pitch/emotion selections,
- allow normal TTS preview to use the new voice.

Billing UX:

- Fetch the current billing overview or a small clone-cost endpoint when the
  dialog opens.
- Show the estimated clone credit cost before submission.
- Disable create and link to recharge/plan management when available credits
  are insufficient.
- After submission, show reserved, charged, or released status using the voice
  DTO `billing_status`.

### Sanitization Changes

The current effect that defaults unknown voices must become provider-aware:

- If provider is MiniMax and `tts_voice_id` is non-empty but unknown, keep it.
- If provider is non-MiniMax and `tts_voice_id` is not in configured voices,
  reset to provider default.
- If provider changes away from MiniMax, reset custom voice IDs unless the new
  provider's configured list contains the same value.

## Runtime Flow

1. Author opens Shifu settings and enables TTS.
2. Frontend loads TTS config and MiniMax cloned voices.
3. Author records source audio in the browser or uploads an existing audio
   file.
4. Frontend sends the audio blob to the clone endpoint.
5. Backend checks billing admission, reserves credits when required, stores the
   raw audio in private temporary storage, creates a queued clone row, and
   enqueues the worker.
6. Frontend polls the voice/job detail endpoint.
7. Worker normalizes recorded audio to `wav`, validates decoded duration,
   uploads audio to MiniMax, creates the cloned voice, captures the reserved
   credits on success, or releases the reservation on failure.
8. Backend stores the cloned voice metadata and returns the MiniMax `voice_id`
   when the poll response reaches `ready`.
9. Author previews TTS. Preview uses the existing `/api/shifu/tts/preview`
   route with the cloned `voice_id`.
10. Author saves. Draft stores `tts_provider=minimax` and `tts_voice_id=<custom>`.
11. Runtime lesson/listen-mode TTS validates the MiniMax custom ID format and
   uses the existing MiniMax TTS provider.

## Error Handling

- Provider credential missing: return parameter error indicating MiniMax TTS is
  not configured.
- Browser microphone unavailable or denied: frontend keeps upload mode
  available and does not call the clone endpoint until audio exists.
- Insufficient credits: fail before enqueueing the clone worker and do not call
  MiniMax.
- Billing reservation failure after local row creation: mark the row `failed`
  and do not enqueue the clone worker.
- Worker enqueue failure after reservation: release the reservation and mark
  the row `failed` with a retryable infrastructure message.
- Recording shorter than MiniMax minimum: frontend blocks submission and backend
  revalidates after decoding.
- Recording longer than MiniMax maximum: frontend auto-stops; backend rejects if
  the decoded duration is still too long.
- Recording/transcode failure: worker marks the job `failed`, releases reserved
  credits, and does not call MiniMax.
- Invalid local upload: return `server.common.paramsError` with the invalid
  field.
- Duplicate local voice ID: return parameter error before provider upload.
- MiniMax duplicate remote voice ID: mark local row `failed`, include
  `status_msg`, and release reserved credits.
- MiniMax sensitive input: mark row `failed`, persist sensitivity fields, and
  show a safe failure message; release reserved credits unless product decides
  sensitive-input failures are still chargeable.
- Preview audio omitted by MiniMax: still treat clone as `ready` when
  `base_resp.status_code == 0`, capture reserved credits, but return an empty
  `preview_audio_url`.
- Billing capture failure after MiniMax success: keep the voice row in
  `billing_pending` and retry capture with the same reservation. Do not expose
  the voice as selectable until billing capture is settled or explicitly waived
  by an operator path.

## Security And Privacy

- Do not expose MiniMax API keys to the browser.
- Only the owner can list, clone, or delete their cloned voices.
- When `shifu_bid` is supplied, verify Shifu edit permission before linking a
  cloned voice to that course.
- Store uploaded audio through existing storage, not in temporary web-accessible
  paths.
- Stop microphone tracks after recording, discard, dialog close, and successful
  submission.
- Do not log raw audio bytes, prompt audio bytes, or API keys.
- Treat custom voice IDs as user-controlled strings and validate before storage
  or provider calls.

## Metering And Billing

Runtime TTS metering remains unchanged. Normal preview, streaming, listen-mode,
generated-audio persistence, and usage settlement continue to use the existing
TTS recorder paths.

Voice clone creation is billable separately from runtime TTS. Use a fixed
request-count charge in creator billing:

- price source: `CreditUsageRate`
- usage type: TTS
- usage scene: preview
- provider/model: `minimax` / `voice_clone`
- metric: `tts_request_count`

Recommended lifecycle:

1. Clone submission estimates the fixed charge from active rate rows.
2. If billing is enabled and the charge is positive, reserve credits before
   enqueueing the worker.
3. The async worker calls MiniMax.
4. On success, create a `BillUsageRecord` for the clone operation and capture
   the reservation into a consume ledger entry.
5. On failure, release the reservation.

This is intentionally stricter than charging only after success without
reservation. It prevents a creator with no usable credits from triggering
provider cost, and it makes repeated worker delivery idempotent through
reservation/capture/release keys.

MiniMax `/v1/voice_clone` can return `extra_info.usage_characters` when preview
text is provided. Persist that in both the cloned voice row and the usage
record `extra` payload. The charge amount should still come from AI-Shifu
`CreditUsageRate`, not directly from MiniMax usage characters, so product can
price clone creation as a stable fixed operation.

## Implementation Sequence

1. Add backend validation helpers for MiniMax custom voice IDs and adjust
   `validate_tts_settings_strict` so MiniMax custom IDs can pass.
2. Add billing helpers for operation credit estimation, reservation, capture,
   and release, plus rate seed or operator configuration support for
   `minimax/voice_clone`.
3. Add the cloned voice model and migration with async and billing fields.
4. Add MiniMax clone client and local audio storage helper.
5. Add audio normalization helpers for browser recordings using pydub.
6. Add `tts.minimax_clone_voice` worker and idempotent status transitions.
7. Add Shifu TTS cloned voice routes, job polling DTOs, and optional retry
   route.
8. Add focused backend tests for validation, route permissions, billing
   reservation/capture/release, async worker success/failure, duplicate IDs,
   and soft delete.
9. Add frontend API definitions and i18n strings.
10. Update Shifu setting UI to list cloned voices, preserve manual IDs, and run
   the clone dialog.
11. Add the browser recording flow with upload fallback and async polling.
12. Add frontend type/lint coverage and focused tests where local patterns
   exist.
13. Run targeted backend tests, frontend type checks, and the repository
   harness checks required by touched surfaces.

## Verification

Backend:

- `cd src/api && pytest tests/service/tts/ -q`
- `cd src/api && pytest tests/service/shifu/test_tts_preview_route.py -q`
- Add new tests for:
  - MiniMax custom voice ID format validation.
  - MiniMax custom voice ID accepted while invalid non-MiniMax voices are still
    rejected.
  - Clone route builds correct MiniMax upload and clone payloads.
  - Clone submission creates queued records, reserves credits when configured,
    and returns `202`.
  - Worker persists ready and failed records.
  - Worker captures reserved credits once on success.
  - Worker releases reserved credits once on failure.
  - Worker retry does not duplicate reservations, MiniMax calls after success,
    usage records, or ledger entries.
  - Clone-cost endpoint reports estimated credits and insufficient-credit
    status without mutating wallet state.
  - Billing capture failure keeps the row out of selectable `ready` state until
    capture succeeds.
  - Clone list only returns current user's voices.
  - Soft delete refuses voices selected by active Shifu unless forced.
  - Browser recording input is decoded, duration-validated, normalized to wav,
    stored, and sent to MiniMax with a supported filename.
  - Too-short, too-long, undecodable, or unsupported recording blobs fail before
    MiniMax upload.

Frontend:

- `cd src/cook-web && npm run type-check`
- `cd src/cook-web && npm run lint`
- Add focused tests if the component test harness already covers
  `ShifuSetting`; otherwise rely on type/lint plus manual browser verification.

Repository:

- `python scripts/check_repo_harness.py`
- `python scripts/check_architecture_boundaries.py` only if the implementation
  changes shared boundaries or adds cross-surface dependencies outside the
  planned backend/frontend route contract.

Manual provider verification:

- With `MINIMAX_API_KEY` configured, upload a valid source audio file and create
  a cloned voice.
- With `MINIMAX_API_KEY` configured, record source audio in the browser and
  create a cloned voice from that recording.
- Confirm returned `voice_id` appears in the Shifu setting voice picker.
- Confirm the submitted clone first appears as queued/processing and only
  becomes selectable after the poll response reaches ready.
- Confirm a creator with insufficient credits cannot enqueue a clone.
- Confirm a failed clone releases reserved credits.
- Preview TTS with the cloned voice.
- Save the Shifu, reload settings, and confirm the custom `tts_voice_id` is not
  reset.
- Run a preview lesson/listen-mode flow and confirm audio generation uses the
  cloned voice.

## Rollout Notes

- Gate the clone UI behind MiniMax provider availability and
  `supports_voice_cloning`.
- Keep manual custom voice ID available even when clone creation fails, so
  operators can recover by creating a voice out of band.
- Do not delete remote MiniMax voices in v1.
- If MiniMax's 7-day unused cloned voice cleanup affects production use, add a
  follow-up job or explicit first-use T2A call after clone creation. This design
  intentionally keeps that out of v1 until product confirms whether automatic
  activation cost is acceptable.

## Open Questions

- What fixed credit price should production use for `minimax/voice_clone`?
- Should cloned voices be scoped to a single course by default, or reusable by
  the same creator across courses? This design defaults to reusable by creator
  with optional `shifu_bid` linkage.
- Should sensitive-input failures always release reserved credits, or should
  product policy charge them after repeated abuse?
- Should operators have a global cloned-voice management page in a later phase?

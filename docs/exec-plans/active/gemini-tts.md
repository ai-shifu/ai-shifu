# Gemini TTS Provider

## Purpose / Big Picture

Add Google Gemini as an application-side TTS provider so overseas deployments
can offer Gemini voices next to Volcengine and ElevenLabs without changing the
listen-mode streaming contract. Teachers select one of three Gemini TTS models
and one of the thirty prebuilt voices; generated audio continues through the
shared segmentation, SSE, caching, storage, and metering paths as MP3.

## Progress

- [x] 2026-09-03: Confirmed provider, validation, streaming, config, and test
  ownership on the latest `origin/main`; researched the Gemini Developer API
  speech contract (PCM-only output, no speed/pitch parameters, preview-only
  models, streaming limited to 3.1).
- [x] 2026-09-03: Extracted shared PCM helpers (`pcm_duration_ms`,
  `export_pcm_to_mp3`) into `flaskr/service/tts/audio_utils.py` and made the
  Tencent SSE provider delegate to them.
- [x] 2026-09-03: Implemented `GeminiTTSProvider`, the shared voice allowlist
  parser, registry wiring, strict validation, shared retry/skip integration,
  and environment declarations.
- [x] 2026-09-03: Added focused provider tests plus audio-utility and
  streaming regression coverage; regenerated the Docker env example.
- [x] 2026-09-03: Credentialed smoke tests. From the US dev pod (direct
  Google access) both `gemini-3.1-flash-tts-preview` and
  `gemini-2.5-flash-preview-tts` returned MP3 in about 3 seconds for a
  43-character sentence, with `duration_ms` matching the decoded MP3 length.
  From the China test host Google is unreachable, so `GEMINI_TTS_API_URL`
  points at the internal Google AI proxy (`.../googleai/v1beta`), which
  returned the same PCM payload in about 9 seconds.

## Surprises & Discoveries

- Gemini's `generateContent` speech responses carry raw 16-bit PCM inside
  `inlineData` (`audio/L16;codec=pcm;rate=24000`). The SSE audio contract has
  no format field and the web player decodes each segment independently, so
  the provider must transcode to MP3 itself.
- `GEMINI_API_URL` is a LiteLLM chat override that the LLM layer discards
  when it points at the official Gemini host. The TTS endpoint therefore has
  its own `GEMINI_TTS_API_URL` instead of reusing that value.
- Preview TTS models report overload as HTTP 503. The shared streaming retry
  matches on a "rate limit" marker in the error text, so 503 is reported the
  same way as 429 to opt into the staggered retry.
- Hosts in mainland China cannot reach `generativelanguage.googleapis.com`.
  The dedicated `GEMINI_TTS_API_URL` lets those deployments route the TTS
  call through the existing Google AI proxy while keeping the default for
  overseas clusters.
- Gemini exposes neither speed nor pitch. Locking both ranges to a single
  value keeps the generic editor working because strict validation uses
  inclusive bounds and the editor clamps into the advertised range.

## Decision Log

- Use the Gemini Developer API with `GEMINI_API_KEY`; the Cloud
  Text-to-Speech transport (GA models, direct MP3, GCP OAuth) is documented as
  a possible follow-up but not implemented.
- Gate exposure behind `GEMINI_TTS_ENABLED` because many deployments set
  `GEMINI_API_KEY` for LLM calls only and must not gain a voice option by
  accident.
- Expose exactly `gemini-3.1-flash-tts-preview`,
  `gemini-2.5-flash-preview-tts`, and `gemini-2.5-pro-preview-tts`.
- Ship the thirty prebuilt voices as the built-in catalog; the optional
  `GEMINI_TTS_VOICES_JSON` allowlist narrows or relabels them and falls back
  to the built-in catalog when invalid.
- Keep the provider explicit-only (not auto-detected) and hide it from the
  config payload unless it is configured and allowlisted, matching ElevenLabs.
- Send each sentence-sized segment as one unary request; provider-native
  streaming for the 3.1 model is intentionally out of scope.
- Do not map `emotion` to a style prompt in this version; the text is sent
  unchanged through a single hook where a prefix could be added later.

## Outcomes & Retrospective

Gemini is available as an explicit, fail-closed provider with three models and
thirty deployment-filterable voices. Existing frontend, database, SSE,
storage, and metering contracts were reused unchanged. Transcoding reuses the
same pydub/ffmpeg path already required by the Tencent SSE provider.

## Context and Orientation

Provider adapters live under `src/api/flaskr/api/tts/`. Registry and picker
payload construction live in that package's `__init__.py`. Strict course
settings are checked in `src/api/flaskr/service/tts/validation.py`, while the
generic listen-mode synthesis and retry behavior live in
`src/api/flaskr/service/tts/streaming_tts.py`. Shared audio helpers live in
`src/api/flaskr/service/tts/audio_utils.py`.

## Plan of Work

Implement a REST adapter that validates its deployment configuration, calls
`generateContent` with `responseModalities=["AUDIO"]`, transcodes the PCM
reply to MP3, and returns the existing `TTSResult`. Register it for explicit
selection, add strict model/voice checks, opt it into shared empty-audio and
rate-limit behavior, declare its environment variables, and cover the
integration with focused tests.

## Concrete Steps

1. Add `pcm_duration_ms` and `export_pcm_to_mp3` to `audio_utils.py`; make
   the Tencent provider delegate to them.
2. Add `voice_config.parse_voice_list_json` for deployment voice allowlists.
3. Add `GeminiTTSProvider` with its model catalog, voice catalog, request
   builder, response validation, and PCM-to-MP3 transcoding.
4. Register `gemini` without changing auto-detection; add it to the strict
   validation sets and the shared empty-audio and non-speakable skip sets.
5. Declare `GEMINI_TTS_ENABLED`, `GEMINI_TTS_API_URL`, and
   `GEMINI_TTS_VOICES_JSON`; regenerate `docker/.env.example.full`.
6. Add provider, audio-utility, validation, and streaming regression tests.

## Validation and Acceptance

With `GEMINI_TTS_ENABLED=true`, a Gemini API key, and matching
`TTS_ALLOWED_MODELS`, the TTS config payload exposes the Gemini models and
voices with locked speed and pitch ranges. Synthesis sends the expected
authenticated request and returns playable MP3 bytes whose duration matches
the PCM length. Missing or disabled configuration hides the provider, and
invalid course settings fail before an external request.

Run:

```bash
cd src/api
python -m pytest tests/service/tts -q
ruff check flaskr/api/tts flaskr/service/tts tests/service/tts
```

## Idempotence and Recovery

Environment example generation is deterministic. Tests use mocked HTTP and a
mocked transcoder and do not require credentials or ffmpeg. If configuration
is invalid, unsetting `GEMINI_TTS_ENABLED` restores the previous provider set
without data migration.

## Interfaces and Dependencies

- New environment variables: `GEMINI_TTS_ENABLED`, `GEMINI_TTS_API_URL`, and
  `GEMINI_TTS_VOICES_JSON`; synthesis reuses `GEMINI_API_KEY`.
- Existing dependencies: `requests`, `pydub` with ffmpeg (already required by
  the Tencent SSE provider and audio concatenation).
- No database, public HTTP DTO, frontend, or deployment repository changes.
  Deployments must add `credit_usage_rates` rows for the Gemini models so the
  picker shows a credit multiplier.

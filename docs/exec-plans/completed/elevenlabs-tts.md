# ElevenLabs TTS Provider

## Purpose / Big Picture

Add ElevenLabs as an application-side TTS provider without changing the
existing listen-mode streaming contract. Teachers can select one of four
approved ElevenLabs models and a deployment-configured voice; generated MP3
audio continues through the shared segmentation, SSE, caching, storage, and
metering paths.

## Progress

- [x] 2026-08-27 13:00 CST: Confirmed provider, validation, streaming, config,
  and test ownership on the latest `origin/main`.
- [x] 2026-08-27 13:04 CST: Implemented the ElevenLabs provider and registry
  integration.
- [x] 2026-08-27 13:05 CST: Added fail-closed model and voice validation plus
  shared retry/skip integration.
- [x] 2026-08-27 13:06 CST: Added focused tests and regenerated the Docker env
  example.
- [x] 2026-08-27 13:08 CST: Passed 61 focused tests, 249 broader TTS tests,
  Ruff checks, and repository harness verification after refreshing generated
  knowledge docs.
- [x] 2026-08-27 18:04 CST: Passed a credentialed application smoke test
  through Flask app creation, the TTS config route, strict validation, preview
  segmentation, real ElevenLabs synthesis, SSE serialization, MP3
  concatenation, and clean FFmpeg decoding. Database metering writes were
  suppressed to avoid persistent test data.

## Surprises & Discoveries

- The provider config endpoint historically lists providers even when their
  credentials are absent. ElevenLabs needs a narrower fail-closed exposure
  rule because its selectable voices are entirely deployment-owned.
- The current generic streaming path already owns segmentation, retry, MP3
  concatenation, subtitle fallback, storage, and metering, so no frontend or
  DTO changes are required.

## Decision Log

- Use the synchronous ElevenLabs create-speech endpoint and request
  `mp3_44100_128`; provider-native streaming is intentionally out of scope.
- Expose exactly `eleven_v3_conversational`, `eleven_v3`,
  `eleven_flash_v2_5`, and `eleven_multilingual_v2`.
- Load voices only from `ELEVENLABS_TTS_VOICES_JSON`; malformed, empty, or
  duplicate voice entries make the provider unavailable.
- Do not add ElevenLabs to automatic provider detection, and do not change the
  current default provider or deployment allowlist.

## Outcomes & Retrospective

ElevenLabs is now available as an explicit, fail-closed provider with four
models and deployment-owned voices. Existing frontend, database, SSE, storage,
and metering contracts were reused unchanged. A credentialed live request used
temporary process-only voice and model configuration: three preview segments
produced one valid 44.1 kHz MP3, while the repository and generated examples
remained free of credentials and deployment values.

## Context and Orientation

Provider adapters live under `src/api/flaskr/api/tts/`. Registry and picker
payload construction live in that package's `__init__.py`. Strict course
settings are checked in `src/api/flaskr/service/tts/validation.py`, while the
generic listen-mode synthesis and retry behavior live in
`src/api/flaskr/service/tts/streaming_tts.py`.

## Plan of Work

Implement a REST adapter that validates its deployment configuration and
returns the existing `TTSResult`. Register it for explicit selection, add
strict model/voice checks, opt it into shared empty-audio/rate-limit behavior,
declare its environment variables, and cover the integration with focused
tests.

## Concrete Steps

1. Add `ElevenLabsTTSProvider` and its model/voice configuration parser.
2. Register `elevenlabs` without changing auto-detection.
3. Enforce required model and allowlisted voice selection.
4. Add ElevenLabs to generic non-speakable and empty-audio handling.
5. Add provider, config, validation, and streaming regression tests.
6. Regenerate `docker/.env.example.full` and run verification.

## Validation and Acceptance

With a key, valid voice JSON, and matching `TTS_ALLOWED_MODELS`, the TTS config
payload exposes the approved ElevenLabs models and voices. Synthesis sends the
expected authenticated request and returns playable MP3 bytes. Missing or
invalid deployment configuration hides the provider, and invalid course
settings fail before an external request.

## Idempotence and Recovery

Environment example generation is deterministic. Tests use mocked HTTP and do
not require credentials or mutate external services. If configuration is
invalid, removing or correcting the two ElevenLabs environment variables
restores the previous provider set without data migration.

## Interfaces and Dependencies

- New environment variables: `ELEVENLABS_API_KEY` and
  `ELEVENLABS_TTS_VOICES_JSON`.
- Existing dependency: `requests`.
- No database, public HTTP DTO, frontend, deployment repository, or billing
  rate changes.

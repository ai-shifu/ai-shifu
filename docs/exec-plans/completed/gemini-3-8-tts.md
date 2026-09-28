# Gemini 3.8 TTS migration

## Purpose / Big Picture

Support Gemini 3.8 Flash TTS and Flash-Lite TTS in the existing Gemini provider so the US deployment can replace its two preview TTS choices while retaining playable MP3 output and character-based metering.

## Progress

- [x] 2026-09-28: Verified both models with the US cluster credential using Google's Interactions API; both returned nonempty raw PCM audio.
- [x] 2026-09-28: Added the Interactions request and response path with focused regression coverage.
- [x] 2026-09-28: Ran 715 TTS tests and a credentialed provider smoke test for both models; MP3 decoding and duration matched.
- [x] 2026-09-28: Merged backend PR #2992 and deploy-config PR #34; deployed the new API image to US API and Celery Worker.
- [x] 2026-09-28: Migrated 56 active draft and 3 active published course settings, inserted time-bounded 2026 and 2027 rates, and narrowed the US allowlist to the two 3.8 models.
- [x] 2026-09-28: Verified both public model options, all API and worker replicas, exact saved rates, zero active old-model course references, and decoded MP3 from both final-config models.

## Surprises & Discoveries

- Gemini 3.8 TTS uses `POST /v1beta/interactions`; the existing provider uses `models/{model}:generateContent` for preview models.
- Requesting `audio/l16` from Interactions preserves the existing PCM-to-MP3 pipeline. The default unary response is WAV.
- The US app connects through `SQLALCHEMY_DATABASE_URI`, not the legacy `MYSQL_DB` variables. Its actual database has active Gemini TTS rates and saved course selections that must be migrated during rollout.
- Interactions may return multiple ordered audio blocks; all blocks must be joined before transcoding. Google announces a price increase for both 3.8 TTS models on 2027-01-01, so rate records need separate effective periods.

## Decision Log

- Keep preview-model support for other deployments and add a model-specific Interactions path for 3.8.
- Keep the existing thirty prebuilt voices and character-based metering contract.
- Do not change production model exposure until the new backend is deployed. Map 2.5 Flash Preview to 3.8 Flash-Lite and 3.1 Flash Preview to 3.8 Flash in active course settings.
- Preserve existing character-based billing and scale the old rate by the supplier's Standard audio-output price ratio: 0.0027777600 credits/character for Flash-Lite and 0.0041666400 for Flash through 2026, doubled from 2027-01-01 UTC.

## Outcomes & Retrospective

Both 3.8 models returned playable MP3 through the deployed US API with positive, matching durations and unchanged usage-character counts. The public picker shows only the two 3.8 Gemini models. The migration updated 59 active course rows, and a readback confirmed zero active references to the two old models. The application database contains exact rates for the current period and the announced 2027 period. Volcengine remains the default and ElevenLabs remains available.

## Context and Orientation

The provider is `src/api/flaskr/api/tts/gemini_provider.py`. Focused tests are in `src/api/tests/service/tts/test_gemini_provider.py`. The US allowlist is in the separate `deploy-config` repository at `k8s/us/runtime-config.yaml`.

## Plan of Work

Add the two 3.8 model IDs, build the documented Interactions request for them, extract all returned audio blocks, and feed raw PCM through the existing transcoder. Keep the old `generateContent` path for preview models. Update the US configuration only after adapter validation.

## Concrete Steps

1. Add model IDs and an explicit Interactions model set.
2. Build and parse Interactions audio without exposing API credentials or audio payloads in logs.
3. Test request, response, error, and legacy behavior.
4. Run a credentialed synthesis smoke for both models.
5. Create exact rates for both new models, deploy the backend, and stage the US allowlist with both old and new models.
6. Migrate active course selections, remove the old models from the allowlist, and verify picker and synthesis.

## Validation and Acceptance

Both 3.8 models appear in the US TTS picker and synthesize playable MP3 through the existing pipeline. The output has a positive duration, valid MP3 data, and unchanged usage-character accounting. Existing preview-model tests continue to pass.

## Idempotence and Recovery

The code change requires no schema migration. To roll back after course selections have been migrated, first map active 3.8 Flash-Lite selections back to 2.5 Flash Preview and active 3.8 Flash selections back to 3.1 Flash Preview. Then restore the old US allowlist and restart the API and workers before reverting the backend. Review any courses edited after rollout before reversing their selections. Keep the new rate rows as historical configuration.

## Interfaces and Dependencies

The new path uses Google's Gemini Developer API Interactions endpoint and the current `GEMINI_API_KEY`, `GEMINI_TTS_API_URL`, and enabled switch. The US application database holds the active and future billing rate rows created by `k8s/us/migrate-gemini-tts-38.py` in deploy-config.

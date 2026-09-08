# Configurable Gemini Live admission capacity

## Purpose / Big Picture
Allow US operators to increase Live capacity without patching running containers. Keep current defaults for other environments.

## Progress
- [x] Verify US production image, flags, hardcoded limits and aggregate Redis occupancy.
- [x] Add five positive integer overrides with conservative fallback and Redis boundary tests.
- [ ] Verify and merge the API change through a focused PR.
- [ ] Persist US values in deployment configuration and roll out compatible API workers.
- [ ] Verify every US worker and Redis admission behavior after rollout.

## Surprises & Discoveries
US production runs two API replicas with rotation enabled. The shared limits are hardcoded; scaling pods cannot increase them. At inspection, Redis held five unexpired credentials across two users and no active owners.

## Decision Log
Keep defaults at 96 global credentials, 8 per user, 24 active owners, 4 user mints/minute and 24 global mints/minute. Set US overrides to 192, 16, 48, 8 and 48 respectively. Preserve legacy non-rotation credential limits, the 15-minute credential lifetime, accounting recovery and atomic Lua admission. Do not clear Redis ledgers.

## Outcomes & Retrospective
Implementation in progress; no production limit change claimed before runtime verification.

## Context and Orientation
`live_follow_up_admission.py` owns atomic admission. Environment definitions live in the central config registry. US deployment manifests are maintained in the separate deploy-config repository under k8s/us.

## Plan of Work
Pass validated app-config limits into the existing Lua script. Expose five environment variables and regenerate Docker examples. Verify default and custom boundaries with isolated real Redis. Deploy only the US overrides after the compatible API image is available.

## Concrete Steps
Run focused admission/config tests, Ruff and repository checks; create a ready PR. Persist configuration through a separate deployment PR. Roll out the approved image/configuration to ack-aishifu-us / ai-shifu-us, then inspect all API replicas.

## Validation and Acceptance
Existing defaults and accounting lifecycle tests pass. Each doubled bound accepts traffic at the former boundary and rejects at the new boundary with retry_after_ms. Invalid values retain defaults. Runtime workers report the configured values; readiness stays healthy.

## Idempotence and Recovery
Configuration can be reapplied. Roll back overrides to defaults without deleting credential ledgers; existing reservations naturally expire. Mixed-version rollout may temporarily retain stricter limits until old workers exit.

## Interfaces and Dependencies
New positive integer variables: GEMINI_LIVE_GLOBAL_CREDENTIAL_LIMIT, GEMINI_LIVE_USER_CREDENTIAL_LIMIT, GEMINI_LIVE_ACTIVE_SESSION_LIMIT, GEMINI_LIVE_USER_MINT_RATE_LIMIT, GEMINI_LIVE_GLOBAL_MINT_RATE_LIMIT. Capacity rejections additionally return capacity_scopes, an ordered array of stable machine enums: global_credentials, worker_credentials, user_credentials, active_sessions, user_mint_rate, global_mint_rate, and legacy_user_credential. Every simultaneously blocking scope is returned and logged server-side without user identifiers or Redis keys. The error_code and maximum retry_after_ms contract remain unchanged; other outcomes omit the new field. No Redis key schema changes.

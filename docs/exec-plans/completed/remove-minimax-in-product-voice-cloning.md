# Remove In-Product MiniMax Voice Cloning

## Purpose / Big Picture

Remove the course editor's in-product MiniMax voice cloning workflow, including
recording or uploading source audio and submitting asynchronous clone jobs.
Keep MiniMax TTS synthesis, externally cloned MiniMax voice IDs, operator
registration of those IDs, and the existing shared cloned-voice selection and
preview behavior. Preserve existing database records.

## Progress

- [x] 2026-09-27 CST: Confirmed the scope and distinguished in-product clone
  creation from external voice-ID registration.
- [x] 2026-09-27 CST: Remove clone creation UI, API, task, provider client, and
  clone-specific credit estimate.
- [x] 2026-09-27 CST: Keep external ID registration, validation, selection,
  preview, and MiniMax synthesis paths intact.
- [x] 2026-09-27 CST: Update docs and remove obsolete creation-only tests and
  translations.
- [x] 2026-09-27 CST: Run focused backend and frontend regression checks, then
  review the final diff and remaining MiniMax references.

## Surprises & Discoveries

- The existing cloned-voice record table is shared by MiniMax and Volcengine
  operator-registered voices. It must remain in place.
- The MiniMax provider configuration already disables teacher-side custom-ID
  entry; operator registration is the existing external-clone import path.

## Decision Log

- Remove only the workflow that records/uploads source audio and creates clone
  jobs inside AI-Shifu.
- Keep external MiniMax ID validation and operator registration, along with
  voice listing, selection, and preview behavior.
- Keep historical rows and schema; do not add a destructive data migration.
- Keep MiniMax provider synthesis and Volcengine cloned-voice behavior.

## Outcomes & Retrospective

Removed the course editor's recording/upload, clone submission, retry, cost
estimate, and demo-audio preview paths. Removed their backend provider client,
routes, Celery task, creation-only copy, and obsolete design proposal. Kept
external Voice ID entry/validation, operator registration, registered-voice
listing/selection, normal MiniMax synthesis, Volcengine support, and existing
database records.

Focused backend tests passed (203 tests across the two targeted runs), and
focused frontend tests passed (101 tests). Ruff passed on the changed backend
files checked. `npm run type-check` still reports an unrelated existing
`es-ES` locale-union mismatch in `src/lib/markdown-flow-locale.ts`. The repo
harness checker reads the Git index and reports the intentionally deleted,
unstaged files as missing.

## Context and Orientation

The authoring UI is `src/web/src/components/shifu-setting/ShifuSetting.tsx`.
Its in-product creation dialog is `MiniMaxVoiceCloneDialog.tsx`. The Flask
creation endpoint is registered in `src/api/flaskr/service/shifu/route.py`,
and creation work runs through `src/api/flaskr/service/tts/tasks.py` and
`minimax_voice_clone.py`. External voice registration is a separate operator
flow under `src/api/flaskr/service/shifu/admin_operations/voice_clones.py` and
the operations UI; preserve it.

## Plan of Work

Delete the authoring dialog and its recording/upload/submit UI. Remove the
clone-submission, clone-retry, single-record read/delete routes, background
task, provider clone client, and MiniMax clone cost estimate. Keep the voice
list path used to select externally registered voices. Keep the external ID
format validator, provider registry entry, operator registration API, and
runtime preview/synthesis behavior.

Remove creation-only translation keys and retire the now-obsolete design
proposal. Preserve clone-management translations still used to display
registered voices. Keep old database rows and migrations unchanged.

## Concrete Steps

1. Remove the course-setting clone dialog, recording helpers, submission state,
   creation-only API helpers, and creation-only copy across locales.
2. Remove backend clone submission/retry service paths, routes, task entrypoint,
   provider clone HTTP/audio-processing implementation, and clone-cost
   estimator. Keep generic voice row serialization and external registration.
3. Remove tests that only exercise in-product job creation/retry; preserve
   coverage files for external ID validation, registration, and TTS use.
4. Retire the design proposal and regenerate the repository documentation
   inventory.
5. Inspect the diff and search for stale references to the removed workflow.

## Validation and Acceptance

- The course settings UI contains no source-audio recording/upload or
  in-product MiniMax clone submission flow.
- No in-product MiniMax clone submit/retry endpoint or background task remains.
- External MiniMax Voice ID registration, voice selection, preview, and normal
  MiniMax TTS remain available.
- Volcengine cloned-voice support remains available.
- Existing database records and historical migrations are preserved.
- Run focused tests for external MiniMax ID validation, voice listing, normal
  TTS preview settings, and operator registration.

## Idempotence and Recovery

This change does not modify database contents or historical migrations. The
removed routes can be restored from version control if the workflow is
reintroduced. External registrations and existing cloned-voice rows remain
available.

## Interfaces and Dependencies

The frontend continues using the voice-list endpoint for external/previously
registered records. The backend continues using the
MiniMax TTS provider wrapper for ordinary synthesis and previews. The
operator-registration route remains the supported path for importing a voice
cloned outside AI-Shifu.

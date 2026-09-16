# Let learners defer personalization and find it later

## Purpose / Big Picture

Clicking “Later” in blocking onboarding opens a compact confirmation dialog. It
explains where personalization can be set later, using the personal menu's
localized entry name. “Start learning” submits the existing skip request and
opens the course on success. “Cancel” or Escape returns to the previous form or
conversation with all session state and drafts preserved. Remove the benefit
carousel; reuse the same modal shell and keep its form mounted.

## Progress

- [x] 2026-09-16 CST: Confirmed the interaction with the user and inspected the
      latest main, dialog, course gate, translations, and analytics consumers.
- [x] 2026-09-16 CST: Replace retention with a cancellable settings-location
      confirmation.
- [x] 2026-09-16 CST: Passed 136 tests, type checking, ESLint, translation
      parity/usage, and desktop/mobile interaction QA with simulated APIs.
- [x] 2026-09-16 CST: Passed the full Lefthook gate and final focused
      regressions. Publication and CI state are tracked on the PR.

## Surprises & Discoveries

The visible menu label is “个性化”; the hint interpolates that existing label.
The backend already remembers a successful skip, so no extra persistent frontend
reminder state is needed. A failed skip must preserve the session and draft and
display an error in the confirmation view.

## Decision Log

- Keep the existing skip API, course gate, settings entry, and save behavior.
- The user clarified that the reminder must be a confirmation with Cancel. The
  first click never persists. Initial focus goes to Cancel. While the skip
  request is pending, both buttons and Escape cancellation are disabled.
- Replace retention analytics with distinct defer-confirmation names; preserve
  the existing successful-skip event. Retired carousel UI, strings, and tests go
  away.
- Single-flight guards prevent duplicate requests; stale account/dialog
  completions must not close or show a hint in a later account/session.

## Outcomes & Retrospective

The compact confirmation replaces the carousel. Cancel/Escape restores the
existing form and conversation. Confirmation alone submits skip; failure remains
retryable and restores keyboard focus to Cancel. Browser QA used the production
component with local mock profile/skip responses at desktop and 390 x 844. It
verified draft preservation, pending controls, success, and failure. No
production account or backend state was changed.

## Context and Orientation

The shared profile dialog/controller/model live in
`src/web/src/components/profile-onboarding/`. The unchanged course gate in
`src/web/src/app/c/[[...id]]/hooks/useCourseProfileOnboardingGate.ts` owns
runtime release after a successful skip. Shared locale JSON is in `src/i18n/`.

## Plan of Work

Replace retention with a compact confirmation, preserving the underlying view.
Route both blocking defer buttons to confirmation; confirm alone calls skip.
Keep errors and retry in the confirmation and clear them on cancel/re-entry.
Update tests and all five locales, then run the relevant frontend and repository
checks.

## Concrete Steps

1. Simplify dialog/controller state and remove the carousel.
2. Add the localized hint and confirm/cancel actions in the existing modal.
3. Replace retired analytics producers and update regression coverage.
4. Generate i18n keys and documentation indexes; validate and publish a ready
   PR.

## Validation and Acceptance

- A defer click opens confirmation without submitting skip. Cancel/Escape
  restores the same draft, session, and original dialog frame.
- Pending duplicates do not submit again. Failure preserves draft/session and
  allows retry or cancel. Only confirmed success closes the dialog and releases
  runtime. Settings, guests, previews, and save do not show defer confirmation.
- Stale account/dialog requests cannot affect the new UI or analytics identity.
- Exact bounded analytics payloads, trigger order, retry outcomes, and tracking
  failure isolation are tested. All five locale key sets remain aligned.

## Idempotence and Recovery

No migration or API change. Failed requests can be retried. The existing
server-side skipped state prevents automatic onboarding and repeated hints on
later visits. Confirmation state is reset on scope changes.

## Interfaces and Dependencies

No public callback or dependency changes. Use the existing shared Dialog/Button.

### Defer confirmation analytics contract

- Business question: how often do learners cancel postponement after seeing the
  settings location, confirm it, and complete or fail the skip request?
- Metrics: weekly raw shown/cancelled confirmations, accepted skip attempts, and
  success/failed terminal results. Cancelled/shown measures return to setup,
  segmented by `source` and `phase`; failures divided by delivered results is
  the failure rate. Retries count separately. These are aggregate counts, not
  exact joins, distinct people, course-start rates, or causal uplift.
- Events: `profile_onboarding_defer_shown` after accepted entry to confirmation;
  `profile_onboarding_defer_cancelled` on accepted Cancel or Escape;
  `profile_onboarding_defer_attempt` before the confirmed skip request;
  `profile_onboarding_defer_result` once after true/void success, false, throw,
  or rejection. No result is emitted under a stale dialog/account identity.
- Population: logged-in learners in blocking course onboarding. Exclude guests,
  preview, hidden onboarding, dismissible settings, and rejected disabled
  clicks.
- Count/deduplication: one exposure per accepted entry, one cancellation per
  accepted return, and one operation guarded synchronously until it settles; a
  deliberate retry is a new operation. No persistent tracking key. Cancel and
  confirm have synchronous re-entry guards. A new confirmation after
  cancellation is a new decision cycle.
- Correlation: no feature identifier or profile/session content; only the shared
  transport owns pseudonymous identity and normalized routing context.
- Consumers: weekly product analysis. Repository search found no checked-in
  query/dashboard consuming retention events; retire that historical funnel and
  compare the new event family separately by release window.
- Compatibility: stop emitting `profile_onboarding_retention_*`; keep their
  historical meaning, with no backfill or renaming. Keep
  `profile_onboarding_skipped` and its `source`/`presentation` payload
  unchanged.
- Complete application payload: `source` (`guided`/`settings`), `presentation`
  (`blocking`), `phase` (`collect`/`save`); result adds `outcome`
  (`success`/`failed`). All fields are low-cardinality non-personal strings.
  Context freezes at confirmation entry, including the intended collection phase
  while data loads. No implicit identity, timestamp, or device fields are added.
- Verification: producer tests cover exact names/payloads, pending duplicates,
  loading/collection/editor phases, retries, failure isolation, stale accounts,
  no legacy retention emissions, and the unchanged skipped producer.

A successful skip does not prove later learning activity or profile completion.
The retained-completion metric is retired together with the benefit carousel.

# Explain personalization before deferring profile setup

## Purpose / Big Picture

Learners in the first-course blocking onboarding flow should understand the
concrete benefit of finishing personalization before they postpone it. The
first click on the blocking defer action (`module.profileOnboarding.skip`)
opens a retention view inside the existing learner profile dialog. That view
proves the benefit with four pure-text examples in
which the underlying fact stays fixed while the explanation changes for three
audiences. Only the explicit second defer action calls the existing skip API.

The settings entry remains dismissible and unchanged. No learner identity is
read to build the examples, and no model call, backend contract, database
change, or new storage is introduced.

## Progress

- [x] 2026-08-29 18:00 CST: Mapped the blocking defer path, dialog state,
      existing analytics, localization, and draft/session preservation rules.
- [x] 2026-08-29 22:00 CST: Added the single-dialog retention state, final
      defer boundary, localized text carousel, accessibility behavior, and
      focused state-machine tests.
- [x] 2026-08-30 10:30 CST: Kept the standard 900 x 760 desktop dialog frame
      and compacted typography so every Chinese slide shows all three
      explanations and controls without scrolling.
- [x] 2026-08-30 11:10 CST: Rebased onto current `origin/main`, removed the
      local-only forced-popup preview, and added the newly required analytics
      contract, privacy assertions, and failure-isolation coverage.
- [x] 2026-08-30 11:30 CST: Passed focused and caller tests, translations,
      TypeScript, ESLint, the repository harness, dev-tool verification, and
      the complete pre-commit gate; archive this plan for publication.
- [x] 2026-08-30 14:13 CST: Extended the decision funnel through durable
      profile-save completion so retained setup can be measured beyond the
      immediate return click.

## Surprises & Discoveries

The dialog shell already owns the session, assistant draft, nickname, and
profile draft. Keeping the underlying collect/save subtree mounted but hidden
while retention is visible preserves all of that state without a second dialog
or a new store.

The initial visual treatment fit an expanded frame but not the established
900 x 760 dialog. Large-screen Tailwind breakpoints were reacting to viewport
width rather than dialog width. A 30 / 20 / 18 / 16 px desktop hierarchy plus
tighter internal spacing makes all four Chinese slides fit, while the existing
middle-content scrolling remains available for longer locales.

The latest `main` added the contract in
`docs/references/frontend-product-analytics.md`. The retention event family
therefore requires a versioned metric, payload, privacy, deduplication, and
failure-isolation contract in this plan. Final review also found that retention
must take precedence over the loading body, that a failed final defer must not
leak its error into the restored collect/save view, and that an immediate
continue click is not sufficient evidence of eventual setup completion.

## Decision Log

- Add `defer-retention` to the internal confirmation state. Do not create a
  nested dialog or change the public backend API.
- Apply retention only when `exitPolicy` is `blocking` and `onDefer` exists.
  Dismissible settings cancellation and close behavior stay unchanged.
- The first accepted defer click changes only local dialog state and emits the
  retention exposure event. It does not call the skip API, close the dialog,
  clear browser drafts, or emit `profile_onboarding_skipped`.
- The retention continue action
  (`module.profileOnboarding.dialog.retention.continueSetup`) restores the prior
  collect or save phase and preserves the mounted conversation, session,
  assistant draft, nickname, and profile draft. Its frozen analytics context is
  retained until a durable profile save succeeds so completion can be
  attributed to the retention funnel.
- The final defer action (`module.profileOnboarding.dialog.retention.defer`)
  reuses the existing single-flight skip path. Both actions and the carousel
  freeze while that request is pending. An attempt event precedes the request,
  and exactly one result event records `success` or `failed`. Failure stays on
  the retention view; success also emits the existing skipped event, clears the
  draft, and releases the blocking gate.
- Use four localized static slides. Each keeps one question and three
  simultaneous audience-specific text explanations. Do not infer or display
  the current learner's real identity.
- Autoplay advances every eight seconds without a visible play/pause control.
  Hover and page hiding pause temporarily; touch, scrolling, focus, or manual
  navigation hands control to the reader. Reduced-motion disables autoplay and
  transition animation.
- Keep the standard dialog frame and existing header/footer. Desktop lays out
  audience labels beside explanations; mobile stacks them and lets the dialog
  body own scrolling.

## Outcomes & Retrospective

Implementation is complete. The retention step is a reversible local view,
not a persistence boundary, and the final skip remains the only operation that
changes onboarding state. The compact text hierarchy communicates the benefit
before the examples while keeping the complete proof visible in the existing
dialog frame.

Final verification passed five Jest suites with 139 tests across the retention
view, shared dialog/model, course blocking gate, and admin settings caller.
TypeScript, ESLint (existing warnings only), five-locale parity and usage,
generated i18n types, repository knowledge generation, the repository harness,
architecture checks, dev-tool verification, Prettier, Ruff, and the complete
Lefthook pre-commit gate passed. Browser QA covered the standard 900 x 760
desktop frame, mobile, short-height, Arabic RTL, reduced motion, and all four
Chinese slides; each Chinese slide displayed its question, three explanations,
and controls without internal overflow. Pull-request CI and review status are
tracked on the PR rather than as unchecked implementation milestones here.

## Context and Orientation

- `src/web/src/components/profile-onboarding/LearnerProfileDialog.tsx`
  owns the shared dialog shell, content switching, fixed chrome, and actions.
- `useLearnerProfileDialogController.ts` owns defer guards, draft/session
  preservation, API submission, and analytics producers.
- `learnerProfileDialogModel.ts` owns the internal confirmation state.
- `LearnerProfileRetentionView.tsx` owns the static slides, responsive layout,
  autoplay, manual navigation, and screen-reader announcements.
- `src/i18n/*/modules/profile-onboarding.json` owns all visible and accessible
  retention text for the five supported locales.
- `events.ts` owns the profile-onboarding event-name constants.

## Plan of Work

Extend the existing dialog state machine with a reversible retention state,
route only the blocking defer action through it, and keep the original phase
mounted so returning is lossless. Add the localized pure-text proof carousel
and its motion, input, and accessibility behavior. Preserve the existing final
skip API path and document the additive analytics funnel. Verify behavior,
privacy, localization, standard-frame layout, and repository gates.

## Concrete Steps

1. Add the `defer-retention` internal state and guarded enter/continue handlers.
2. Render the retention view and actions inside the current dialog, preserving
   the collect/save subtree and focus restoration.
3. Keep final defer single-flight and show its failure only in retention.
4. Add four localized text slides, eight-second autoplay, reader-control
   handoff, reduced-motion behavior, RTL controls, and responsive scrolling.
5. Add safe additive analytics producers and the contract below.
6. Regenerate i18n key types and add focused component/controller tests.
7. Run focused tests, translations, type checking, lint, repository harness,
   pre-commit hooks, and visual QA before creating a ready PR.

## Validation and Acceptance

- The first blocking defer action (`module.profileOnboarding.skip`) displays
  retention in the same dialog and does not call the skip API or emit the
  skipped event.
- Continue restores the exact prior phase, DOM-backed conversation, session,
  nickname, profile draft, and assistant draft.
- Final defer is single-flight and emits one attempt plus one terminal result.
  Failure keeps both actions retryable in retention; success alone clears the
  draft and closes/releases the gate.
- Settings cancellation, Escape/outside-click rules, close behavior, backend
  state, and onboarding status semantics remain unchanged.
- Autoplay loops every eight seconds; manual/touch/scroll/focus behavior,
  visibility pause, reduced motion, silent automatic changes, polite manual
  announcements, and RTL arrows are covered.
- All five locales contain the same key structure, and generated key types are
  current.
- At desktop the dialog remains 900 x 760 and all three Chinese explanations
  plus controls fit on every slide. Mobile, short-height, long-language, and RTL
  layouts retain a reachable single-scroll experience.
- Analytics tests prove exact safe payloads, accepted-trigger deduplication,
  durable retained-completion timing, final-defer timing, prohibited-field
  absence, and fail-open behavior.

## Idempotence and Recovery

The retention view is local component state. Re-entering it after returning to
setup intentionally starts a new decision cycle; closing or changing account
uses the existing dialog reset. Autoplay timers and listeners clean up on
unmount. A failed skip preserves all local and durable state and can be retried.
Generators and tests are safe to rerun. No migration or backfill exists.

## Interfaces and Dependencies

`LearnerProfileDialogConfirmation` gains the internal value
`defer-retention`. No backend route, DTO, database schema, public provider, or
package dependency changes. The existing `onDefer(sessionId?)` callback remains
the sole skip boundary.

### Profile onboarding retention decision events

- Business question: when an eligible learner is about to postpone blocking
  profile setup, how often does the benefit explanation lead them back to
  setup, how often does that return lead to a durable profile save, how often do
  they still attempt to defer, and what share of delivered defer results fail?
- Metric definition: for each rolling seven-day window, report raw accepted
  `profile_onboarding_retention_continued` divided by raw accepted
  `profile_onboarding_retention_shown` as the return-to-setup rate; raw
  `profile_onboarding_retention_completed` divided by raw continued as the
  post-return completion rate; raw completed divided by shown as the retained
  setup-completion rate; and raw
  `profile_onboarding_retention_defer_attempt` divided by shown as the final
  defer-attempt rate. Report failed `profile_onboarding_retention_defer_result`
  events divided by all delivered defer-result events as the terminal failure
  rate. Segment all rates by `source` and `phase`. Counts are decision cycles,
  successful saves, or attempts, not distinct users; a deliberate retry is a
  new attempt. Each cycle freezes `source`, `presentation`, and `phase` when
  retention is shown, and all later decision events reuse that context. When
  the blocking gate is still loading profile details, its known auto-start
  target is classified as `collect` rather than the reducer's temporary default
  phase. Without a correlation ID, aggregate continued/completed and
  attempt/result ratios must not be presented as exact per-cycle joins or as
  causal uplift. Incremental lift requires a separately designed control or
  experiment cohort.
- Event names: `profile_onboarding_retention_shown`,
  `profile_onboarding_retention_continued`,
  `profile_onboarding_retention_completed`,
  `profile_onboarding_retention_defer_attempt`, and
  `profile_onboarding_retention_defer_result`.
- Actor and surface: authenticated learners in the fixed
  `course_blocking_profile_onboarding` surface. The surface is fixed by the
  guarded dialog path and is not duplicated in the payload.
- Trigger: `shown` fires after the first defer handler passes all guards and
  accepts the transition into retention. `continued` fires after the primary
  retention action passes its guards and before the dialog restores the prior
  phase. `completed` fires after a later profile-save API confirms durable
  success and before dialog cleanup, only when the learner previously accepted
  continue for a retention cycle. `defer_attempt` fires after all single-flight
  guards accept the final defer action and before `onDefer` starts.
  `defer_result` fires exactly once when `onDefer` returns success, returns
  `false`, throws, or rejects; later dialog cleanup failure cannot change that
  terminal result. Automatic slide changes and carousel controls do not emit
  decision events. The existing skipped event still fires only after the skip
  API confirms success.
- Population: include authenticated learners for whom the course gate renders
  blocking onboarding. Exclude guests, preview mode, hidden onboarding,
  dismissible settings entry, ordinary close/cancel, render-only states, and
  clicks rejected while collection or submission is in flight.
- Count unit: one accepted retention entry for `shown`, one accepted return
  action for `continued`, one durable profile save after retained return for
  `completed`, and one accepted final-defer operation for each attempt/result
  pair.
- Deduplication: React state and single-flight guards allow at most one event
  per accepted state transition and exactly one terminal result per accepted
  defer attempt. The frozen context survives failed save attempts and is
  cleared after the first durable save, so save retry emits at most one
  `completed`. Re-render, pending duplicate clicks, and disabled clicks do not
  count. A deliberate defer retry after failure is a new attempt. There is no
  persisted user/session deduplication; a deliberate later re-entry is a new
  cycle.
- Correlation: no feature-owned identifier is collected. Events can be
  compared only in aggregate by ingestion window and bounded enums. The shared
  helper's inherited user ID is not approved as a new consumer dependency.
- Consumers: weekly aggregate onboarding-retention analysis owned by the
  product team. No production dashboard, experiment, or correctness-sensitive
  workflow is changed in this PR.
- Compatibility: additive event names with no historical backfill or rename.
  A successful defer dual-writes the new result with `outcome: success` and the
  existing `profile_onboarding_skipped`; the skipped name and payload remain
  unchanged.
- Verification: focused dialog tests assert exact triggers and payloads,
  repeat-entry behavior, double-click/single-flight guards, durable completion
  timing, save retry, final-defer timing, `false`/throw/reject failures, cleanup
  failure, prohibited-field absence, and synchronous/asynchronous analytics
  failure isolation.

| Event                                        | Trigger                                                       | Feature-owned fields                         |
| -------------------------------------------- | ------------------------------------------------------------- | -------------------------------------------- |
| `profile_onboarding_retention_shown`         | Accepted transition from blocking collect/save into retention | `source`, `presentation`, `phase`            |
| `profile_onboarding_retention_continued`     | Accepted primary action that restores collect/save            | `source`, `presentation`, `phase`            |
| `profile_onboarding_retention_completed`     | Durable profile save after an accepted retained return        | `source`, `presentation`, `phase`            |
| `profile_onboarding_retention_defer_attempt` | Accepted final-defer operation before its request starts      | `source`, `presentation`, `phase`            |
| `profile_onboarding_retention_defer_result`  | One terminal result after the final-defer request settles     | `source`, `presentation`, `phase`, `outcome` |

| Field          | Type   | Allowed values       | Cardinality | Privacy class     | Why required                                                   |
| -------------- | ------ | -------------------- | ----------- | ----------------- | -------------------------------------------------------------- |
| `source`       | string | `guided`, `settings` | low         | non-personal enum | distinguish the collection intent that owns the retained draft |
| `presentation` | string | `blocking`           | low         | non-personal enum | protect the retention population boundary                      |
| `phase`        | string | `collect`, `save`    | low         | non-personal enum | compare whether learners return to questions or profile review |
| `outcome`      | string | `success`, `failed`  | low         | non-personal enum | distinguish confirmed defer completion from terminal failure   |

The feature-owned payload explicitly excludes nickname, learner profile,
answers, question or slide text, session/dialog IDs, course or lesson IDs,
errors, URLs, and timestamps. The shared `useTracking` helper currently adds
the inherited fields below. They are recorded for complete delivered-schema
review, not copied into feature code and not approved as dependencies for new
consumers.

| Inherited field | Type / values                     | Cardinality | Privacy class             | Compatibility note                                             |
| --------------- | --------------------------------- | ----------- | ------------------------- | -------------------------------------------------------------- |
| `user_type`     | string: `guest`, `user`, `member` | low         | non-personal enum         | helper-owned; eligible events should be `user` or `member`     |
| `user_id`       | stable numeric account ID         | high        | pseudonymous machine ID   | grandfathered helper field; not required by this metric        |
| `device`        | string: `H5`, `Web`               | low         | non-personal enum         | helper-owned presentation context                              |
| `timeStamp`     | localized string                  | high        | non-personal legacy value | grandfathered debt; consumers use Umami ingestion time instead |

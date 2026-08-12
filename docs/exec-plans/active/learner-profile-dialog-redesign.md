# Learner Profile Dialog Redesign

## Purpose / Big Picture

Replace the learner-facing full-page personalization settings and legacy
three-field onboarding experience with one responsive learner-profile dialog.
Learners stay in the active lesson, write one natural-language introduction,
and let the AI teacher use that canonical profile across courses. The dialog
never exposes nickname extraction or the legacy `sys_user_nickname`,
`sys_user_background`, and `sys_user_style` variables. Existing courses keep
their historical variables and runtime compatibility. When an explicit name
can be safely recognized from the canonical profile, `user_users.nickname` is
updated in the same transaction without adding a second editable field.

The selected visual truth began with the revised option-three mock at
`/Users/sunner/.codex/generated_images/019fe96e-310e-71e1-b426-efff9e67343f/exec-8c6fc012-e17d-4cbd-99c3-4838c2409753.png`
and was refined by direct user feedback: the active dialog has only its
secondary action and primary save action, with no clear or overflow control.

## Progress

- [x] 2026-08-11 10:20 CST: Inspected the current desktop screenshot, generated
      three responsive dialog directions, and selected/revised direction three
      with the user.
- [x] 2026-08-11 10:40 CST: Mapped the current menu, full-page settings,
      automatic onboarding, canonical CRUD, legacy variable, sign-in merge, and
      user-info nickname paths.
- [x] 2026-08-12 06:20 CST: Implement the shared responsive learner-profile
      dialog and replace the full-page learner settings entry.
- [x] 2026-08-12 06:20 CST: Route first-time onboarding through the canonical
      dialog while retaining the old backend wire contract for compatibility.
- [x] 2026-08-12 06:20 CST: Add background nickname recognition and atomic
      user-info synchronization without displaying parsing metadata.
- [x] 2026-08-12: Refine the selected visual target from direct user feedback
      so the active dialog exposes no clear or overflow action.
- [ ] 2026-08-12 06:20 CST: Focused backend/frontend behavior, type-check,
      ESLint, Ruff, translation, architecture, repository harness, and production
      build checks pass. Browser-rendered desktop/mobile comparison remains blocked
      by the selected in-app browser's localhost security policy.

## Surprises & Discoveries

- The current “个性化设置” is not a dialog: `ChatUi` hides the lesson and
  absolutely positions `UserSettings` across the full learning canvas.
- The page has two saves. The outer save writes avatar, birth, sex, nickname,
  every dynamic field, and legacy system variables before the canonical
  profile section performs its own save.
- First-course onboarding remains a separate legacy MarkdownFlow questionnaire
  that writes the same three `sys_*` values. Removing only the settings fields
  would leave the obsolete data-entry path active.
- Runtime nickname substitution currently prefers `user_users.nickname` over
  historical variable rows, so canonical nickname synchronization can preserve
  old-course reads without creating new legacy rows.
- The canonical profile is free-form multilingual prose. Recognition must be
  conservative and deterministic: only explicit forms of address become the
  account nickname, and a profile without one yields an empty derived nickname.
- Eligibility and profile requests can outlive account or dialog-mode changes.
  Runtime readiness therefore has to be keyed by account, not held as a single
  boolean, and user-info refresh must reject stale token or user-ID results.
- A canonical clear remains a handled profile mutation for compatibility, but
  the redesigned dialog no longer exposes it. The modern DELETE endpoint and
  legacy `LearnerProfileSettingsSection` clear flow remain stable interfaces.

## Decision Log

- Decision: use one shared `LearnerProfileDialog` for menu editing and
  first-time presentation.
  Rationale: one component gives the same load, save, moderation,
  account-switch, accessibility, and responsive behavior at every entry.
- Decision: show only the context-appropriate secondary action and primary
  save action in the redesigned dialog; do not expose clear or overflow UI.
  Rationale: direct user feedback preferred a simpler active flow. The modern
  DELETE API and legacy settings-section clear behavior stay available as
  compatibility contracts rather than dialog actions.
- Decision: keep exactly one stored learner-profile text and show no parsed
  nickname or derived metadata in the dialog.
  Rationale: the learner should experience name recognition as a background
  consequence of a natural introduction, not as another field to manage.
- Decision: recognize only explicit, bounded address phrases in supported
  languages and treat the result (including no result) as the derived account
  nickname; clearing the canonical profile clears that derived nickname.
  Rationale: the user explicitly made the learner profile the source of truth
  for nickname while keeping recognition invisible in the UI. A deterministic
  recognizer avoids a second provider call, raw-profile logging, and
  nondeterministic save failures.
- Decision: update `learner_profile`, its timestamp, derived nickname, and
  profile-v2 state in the existing unit of work.
  Rationale: moderation or database failure must not leave a half-synchronized
  account.
- Decision: stop new UI writes to the three legacy variables, but do not delete
  their definitions, rows, endpoints, parser, or runtime resolution.
  Rationale: old courses and rolling deployments still depend on those
  contracts.
- Decision: keep the existing handled behavior for “稍后再说” by writing only
  the legacy onboarding sentinel through the stable skip wire contract.
  Rationale: dismissing must not create any of the three obsolete `sys_*`
  values, but it also must not nag the learner on every reload or course.

## Outcomes & Retrospective

The learner now stays inside the lesson while one shared responsive dialog
collects a single natural introduction. No legacy nickname/background/style
fields or parsed nickname are displayed. A moderated save atomically updates
the canonical profile, profile-v2 handled state, and a conservatively derived
account nickname; clear atomically empties the profile and nickname while
remaining handled through the stable compatibility API. The redesigned dialog
itself presents only its secondary action and save. Historical `sys_*` rows
and old-course reads remain intact.

Focused verification currently reports 83 canonical-profile backend tests, 13
manual-activation compatibility tests, and 54 combined frontend flow/component
tests passing, plus type-check, focused ESLint, repository-pinned Ruff 0.15.13,
translation parity/usage, architecture, repository harness, UoW ratchet, and a
production build. The installed local Ruff 0.16.2 makes the repository-wide
lefthook run fail on pre-existing baseline findings; all other hook jobs pass,
and the pinned changed-file Ruff command passes. The final browser-rendered
desktop/mobile comparison remains blocked and is recorded in the root
`design-qa.md`; this plan must not be marked complete until that report says
`final result: passed`.

## Context and Orientation

The learner route and onboarding gate live in
`src/cook-web/src/app/c/[[...id]]/page.tsx`. The current learner menu is
`src/cook-web/src/c-components/NavDrawer/MainMenuModal.tsx`; the full-page
settings composition is under
`src/cook-web/src/app/c/[[...id]]/Components/Settings/`. Reusable profile UI
belongs under `src/cook-web/src/components/profile-onboarding/`, with modern
transport in `src/cook-web/src/api/learnerProfile.ts` and shared translations
under `src/i18n/`.

Canonical persistence, moderation, fixed profile-v2 state, and sign-in merge
live in `src/api/flaskr/service/profile/learner_profile.py`. Authenticated
routes are in `src/api/flaskr/route/user.py`. Legacy variable persistence and
runtime projection remain in `src/api/flaskr/service/profile/funcs.py` and the
legacy onboarding service remains in
`src/api/flaskr/service/profile/onboarding.py`.

## Plan of Work

1. Build a controlled, account-scoped `LearnerProfileDialog` from the shared
   Radix dialog, `ProfileDraftEditor`, modern learner-profile API, and existing
   stale-response protections.
2. Change the avatar-menu row into a semantic button that closes the menu and
   opens the dialog without hiding the lesson. Remove learner-personalization
   props and rendering from `ChatUi`.
3. Replace the automatic legacy questionnaire presentation with the same
   canonical dialog while keeping the legacy GET as the rollout-safe
   eligibility signal and retaining the old complete endpoint/client/parser.
4. Hide the three legacy variables from all new settings surfaces and stop the
   learner-profile flow from calling legacy profile updates. Preserve unrelated
   course-defined variables outside this dialog.
5. Add conservative nickname recognition in the canonical service and apply a
   recognized nickname inside the existing profile/state unit of work. Refresh
   frontend user info after accepted saves.
6. Add focused tests for entries, responsive/accessible behavior, load/save/
   error/dismiss/account-switch behavior, nickname recognition and atomicity,
   plus compatibility coverage for the modern DELETE endpoint and legacy
   settings-section clear flow.
7. Capture desktop and mobile implementations, compare them with the selected
   mock, fix P0-P2 differences, and record `design-qa.md` with a passing result.

## Concrete Steps

- Reuse `Dialog`, `Button`, `ProfileDraftEditor`, `getLearnerProfile`,
  `updateLearnerProfile`, `refreshUserInfo`, and `learner-profile-changed`; do
  not add another request client. Preserve `clearLearnerProfile` for existing
  compatibility consumers, but do not expose it in the redesigned dialog.
- Keep the dialog header/footer visible and the body scrollable; use a centered
  approximately 720-pixel desktop surface and a near-full-height mobile sheet
  with at least 44-pixel actions.
- Provide three optional writing-prompt buttons that only focus/seed the same
  textarea. The complete placeholder must cover address, background, existing
  foundation, goal, current problem, explanation preferences, and scenarios.
- Do not add or regenerate a database migration. Nickname already belongs to
  `user_users`.
- Preserve legacy endpoint payloads and historical rows; focused diff checks
  must prove no accidental deletion or rewrite.

## Validation and Acceptance

- Opening “学习者画像” closes the account menu, leaves the lesson visible, and
  opens a focus-managed dialog on desktop and a usable sheet on mobile.
- The dialog contains one learner-profile textarea, complete example guidance,
  a context-appropriate secondary action and primary save action, inline error
  and retry states, and no clear/overflow or editable/parsed
  nickname/background/style controls.
- Saving a moderated profile writes profile, profile-v2 handled state, and the
  safely derived nickname atomically; no recognizable name stores an empty
  nickname. Clearing the profile clears the derived nickname and marks the
  profile handled.
- New learner flows do not call legacy profile-write endpoints or create new
  `sys_*` rows. Existing historical rows, old backend wire contracts, old
  course variable resolution, Teaching, Ask, and preview behavior remain
  covered.
- The modern DELETE endpoint and the legacy `LearnerProfileSettingsSection`
  clear behavior remain stable compatibility interfaces even though the active
  dialog does not expose a clear action.
- Direct menu editing and first-time presentation share account-switch and
  late-response guards. Load failure is recoverable and never blocks the
  lesson.
- Focused pytest/Jest pass, followed by Ruff, type-check, ESLint, translation,
  architecture, repository harness, developer-tool, lefthook, and design-QA
  gates.

## Idempotence and Recovery

All changes are ordinary source patches and tests. No migration is generated
or applied. Re-running focused tests, generators, static checks, screenshots,
and design QA is safe. If a mixed legacy file regresses, restore only that
file from the current branch head and reapply the narrow dialog or compatibility
hunk; never reset the entire worktree or touch another worktree.

## Interfaces and Dependencies

- Database: existing `user_users.nickname`, `learner_profile`,
  `learner_profile_updated_at`, and fixed `user_onboarding_states` profile-v2
  row; no schema change.
- Backend: stable `GET|PUT|DELETE /api/user/learner-profile`, legacy
  `GET|POST /api/user/profile-onboarding[/complete]`, canonical moderation and
  unit-of-work helpers. DELETE remains a compatibility interface and is not an
  action in the redesigned dialog.
- Frontend: shared `LearnerProfileDialog`, modern learner-profile API,
  `useUserStore.refreshUserInfo`, `learner-profile-changed`, account menu and
  course onboarding gate.
- Visual target: revised generated mock path recorded above, with the direct
  user-feedback refinement that removes clear/overflow UI; implementation is
  verified at desktop and mobile viewports before handoff.

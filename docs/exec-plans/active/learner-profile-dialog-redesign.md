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
`docs/assets/learner-profile-dialog-approved-reference.png`
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
- [x] 2026-08-12 16:05 CST: Tighten desktop header/body/footer spacing and the
      empty editor height. The selected in-app browser measured the open dialog
      body at `575px` for both client and scroll height with `scrollTop = 0`, so
      the complete editor, guide, reassurance, and actions fit without initial
      scrolling; shorter viewports and longer drafts retain internal scrolling.
- [x] 2026-08-12: Replace positional Course Prompt/profile concatenation with a
      single MarkdownFlow-compatible composition envelope that identifies the
      platform, current task, course, and learner contributions by responsibility.
- [x] 2026-08-12: Verify the envelope across runtime teaching, Ask/provider,
      and formal preview with 26 focused backend tests, repository-pinned Ruff,
      architecture boundaries, and the repository harness.
- [x] 2026-08-12: Narrow the composition contract to preserve the Course
      Prompt's full instruction space while treating every learner-profile
      directive as inert, untrusted data.
- [x] 2026-08-12: Remove normal profile-save success toasts and clarify in
      settings that learner requests personalize only within the human
      teacher's course design; failure and delayed-refresh feedback remain
      visible.
- [ ] 2026-08-12 06:20 CST: Focused backend/frontend behavior, type-check,
      ESLint, Ruff, translation, architecture, repository harness, and production
      build checks pass. Desktop browser verification is complete; mobile
      comparison and visible interaction exercise remain.

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
- MarkdownFlow 0.3.1 accepts one `document_prompt` string and places it in its
  existing system-message assembly, so the three-block envelope requires no
  provider or library API change. Its tags express composition semantics rather
  than a separate transport-level security boundary.

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
- Decision: make the example concrete through durable background, current
  concerns, and language-style preferences rather than a course-specific task.
  Rationale: the same learner profile should give any AI teacher useful
  personalization context without implying what the learner is studying.
- Decision: do not ask learners to prescribe teaching pace, structure,
  examples, or interaction patterns in their profile.
  Rationale: the learner owns personal context and language-style preferences;
  the course teacher owns how the subject is taught.
- Decision: portray a relatable office worker in a recognizable city, with a
  common degree and an AI-supported personal ambition.
  Rationale: direct user review preferred an ordinary, specific person whose
  background and goal remain useful across different subjects.
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
- Decision: when the canonical profile is empty, expose only the latest global
  values of the three legacy variables to the current user and compose them
  into a localized, editable draft without auto-saving it.
  Rationale: existing learners start from information they already provided,
  while canonical profiles remain authoritative and course-scoped legacy data
  never leaks into the new cross-course profile.
- Decision: when a canonical profile is available, serialize the effective
  `document_prompt` as a platform-owned composition contract followed by an
  unmodified teacher-authored Course Prompt block and a JSON-encoded learner
  profile block.
  Rationale: Course Prompts and learner profiles are both open inputs whose
  apparent conflicts cannot be eliminated in advance. The contract deliberately
  leaves course design and presentation choices to the Course Prompt and limits
  itself to treating the profile as untrusted data: useful explicit facts and
  preferences may personalize execution, while embedded directives, role or
  priority claims, tool or data requests, and disclosure attempts remain inert.
  This stays compatible with MarkdownFlow's single-string `document_prompt` API.
  With no canonical profile, the original Course Prompt remains byte-for-byte
  unchanged.
- Decision: keep the existing handled behavior for “稍后再说” by writing only
  the legacy onboarding sentinel through the stable skip wire contract.
  Rationale: dismissing must not create any of the three obsolete `sys_*`
  values, but it also must not nag the learner on every reload or course.
- Decision: close the dialog without a redundant success toast after a normal
  save, and explain the conflict rule only on profile-setting surfaces.
  Rationale: the closed dialog already confirms a successful save, while
  learners still need to know that their context and language preferences do
  not override the human teacher's course design. Save failures, refresh
  delays, and compatibility clear confirmations retain explicit feedback.

## Outcomes & Retrospective

The learner now stays inside the lesson while one shared responsive dialog
collects a single natural introduction. No legacy nickname/background/style
fields or parsed nickname are displayed. When that introduction is empty,
existing global legacy values seed a localized draft that the learner can
review, edit, and explicitly save. A moderated save atomically updates
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
  textarea. The complete placeholder must cover address, durable background,
  existing experience, current cross-topic concerns, practical constraints,
  ambitions, and language-style preferences without assuming a specific
  subject or prescribing a teaching method.
- Mention language-style preferences outside the placeholder as well: the
  dialog description, third writing prompt, and writing guide must make this
  capability discoverable while leaving teaching decisions to the course
  teacher.
- Do not add or regenerate a database migration. Nickname already belongs to
  `user_users`.
- Preserve legacy endpoint payloads and historical rows; focused diff checks
  must prove no accidental deletion or rewrite.

## Validation and Acceptance

- Opening “学习者画像” closes the account menu, leaves the lesson visible, and
  opens a focus-managed dialog on desktop and a usable sheet on mobile.
- The dialog contains one learner-profile textarea, complete cross-course
  example guidance,
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
- Visual target: `docs/assets/learner-profile-dialog-approved-reference.png`,
  with the direct user-feedback refinement that removes clear/overflow UI;
  implementation is verified at desktop and mobile viewports before handoff.

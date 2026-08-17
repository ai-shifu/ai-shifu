# Unified Learner Profile Dialog

## Purpose / Big Picture

Learners should experience research, AI optimization, editing, and saving as
one personalization workflow. The existing learner-profile dialog becomes the
only shell: learners without a canonical profile answer guided questions,
receive an automatically optimized draft, and confirm it; learners with a
profile open directly in the same editor and may restart research there.

Research and optimization are draft-only. The final primary action is the only
operation that persists the canonical learner profile and profile-v2 state.

## Progress

- [x] 2026-08-17 CST: Rebased the guided-profile branch onto current `main`
      and mapped the existing dialog, course gate, session runtime, optimizer, and
      completion contracts.
- [x] 2026-08-17 CST: Added atomic optional nickname support to guided
      completion.
- [x] 2026-08-17 CST: Replaced the nested rerun modal with one internal dialog
      state machine.
- [x] 2026-08-17 CST: Routed course blocking and non-blocking onboarding through
      the unified dialog.
- [x] 2026-08-17 CST: Rebased onto `main` at `47de277ef`, installed the
      lockfile-pinned `markdown-flow-ui` 0.2.10, and completed focused, static,
      repository, and responsive browser gates.
- [x] 2026-08-17 CST: Collapsed the course's automatic and menu entry points
      into one mounted dialog instance, preserving its draft and research session
      when eligibility changes the exit policy in place.
- [x] 2026-08-17 CST: Compacted the guided-only collection and save views,
      generalized the internal collection boundary, and revalidated the unified
      dialog without introducing any PR3 import experience.

## Surprises & Discoveries

The canonical profile service already supports atomically saving an optional
nickname; only the profile-v2 completion service and wire contract need to
expose it. The guided conversation already returns an unsaved terminal draft,
so automatic optimization can run before completion without changing the
MarkdownFlow runtime.

The first short-height browser pass exposed a nested-scroll regression: the
conversation input could sit behind the fixed footer at 320 x 568. Keeping the
dialog body fixed during research and making the conversation the only body
scroll region restored a reachable question area without changing the shell
size. A final dependency sync also found that the original shared
`node_modules` link still contained `markdown-flow-ui` 0.2.6; a clean install
from the current lockfile verified the implementation against 0.2.10.

The compact disclosure added a second short-height edge: when expanded, it
could consume the collection area's remaining height. The final layout keeps a
minimum usable conversation region and lets the dialog body carry overflow,
so the disclosure can expand without disappearing behind the fixed footer. A
terminal draft that is empty or above the editor limit also still passes
through the visible processing state and returns to the editor with an error
instead of silently skipping the transition.

## Decision Log

- `LearnerProfileDialog` is the only dialog shell. Research, optimizing, and
  review are internal views rather than nested dialogs.
- Each page host renders one stable `LearnerProfileDialog` instance per account
  scope. Automatic eligibility and menu actions only open the instance or
  change its exit policy; they never select a second mount or reset its step.
- If a pending course gate becomes blocking while a settings discard prompt is
  visible, the prompt is dismissed without discarding the draft; the same
  dialog then exposes only the blocking-safe save or explicit-defer exits.
- Dirty-discard and research-replacement confirmations are inline dialog views,
  so the workflow never creates a second focus trap.
- A missing canonical profile starts research when guided configuration is
  available. An existing profile starts review. Missing or broken guided
  configuration falls back to the manual editor.
- A terminal research draft starts optimization automatically. Optimization
  success replaces the draft; failure exposes the research draft with retry
  and still permits saving.
- Opening an existing profile never optimizes or rewrites it automatically.
- Restarting research with dirty edits requires explicit confirmation. Once a
  new terminal result is produced it replaces the in-memory draft without an
  undo path; nothing is persisted until final save.
- Fresh research uses the `onboarding` intent. Reruns use `settings`.
- Course blocking retains its single explicit defer action and cannot close by
  Escape, outside click, or an X button. Settings keeps normal close and dirty
  discard confirmation.
- Nickname is never inferred by research or optimization. When supplied on
  guided completion, it saves atomically with the profile and v2 state.
- The dialog keeps the persistent purpose statement: "让 AI 老师了解你的背景和偏好，以更适合你的方式讲课。"
  It does not render a step indicator.
- The guided collection view contains only its short title, an approximately
  one-minute expectation, the official MarkdownFlow conversation, and a
  collapsed information-usage disclosure.
- The save view keeps the nickname label without presenting it as optional,
  the learner-profile editor, contextual optimization feedback, and footer
  actions. It removes the prompt cards, default optimization explanation,
  confirmation description, and persistent reassurance copy.
- "互动收集" is a secondary footer action at the same action level as save.
  Blocking keeps "以后再说" visually separate as its low-emphasis defer
  action.
- Internal state uses the neutral collection phases `collect`, `processing`,
  and `save`, but the only implemented collector remains guided MarkdownFlow.
  Familiar-AI import, paste UX, method selection, browser draft storage, and
  route-selection analytics remain deferred to PR3.

## Outcomes & Retrospective

Research is now one way to create or replace the draft inside the existing
personalization editor, not a second feature or nested modal. Learners without
a profile enter guided questions when available and otherwise receive a usable
manual editor. Learners with a profile enter review immediately, can optimize
without an automatic rewrite, and can restart research after an explicit dirty
draft confirmation. A terminal research result is optimized locally, falls
back to its raw draft on failure, and is persisted only by the final save.

The course page and settings entry now share the same mounted dialog instance,
not merely the same component implementation. Opening the menu while automatic
onboarding is active keeps the current question, session, draft, and focus.
When a pending automatic gate becomes blocking while the menu dialog is open,
the same instance adopts blocking exit rules without reloading learner data.
Blocking courses remain stopped until durable save or explicit defer;
non-blocking and fail-open behavior, account-generation guards, and the
settings dirty-close contract remain intact. The retired onboarding modal and
its separate focus trap were removed. No migration, browser draft store, or
new provider/runtime dependency was introduced.

Final verification on `markdown-flow-ui` 0.2.10 passed 302 backend tests (one
opt-in MySQL smoke skipped), 128 frontend tests, TypeScript, ESLint, Prettier,
Ruff check/format, three-locale parity and unused-key checks, architecture
(133 baseline, zero new or stale), and diff checks. Real-browser QA covered
1280 x 720, 390 x 844, 320 x 568 French, and 844 x 390 research, optimizing,
review, dirty-confirmation, blocking-dismiss, and fixed-footer states. Evidence
is retained under `/private/tmp/profile-onboarding-unified-visual/`; temporary
harness routes and browser state are not part of the change.

The guided-only compact refinement passed 115 focused frontend tests,
TypeScript, changed-file ESLint and Prettier, three-locale parity and unused-key
checks, architecture validation, and the repository harness. Browser evidence
under `/private/tmp/profile-onboarding-guided-compact-visual/` covers compact
collection, visible processing, save actions, dirty replacement confirmation,
the expanded information disclosure, blocking dismissal, 320 x 568 French,
and short-height landscape. Temporary routes, API mocks, browser state, and
build output were removed after verification.

## Context and Orientation

- The existing editor shell and settings rerun live in
  `src/cook-web/src/components/profile-onboarding/LearnerProfileDialog.tsx`.
- The reusable guided conversation remains in
  `ProfileOnboardingConversation.tsx`; the obsolete separate modal shell has
  been removed.
- Course presentation and runtime blocking live in
  `src/cook-web/src/app/c/[[...id]]/page.tsx`.
- Canonical completion lives in
  `src/api/flaskr/service/profile/onboarding.py` and the learner route.

## Plan of Work

First extend profile-v2 completion with an optional nickname while preserving
strict legacy/v2 field dispatch. Then move the guided conversation into the
learner-profile dialog and add explicit `research`, `optimizing`, and `review`
views. Finally replace the course-owned modal with the unified dialog and
regenerate translations/types before running focused and repository gates.

## Concrete Steps

1. Accept optional string `nickname` only on the v2 completion payload and
   forward presence separately from omission into the existing atomic profile
   save service.
2. Load canonical profile and onboarding status together, choose the initial
   view from canonical-profile presence and guided availability, and preserve
   account-generation guards.
3. Reuse `ProfileOnboardingConversation` inside the dialog. Store its terminal
   draft and session id locally, automatically call the existing optimizer,
   then render the shared profile editor.
4. Make final save dispatch to guided completion when a research session is
   active and to canonical PUT for direct editing. Keep errors and drafts
   editable and single-flight.
5. Update course and admin callers, remove the nested rerun shell from the
   learner dialog, and retain presentation-specific close/defer behavior.
6. Update three locales, generated i18n types, component/API/backend tests, and
   responsive visual evidence.
7. Rename the dialog's internal research phase and completion state to a
   guided-only collection result boundary, while preserving the existing
   runtime and persistence contracts.
8. Replace the entry-semantic `mode` prop with an exit-policy prop so content
   selection continues to depend only on canonical profile state and guided
   availability.
9. Compact the collection and save views using the approved persistent copy
   and footer hierarchy, then update focused caller/component tests.
10. Re-run static, translation, repository, and four-viewport browser gates;
    confirm the diff contains no PR3 UI, storage, analytics, or provider names.

## Validation and Acceptance

- No profile plus guided availability opens research; existing profile opens
  the editor; unavailable guided configuration opens an empty manual editor.
- Research completes into automatic optimization without a database write.
  Optimization failure leaves the research draft saveable and retryable.
- Restarting research happens inside the same dialog. Dirty edits require
  confirmation before replacement.
- Automatic and menu entry points render one dialog mount. Switching entry
  context in place does not reload the profile, recreate the research session,
  or discard a local draft; only account scope or a genuinely new open journey
  resets dialog state.
- Guided final save performs one durable operation for profile, optional
  nickname, v2 state, and session cleanup. Direct edits keep using canonical
  PUT.
- Blocking course runtime remains unmounted through research, optimization,
  and review; successful save or explicit defer releases it. Non-blocking and
  hidden/fail-open behavior remains unchanged.
- Account switching ignores stale load, stream, optimize, and save responses.
- Focused pytest/Jest, TypeScript, ESLint, Prettier, Ruff, translations,
  architecture, repository harness, diff-check, dev-tools, and responsive
  browser QA pass.
- The dialog always shows its persistent purpose statement, never shows a
  progress indicator, and renders "互动收集" beside the save action without
  labeling nickname as optional.
- The focused production diff contains no familiar-AI entry, paste route,
  method chooser, provider list, route-selection event, or browser draft
  storage.

## Idempotence and Recovery

No database migration or browser draft storage is introduced. A failed load,
stream, optimization, or save leaves durable learner state unchanged. Tests
and generators are safe to rerun; account changes invalidate local work.

## Interfaces and Dependencies

- V2 `POST /api/user/profile-onboarding/complete` accepts required
  `learner_profile` and `trigger_source`, optional `session_id`, and optional
  `nickname`. Omission preserves nickname; an empty string clears it.
- Legacy completion payloads and all legacy `sys_*` persistence remain
  unchanged and isolated.
- The official MarkdownFlow/Redis session runtime and the existing learner
  profile optimizer remain the only research and optimization providers.
- No schema migration or new storage dependency is required.

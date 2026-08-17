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

## Decision Log

- `LearnerProfileDialog` is the only dialog shell. Research, optimizing, and
  review are internal views rather than nested dialogs.
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

## Outcomes & Retrospective

Research is now one way to create or replace the draft inside the existing
personalization editor, not a second feature or nested modal. Learners without
a profile enter guided questions when available and otherwise receive a usable
manual editor. Learners with a profile enter review immediately, can optimize
without an automatic rewrite, and can restart research after an explicit dirty
draft confirmation. A terminal research result is optimized locally, falls
back to its raw draft on failure, and is persisted only by the final save.

The course page and settings entry now share the same dialog implementation.
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

## Validation and Acceptance

- No profile plus guided availability opens research; existing profile opens
  the editor; unavailable guided configuration opens an empty manual editor.
- Research completes into automatic optimization without a database write.
  Optimization failure leaves the research draft saveable and retryable.
- Restarting research happens inside the same dialog. Dirty edits require
  confirmation before replacement.
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

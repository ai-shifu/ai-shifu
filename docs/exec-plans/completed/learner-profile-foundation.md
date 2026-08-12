# Learner Profile Foundation

## Purpose / Big Picture

Deliver the first independently deployable layer of the learner-profile work
from source snapshot `331a54f53`. Learners can edit or clear one canonical
profile in settings. When a profile exists, the course prompt and JSON-encoded
learner data are composed once inside a platform-owned responsibility contract
used by teaching, ask, and formal preview. The legacy profile-onboarding
questionnaire and its `sys_*` storage contract remain intact.

## Progress

- [x] 2026-08-10 09:50 CST: Verified this worktree starts at current
  `origin/main` (`96fb6ca36`) and created
  `sunner/learner-profile-foundation`.
- [x] 2026-08-10 10:00 CST: Audited the complete source-snapshot diff and
  identified PR1-owned files and mixed-file hunks.
- [x] 2026-08-10 10:25 CST: Extracted the backend persistence, API,
  compatibility, and prompt-composition layer.
- [x] 2026-08-10 10:40 CST: Extracted the direct settings editor without the
  guided onboarding flow.
- [x] 2026-08-10 11:18 CST: Validated migration structure/head, backend and
  frontend behavior, translations, architecture, repository harness, and
  lefthook.
- [x] 2026-08-10 11:23 CST: Committed and pushed the split, then created ready
  pull request #2301.

## Surprises & Discoveries

- The source snapshot is a squash directly on the current main commit, so its
  migration parent `b8d5f0a2c3e4` is already present on main and the existing
  `c8f1a2d3e4b5` revision can be reused unchanged.
- The source snapshot replaces the legacy onboarding contract with profile-v2.
  PR1 instead needs the canonical profile and fixed profile-v2 state to coexist
  with the legacy GET/complete wire contract.
- The source settings component imports its shared editor from the redesigned
  onboarding modal. PR1 must extract that editor into an independent component
  so no guided conversation or redesigned modal becomes a dependency.
- Formal preview resolves the current logged-in user profile on every request.
  The source snapshot's lightweight browser event is still needed so the
  preview banner refreshes immediately after same-page settings saves or
  clears, with request sequencing to discard stale-account responses.
- Profile writes must notify same-page preview consumers only after the active
  settings instance and account generation accept the response. Transport
  helpers cannot safely emit that event before stale-response checks.
- An older backend may not expose the learner-profile endpoint during a rolling
  deployment. A failed initial profile load therefore leaves the editor
  disabled but is a no-op for the page-wide legacy settings save.

## Decision Log

- Decision: preserve the current legacy `/profile-onboarding` GET and
  `/profile-onboarding/complete` payloads and `sys_*` writes byte-for-byte,
  changing only the GET eligibility gate for canonical profile/profile-v2
  compatibility.
  Rationale: PR1 must deploy without forcing the new onboarding UI or contract.
- Decision: make PUT/DELETE canonical profile writes and fixed profile-v2
  `completed/settings` state writes one unit of work.
  Rationale: clearing the text must remain handled and saving must never leave
  profile and onboarding state out of sync.
- Decision: keep profile data inside the effective course-prompt string and do
  not add profile-specific provider, LLM, or Langfuse parameters.
  Rationale: teaching, ask, and preview already share course-prompt resolution.
- Decision: include the source-snapshot backend migration-workflow guidance as
  a separate maintenance commit.
  Rationale: it is an explicitly requested repository rule, independent from
  runtime behavior.
- Decision: keep fixed profile-v2 state identifiers owned by the canonical
  learner-profile module, and let legacy onboarding depend only on canonical
  eligibility.
  Rationale: PR2 can replace legacy config/parser ownership without creating a
  reverse dependency from canonical persistence.
- Decision: ordinary preview logs record only prompt-presence and profile-tail
  metadata, while the full effective prompt still reaches the model and
  existing tracing path.
  Rationale: a learner profile must not gain another raw local copy in normal
  service logs.

## Outcomes & Retrospective

PR #2301 delivers the canonical profile, direct settings management, legacy
compatibility gate, and shared Teaching/Ask/formal-preview prompt composition
without importing the guided onboarding redesign. Focused verification ended
with 42 backend tests and 32 frontend tests passing, followed by clean Ruff,
type-check, translation, architecture, harness, developer-tool, and lefthook
gates.

Review before publication found several rolling-deploy and async-lifecycle
edges that the source implementation did not fully isolate. The final split
keeps basic-info saves independent, treats an unavailable learner-profile GET
as a no-op for legacy settings, accepts save/clear responses only for a mounted
matching account generation, uses the active interface locale for timestamps,
cleans failed preview database sessions, and excludes profile text from normal
preview logs.

## Context and Orientation

Canonical learner data lives on `user_users` and is exposed through the user
repository aggregate. Learner-profile service behavior belongs under
`src/api/flaskr/service/profile/`; authenticated routes are registered in
`src/api/flaskr/route/user.py`. Effective MarkdownFlow course prompts are
resolved in `src/api/flaskr/service/learn/context_v2.py`. The legacy learner
settings page is
`src/cook-web/src/app/c/[[...id]]/Components/Settings/UserSettings.tsx`, with
transport helpers in `src/cook-web/src/c-api/user.ts` and shared translations
under `src/i18n/`.

## Plan of Work

1. Restore source-owned model, migration, service helper, prompt template, and
   focused tests from `331a54f53`, then crop profile-v2/guided dependencies.
2. Add only the mixed-file repository, legacy compatibility, authenticated
   route, and effective-prompt hunks required by PR1.
3. Extract a standalone `ProfileDraftEditor` and Unicode code-point helper;
   build the settings section around direct GET/PUT/DELETE only.
4. Keep legacy dynamic profile fields visible and add race-safe account-switch,
   load-failure, save, and clear coverage.
5. Restore the migration-workflow rule source and regenerate its mirrored
   instruction files.
6. Run focused checks first, then required repository-wide gates.

## Concrete Steps

- Use `git restore --source=331a54f53 -- <file>` only for files wholly owned by
  PR1.
- Use reviewed patches for `models.py`, `repository.py`, `onboarding.py`,
  `route/user.py`, `context_v2.py`, `UserSettings.tsx`, `c-api/user.ts`, and
  translations.
- Do not run `flask db migrate`; inspect and test the existing migration and
  run Alembic head validation instead.
- Run focused pytest and Jest suites, Ruff on changed Python files,
  TypeScript type-check, ESLint, translation checks, architecture checks,
  repository harness, tool doctor, and lefthook.

## Deployment and Rollback

Deploy in this order: run `FLASK_APP=app.py flask db upgrade` from `src/api/`,
wait for the new backend to be ready on every instance, and only then deploy the
frontend. The frontend may be rolled back first. After any canonical profile is
saved, do not roll the backend back to a binary that does not recognize the
canonical profile and fixed profile-v2 state; such a binary can show the legacy
questionnaire again. This layer intentionally does not write an additional
legacy marker.

## Validation and Acceptance

- Migration `c8f1a2d3e4b5` adds nullable profile text and update time and is the
  single Alembic head following main's `b8d5f0a2c3e4`.
- GET/PUT/DELETE profile routes authenticate, moderate, normalize, save, and
  clear correctly; PUT/DELETE atomically retain fixed profile-v2 handled state.
- Legacy questionnaire payloads, parser, `sys_*` writes, and old course profile
  reads remain compatible; canonical/v2 users do not see the old questionnaire.
- No-profile course prompts are unchanged. When a profile exists, one effective
  prompt preserves the teacher-authored Course Prompt and places the encoded
  profile in its own learner-data block after a responsibility-based composition
  contract; teaching, ask, and formal preview use that same prompt.
- Settings survives load failure, saves and clears explicitly, does not close
  on failed save, ignores stale account responses, and leaves old background
  and style fields visible.
- Same-page saves and clears notify the preview banner, and both banner refresh
  and formal prompt resolution discard or avoid stale profile data.

## Idempotence and Recovery

Source restores are repeatable because every target is pinned to
`331a54f53`. Mixed-file patches are small and reviewable against HEAD. If a
focused extraction fails, restore only that file from HEAD and reapply the
owned hunk; never reset the whole worktree. Database migration validation is
read-only and the migration is not executed against a shared database.

## Interfaces and Dependencies

- Database: `user_users.learner_profile`,
  `user_users.learner_profile_updated_at`, existing
  `user_onboarding_states` fixed row (`profile_onboarding`, `profile-v2`).
- Backend API: `GET|PUT|DELETE /api/user/learner-profile`; legacy
  `GET|POST /api/user/profile-onboarding[/complete]` remains stable.
- Backend service: canonical serialize/validate/apply/save/clear helpers and
  `build_course_prompt(course_prompt, learner=...)`.
- Frontend: `LearnerProfile`, GET/PUT/DELETE client helpers,
  `ProfileDraftEditor`, and `LearnerProfileSettingsSection.saveIfDirty()`.

# Learner Profile Dialog Redesign

## Purpose / Big Picture

Replace the learner-facing full-page personalization settings and legacy
three-field onboarding experience with one responsive learner-profile dialog.
Learners stay in the active lesson, write one natural-language introduction,
and may separately provide a low-emphasis nickname for the AI teacher to use.
They may optionally ask AI to organize the introduction into a durable learner
brief that downstream course delivery can use for more relevant examples,
terminology, emphasis, and language. Optimization is an explicit, reversible
draft-only action: it never persists automatically and never participates in
nickname handling.
The introduction and nickname are independent inputs: the service never parses
or uses an LLM to extract a nickname from the introduction. The explicit
nickname is stored directly in `user_users.nickname` in the same transaction as
the canonical profile mutation. The dialog does not expose the legacy
`sys_user_nickname`, `sys_user_background`, or `sys_user_style` variables.
Existing courses keep their historical variables and their pre-PR
`sys_user_nickname` write, read, and runtime-substitution behavior unchanged.

The selected visual truth began with the revised option-three mock at
`docs/assets/learner-profile-dialog-approved-reference.png`
and was refined by direct user feedback: the active dialog has only its
secondary action and primary save action, with no separate clear or overflow
control. Deliberately emptying a loaded draft and choosing save performs the
canonical empty-profile write through PUT and keeps the independent nickname.

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
- [x] 2026-08-13: Replace the proposed nickname-recognition design with one
      optional explicit nickname input. Persist it directly to
      `user_users.nickname`; never parse or use an LLM to infer a nickname from
      the introduction, and do not change the legacy `sys_user_nickname`
      mechanism. The separate optional optimizer may rewrite only the
      introduction after an explicit learner action.
- [x] 2026-08-12: Refine the selected visual target from direct user feedback
      so the active dialog exposes no separate clear or overflow control.
- [x] 2026-08-13: Tighten desktop header/body/footer spacing and the editor
      height after adding the nickname field. At a real `1280 x 720` in-app
      course viewport, the open dialog body measured `490px` for both client and
      scroll height with `scrollTop = 0`; the nickname, introduction, guide,
      reassurance, and actions all fit without initial scrolling. Shorter
      viewports and longer drafts retain internal scrolling.
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
- [x] 2026-08-13: Let learners deliberately empty a loaded introduction and
      save it through the normal PUT contract. Keep DELETE as a compatibility
      interface that clears only the introduction and preserves the independent
      nickname. Reuse the existing profile-v2 handled state so legacy values
      seed only never-handled profiles and do not reappear after an explicit
      clear; no new persistence is required.
- [x] 2026-08-13: Rename the settings title to invite learners to introduce
      themselves, clarify the Chinese long-term field label, and remove the
      header-only max-width so the title and description share the form's left
      edge. A same-size 684 x 781 browser comparison passes in `design-qa.md`.
- [x] 2026-08-13: Complete pre-commit verification for the explicit-nickname
      contract: 218 focused backend tests passed with 4 skipped, 56 focused
      frontend tests passed, TypeScript and focused ESLint passed, repository-
      pinned Ruff 0.15.13 and Prettier passed, translation and unused-key checks
      passed, architecture and repository harness checks passed, the migration
      graph remained single-head, and the real desktop browser check passed.
- [x] 2026-08-14: Make the introduction editor content-independent in height
      while adapting it to the available viewport, and add an optional,
      reversible AI optimization action with no learner business-data writes.
      Verified the 115px desktop editor remains unchanged while its scroll
      height grows from 113px to 480px, the 390 x 844 mobile editor resolves to
      135px, and the compact mobile optimizer action retains a 44px target.
- [x] 2026-08-14: Define optimization from the real Teaching, Ask, and Preview
      consumption contract instead of treating it as generic proofreading or a
      style expander. It organizes every explicitly stated background fact,
      prior experience, knowledge level, current interest, goal, concern,
      difficulty, practical constraint, familiar context, and language
      preference into concise learner context that can support relevant
      examples, terminology, emphasis, and expression. A named language-style
      reference remains one narrow interpretive expansion; it never authorizes
      inference of personal facts or control over course content, pedagogy,
      sequence, interactions, or format. Natural mixed-language wording in the
      learner's own input may remain when the optimized profile is still clear.
- [x] 2026-08-14: Shift optimization from compression to meaning-preserving
      elaboration. The optimizer now retains every distinct stated detail,
      expands terse or indirect meaning only when the added detail follows from
      the learner's words, and prefers downstream usefulness over brevity. The
      runtime composition contract actively applies relevant profile details
      to examples, terminology, emphasis, and language style instead of merely
      acknowledging or summarizing them; Course Prompt ownership is unchanged.
- [x] 2026-08-14: Stop accepting no-op optimization responses. The service now
      requires material detail beyond the source, asks the model once more with
      a concise correction when the first response is unchanged or
      insufficient, and returns the existing optimization failure only if the
      second result still fails. Labels remain a model instruction rather than
      a hard acceptance gate because useful elaboration matters more than its
      exact layout. Both attempts remain review-only: they do not update learner
      business data or emit profile-change events.
- [x] 2026-08-14: Treat a copied source paragraph followed by real expansion as
      a recoverable model artifact: remove the exact source prefix and return
      only the new detailed profile. The prompt also forbids copying the source
      and limits non-imitation language to inputs that actually name a style,
      avoiding a fabricated preference in ordinary profiles.
- [x] 2026-08-14: Restore the proven named-style boundary after real dev output
      positively framed a person as an imitation target and invented visual
      performance details. Short inputs now require one bounded labeled entry;
      a named reference may appear only after the final non-imitation boundary,
      and expansion is limited to observable language qualities.
- [x] 2026-08-14: Replace the optimizer's long rule manual with a compact
      transformation contract after a real learner paragraph was returned
      nearly unchanged. The new contract always rewrites prose into short,
      labeled, standalone lines, forbids unchanged paragraph output, and keeps
      only the minimum safety, course-ownership, and JSON boundaries.
      Real dev verification converted the reported paragraph into five labeled
      learner-context lines. Mixed-language terms are accepted rather than
      translated mechanically. A named-style-only regression then added two
      compact safeguards: omit every unstated category rather than reporting it
      as missing, and express named references as concrete traits plus an
      explicit non-imitation boundary, never as an instruction to imitate.
      Further browser runs exposed over-classification and an omitted boundary,
      so the final prompt is limited to six rules: use the fewest categories,
      make style-only input exactly one language-style line, and end that same
      line with a named non-imitation boundary while prohibiting positive
      instructions to emulate or borrow from the reference.
- [ ] 2026-08-13: Rebase onto the latest `origin/main`, repeat the focused
      gates, update the ready PR and deployment notes, and read back CI and
      active review threads.

## Surprises & Discoveries

- The current “个性化设置” is not a dialog: `ChatUi` hides the lesson and
  absolutely positions `UserSettings` across the full learning canvas.
- The page has two saves. The outer save writes avatar, birth, sex, nickname,
  every dynamic field, and legacy system variables before the canonical
  profile section performs its own save.
- First-course onboarding remains a separate legacy MarkdownFlow questionnaire
  that writes the same three `sys_*` values. Removing only the settings fields
  would leave the obsolete data-entry path active.
- Nickname has two distinct compatibility surfaces. The redesigned canonical
  endpoint may write the explicit value directly to `user_users.nickname`, but
  existing `sys_user_nickname` VariableValue writers, readers, and runtime
  substitution must behave exactly as they did before this PR. The new flow
  must not add canonical-profile guards to those old paths. The unchanged
  runtime precedence already projects `user_users.nickname` as the effective
  legacy variable value, so a newly explicit account nickname is naturally
  visible to old courses without rewriting their VariableValue rows.
- The canonical introduction is free-form multilingual prose. Treating an
  inferred name as account data would be surprising and nondeterministic, so
  the explicit nickname field is the only new source for nickname changes.
- Eligibility and profile requests can outlive account or dialog-mode changes.
  Runtime readiness therefore has to be keyed by account, not held as a single
  boolean, and user-info refresh must reject stale token or user-ID results.
- A canonical clear remains a handled profile mutation for compatibility. The
  redesigned dialog offers no separate clear control; deleting all loaded
  introduction text and pressing save invokes PUT with an empty profile. The
  DELETE endpoint remains stable for compatibility consumers, clears only the
  profile, and never clears the independent nickname.
- MarkdownFlow 0.3.1 accepts one `document_prompt` string and places it in its
  existing system-message assembly, so the three-block envelope requires no
  provider or library API change. Its tags express composition semantics rather
  than a separate transport-level security boundary.
- The shared textarea auto-resizes only when `minRows` or `maxRows` is passed.
  The active dialog can therefore use a viewport-relative CSS height and
  internal scrolling without changing the legacy settings editor or the shared
  textarea's default behavior.
- The shared LLM path records usage and Langfuse observations. Profile
  optimization must opt into sensitive-content logging so ordinary logs and
  local usage metadata contain only counts and status, while the existing
  Langfuse policy retains the complete model input and output.
- Temporary and registered users can both reach the optimizer, so a disabled
  frontend button is not cost or capacity admission. The backend must enforce
  per-user and trusted network-scope request and in-flight limits before
  moderation and model execution without trusting client-supplied forwarding
  headers.

## Decision Log

- Decision: use one shared `LearnerProfileDialog` for menu editing and
  first-time presentation.
  Rationale: one component gives the same load, save, moderation,
  account-switch, accessibility, and responsive behavior at every entry.
- Decision: show only the context-appropriate secondary action and primary
  save action in the redesigned dialog; do not expose clear or overflow UI.
  Rationale: direct user feedback preferred a simpler active flow. An
  intentionally empty introduction uses the normal PUT save, while DELETE and
  the legacy settings-section clear behavior stay available as compatibility
  contracts.
- Decision: show a separate, optional, low-emphasis nickname input alongside
  the learner-profile introduction.
  Rationale: nickname is explicit account data that learners should be able to
  understand and correct. The service must never infer it from the introduction
  or make save depend on an additional LLM call.
- Decision: keep the nickname and personal introduction independent.
  Rationale: an empty introduction must not clear a nickname, and changing or
  clearing a nickname must not rewrite the introduction.
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
- Decision: extend the canonical PUT with an optional `nickname` field. A
  missing field preserves the current nickname; an explicit empty string clears
  it; any supplied value is bounded and moderated. The profile text itself may
  also be empty.
  Rationale: these semantics support independent edits and rolling clients
  without introducing a second endpoint or an ambiguous inferred value.
- Decision: apply each provided canonical field and the profile-v2 handled
  state inside the existing unit of work.
  Rationale: moderation or database failure must not leave a half-saved profile
  and nickname update.
- Decision: stop new UI writes to the three legacy variables, but do not delete,
  guard, or otherwise change their definitions, rows, endpoints, parser,
  writers, readers, or runtime resolution. In particular,
  `sys_user_nickname` retains its pre-PR behavior.
  Rationale: old courses and rolling deployments still depend on those exact
  contracts. The new explicit nickname write to `user_users.nickname` is an
  additional canonical path, not a replacement for legacy behavior.
- Decision: when the canonical profile is empty and no fixed profile-v2 state
  exists, use only the latest global legacy background/style values to compose
  a localized, editable introduction draft without auto-saving it. Do not put
  `sys_user_nickname` into that prose. The separate nickname input first reads a
  safe account nickname and may fall back to an existing global legacy nickname;
  with a new backend, the first canonical save migrates that displayed fallback
  into `user_users.nickname` without altering its legacy row. Once the existing
  profile-v2 state records an explicit clear, keep the editor empty instead of
  restoring those legacy background/style values.
  Rationale: existing learners start from information they already provided,
  while an explicit empty save remains durable without adding new persistence;
  canonical profiles remain authoritative and course-scoped legacy data never
  leaks into the new cross-course profile.
- Decision: when a canonical learner context is available, serialize the
  effective `document_prompt` as a platform-owned composition contract followed
  by an unmodified teacher-authored Course Prompt block and a JSON-encoded
  learner-owned data block. That learner data may contain the introduction, the
  explicit nickname, or both.
  Rationale: Course Prompts and learner profiles are both open inputs whose
  apparent conflicts cannot be eliminated in advance. The contract deliberately
  leaves course design and presentation choices to the Course Prompt and limits
  itself to treating the profile as untrusted data: useful explicit facts and
  preferences may personalize execution, while embedded directives, role or
  priority claims, tool or data requests, and disclosure attempts remain inert.
  This stays compatible with MarkdownFlow's single-string `document_prompt` API.
  The explicit nickname is also untrusted learner data and never gains
  instruction authority. With neither an introduction nor an explicit
  nickname, the original Course Prompt remains byte-for-byte unchanged.
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
- Decision: make profile optimization an optional button labeled “帮我优化”
  rather than a mandatory save step or a background rewrite.
  Rationale: learners retain control over personal facts, LLM latency or
  failure never blocks saving, and one in-editor result plus a single undo
  action keeps the desktop and mobile flow compact.
- Decision: optimize for the learner profile's actual downstream use, not only
  for prose quality or language-style expansion.
  Rationale: Teaching, Ask, and Preview all receive the same learner data and
  may use relevant stated facts and preferences for examples, terminology,
  emphasis, and language style. The optimizer therefore makes background,
  experience, current concerns, goals, difficulties, and constraints easy to
  consume while leaving subject matter, pedagogy, sequence, interactions, and
  output format to the human teacher's Course Prompt and the current task.
- Decision: express the optimizer contract as one mandatory transformation,
  not a catalog of downstream mechanisms and overlapping exceptions.
  Rationale: the longer prompt made copying an already-readable paragraph the
  model's safest response. The compact contract now requires one localized
  category per standalone line and explicitly disallows returning the source
  paragraph unchanged, while the runtime composition prompt continues to own
  the detailed Course Prompt and learner-data relationship.
- Decision: keep optimization draft-only and business-state-free.
  Rationale: the optimize endpoint may create the existing redacted moderation,
  usage, and Langfuse observability records, but it must not update the
  canonical profile, nickname, timestamps, profile-v2 handled state, or client
  profile-changed events. Only the existing PUT persists a learner-confirmed
  draft.
- Decision: keep optimization observable but sensitive.
  Rationale: the endpoint omits request and response bodies from the ordinary
  HTTP logger, and the LLM call opts into metadata-only transport and local
  usage records. Moderation audit, bill-usage token metadata, and Langfuse
  traces remain the allowed observability writes; Langfuse intentionally keeps
  the full model input and output. Failed child generations and their root
  trace are finalized instead of being left open.
- Decision: bound optimizer cost and concurrency on the server.
  Rationale: temporary and registered users can both reach the endpoint.
  Per-user and trusted network-scope rate limits plus in-flight caps run before
  moderation and LLM work; frontend state is only a usability guard, not an
  admission boundary. Only a direct peer listed in
  `TRUSTED_REVERSE_PROXY_ADDRESSES` may supply the proxy-overwritten
  `X-Real-IP`; client-controlled `X-Forwarded-For` is ignored, and IPv6 scopes
  are grouped by `/64`. Configured Redis fails closed, while an environment
  with no Redis uses a process-local fallback intended for local development.
- Decision: make the editor height stable for a given viewport, not a single
  fixed pixel value.
  Rationale: `clamp(7rem, 16dvh, 11rem)` uses more room when available while
  preventing entered content from shifting the dialog; overflow stays inside
  the editor.

## Outcomes & Retrospective

The learner stays inside the lesson while one shared responsive dialog collects
a natural introduction and, separately, an optional nickname. The dialog does
not expose the three legacy variables and never infers nickname data from prose.
When the canonical introduction is empty, eligible existing global legacy
background/style values seed a localized draft that the learner can review,
edit, and explicitly save. A moderated PUT atomically applies the profile and
any explicitly supplied nickname while recording the existing profile-v2
handled state. Saving an empty introduction does not clear the nickname; the
compatibility DELETE endpoint also preserves it. Historical `sys_*` rows and
all pre-PR `sys_user_nickname` behavior remain intact.

The explicit-nickname implementation now passes its pre-commit behavior and
static gates: 218 backend tests passed with 4 skipped, 56 frontend tests passed,
and the focused type, lint, formatting, translation, architecture, repository
harness, migration-graph, and desktop-browser checks all passed. The final
post-rebase repetition and PR/CI readback remain before this plan can move to
the completed archive; counts from the superseded inferred-nickname design are
not treated as evidence for this contract.

The optional optimizer is implemented without a schema change or learner
business-state mutation. Its final focused gates passed with 112 backend tests
and 1 skip, 166 related Learner Profile/Teaching/Ask tests and 4 skips, and 60
frontend tests plus 17 onboarding-gate tests. TypeScript, focused ESLint,
repository-pinned Ruff,
Prettier, translation and unused-key checks, architecture boundaries,
repository harness, developer-tool checks, and `git diff --check` also passed.
Browser QA at 1280 x 720, 1487 x 1058, and 390 x 844 confirmed stable editor
height, internal scrolling, the compact failure fallback, close/discard, a
visible sticky footer, and a 44px mobile optimizer target. The shared
development backend did not yet expose the new endpoint, so browser success
and undo remain covered by focused component tests until deployment.

The optimized result is a reusable learner brief rather than a generated
lesson plan. It keeps only learner-provided context and preferences, exposes
them clearly enough for later course delivery to select relevant connections,
terminology, and emphasis, and treats language-style expansion as one optional
dimension rather than the entire optimization goal.

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
5. Add a low-emphasis optional nickname input. Extend canonical GET/PUT with
   direct `user_users.nickname` semantics, never inspect the introduction for a
   name, and refresh frontend user info after accepted nickname saves. Preserve
   every pre-PR `sys_user_nickname` writer/read/runtime path unchanged.
6. Add focused tests for entries, responsive/accessible behavior, load/save/
   error/dismiss/account-switch behavior, independent nickname/profile edits
   and atomicity, plus compatibility coverage for DELETE preserving nickname
   and for the unchanged legacy nickname paths.
7. Capture desktop and mobile implementations, compare them with the selected
   mock, fix P0-P2 differences, and record `design-qa.md` with a passing result.
8. Add a draft-only learner-profile optimizer that organizes the whole
   introduction for its downstream Teaching, Ask, and Preview use, returns the
   suggestion into the same editor, supports one-step undo, and leaves direct
   save available when optimization is skipped or fails.

## Concrete Steps

- Reuse `Dialog`, `Button`, `ProfileDraftEditor`, `getLearnerProfile`,
  `updateLearnerProfile`, `refreshUserInfo`, and `learner-profile-changed`; do
  not add another request client. Preserve `clearLearnerProfile` for existing
  compatibility consumers, but do not expose it in the redesigned dialog.
- Keep the dialog header/footer visible and the body scrollable; use a centered
  approximately 720-pixel desktop surface and a near-full-height mobile sheet
  with at least 44-pixel actions.
- Give the active introduction editor a content-independent
  `clamp(7rem, 16dvh, 11rem)` height, disable manual resize, and keep overflow
  keyboard-, pointer-, and touch-scrollable inside the field. Do not change the
  legacy settings editor's auto-resize behavior.
- Place “帮我优化” and the character count on one compact row. Replace the
  current draft in the same editor only after a successful, current-account
  response; keep one in-memory undo value, never auto-save, and keep close and
  cancel available while optimization is pending.
- Call the shared LLM path with `DEFAULT_LLM_MODEL`, JSON response mode,
  temperature `0.1`, a 15-second provider timeout, and at most 1200 output
  tokens. Accept only an exact one-key JSON object containing a non-empty
  optimized string no longer than 1000 characters.
- Distinguish an explicit moderation rejection from a technical optimization
  failure. Rejection asks the learner to revise before retrying; provider,
  timeout, malformed-response, unsupported-old-backend, or other technical
  failures preserve the current draft and ordinary save path.
- Omit optimizer request/response bodies and sensitive LLM input/output from
  ordinary logs and local usage `extra`, while retaining length, status, model,
  token metadata, and the established full-content Langfuse trace. Close child
  generation observations on both success and failure.
- Apply server-side per-user and trusted network-scope rate and in-flight
  admission before moderation and LLM execution. Client-supplied forwarding
  headers cannot select a new quota bucket.
- Provide three optional writing-prompt buttons that only focus/seed the same
  textarea. The complete placeholder must cover durable background, existing
  experience, current cross-topic concerns, practical constraints, ambitions,
  and language-style preferences without assuming a specific subject or
  prescribing a teaching method. Nickname belongs only in its separate input.
- Mention language-style preferences outside the placeholder as well: the
  dialog description, third writing prompt, and writing guide must make this
  capability discoverable while leaving teaching decisions to the course
  teacher.
- Do not add or regenerate a database migration. Nickname already belongs to
  `user_users`.
- Keep the canonical learner-profile `nickname` request member optional. Omit
  it for an introduction-only update, send an explicit empty string to clear
  it, and never couple it to profile-clear or DELETE behavior.
- Preserve legacy endpoint payloads and historical rows; focused diff checks
  must prove no accidental deletion, guard, or rewrite of pre-PR
  `sys_user_nickname` behavior. Its existing runtime precedence may expose the
  new `user_users.nickname` value, but the canonical API must never create,
  delete, or rewrite a legacy nickname row.

## Validation and Acceptance

- Opening “学习者画像” closes the account menu, leaves the lesson visible, and
  opens a focus-managed dialog on desktop and a usable sheet on mobile.
- The dialog contains one learner-profile textarea, a separate optional
  nickname input, complete cross-course example guidance,
  a context-appropriate secondary action and primary save action, inline error
  and retry states, and no separate clear/overflow or editable legacy
  background/style controls.
- Saving writes an empty or non-empty profile, profile-v2 handled state, and any
  explicitly supplied nickname atomically. Omitting `nickname` preserves it;
  an explicit empty value clears it. No save path parses or sends the
  introduction to an LLM for nickname inference.
- New learner flows do not call legacy profile-write endpoints or create new
  `sys_*` rows. Existing historical rows, old backend wire contracts, old
  course variable resolution, Teaching, Ask, and preview behavior remain
  covered.
- The modern DELETE endpoint and the legacy `LearnerProfileSettingsSection`
  clear behavior remain stable compatibility interfaces. DELETE clears the
  profile and marks it handled while preserving `user_users.nickname`. The
  active dialog saves an empty introduction through PUT and does not invoke
  DELETE or expose a separate clear control.
- A course with learner context may receive the explicit nickname as bounded,
  JSON-encoded, untrusted learner data. It has lower priority than the human
  teacher's Course Prompt. If both profile and nickname are empty, the Course
  Prompt remains unchanged.
- Direct menu editing and first-time presentation share account-switch and
  late-response guards. Load failure is recoverable and never blocks the
  lesson.
- Optimization accepts only a non-empty in-limit draft, does not touch the
  nickname, and never emits a profile-changed event. Success remains editable
  and requires the ordinary save button; failure or an old-backend 404 leaves
  the original draft and save action available. Late responses after close,
  unmount, or account change are ignored.
- Error `1022` represents an explicit moderation rejection and asks the learner
  to revise. Error `1021` represents provider, timeout, malformed-response, or
  other optimization failure and preserves direct save. Admission rejection
  is distinct and never enters moderation or the LLM.
- The optimization provider receives JSON-wrapped untrusted input and returns
  one bounded JSON string. It may reorganize only stated background,
  experience, knowledge level, current interests, goals, concerns,
  difficulties, constraints, familiar contexts, and language-style
  preferences. The result should make relevant examples, terminology,
  emphasis, and expression easier for downstream course delivery to adapt. A
  named style may be translated into high-level, observable expression
  requirements, but the optimizer must not infer learner facts or proficiency,
  mandate examples, issue advice, imitate a named person, prescribe pedagogy,
  pace, sequence, interactions, or output format, or weaken the existing
  runtime learner-data boundary. Natural mixed-language wording may remain.
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
  unit-of-work helpers. GET returns the canonical explicit nickname. PUT accepts
  an optional `nickname`: omission preserves it and an explicit empty string
  clears it; `learner_profile` may be empty. DELETE remains a compatibility
  interface that clears only the profile and preserves nickname. The old
  `sys_user_nickname` VariableValue API and runtime contract are unchanged.
- Backend addition: authenticated
  `POST /api/user/learner-profile/optimize` accepts only
  `{ "learner_profile": string }` and returns only
  `{ "optimized_learner_profile": string }` inside the shared response
  envelope. It performs no learner business-state writes and has no schema
  dependency. It uses `DEFAULT_LLM_MODEL` with bounded JSON generation,
  distinct rejection/technical/admission errors, sensitive-content logging,
  and server-side request/in-flight admission.
- Frontend: shared `LearnerProfileDialog`, modern learner-profile API,
  `useUserStore.refreshUserInfo`, `learner-profile-changed`, account menu and
  course onboarding gate. The dialog uses PUT for empty-profile saves and sends
  `nickname` only when the learner changed that independent input or when a new
  backend explicitly offers a displayed legacy nickname for one-time migration.
- Visual target: `docs/assets/learner-profile-dialog-approved-reference.png`,
  with the direct user-feedback refinement that removes clear/overflow UI;
  implementation is verified at desktop and mobile viewports before handoff.

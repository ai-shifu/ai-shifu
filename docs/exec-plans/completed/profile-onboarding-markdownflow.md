# Full MarkdownFlow Profile Onboarding and Canonical Learner Profile

## Purpose / Big Picture

Replace the current regex-driven profile questionnaire with a real, course-neutral
MarkdownFlow conversation and add a second path for importing a profile from a
personal AI agent. Both paths produce one canonical user-owned learner profile.
The existing course-prompt resolvers append that profile as explicitly
lower-priority background data. Teaching, Ask, preview, and external providers
continue to consume the course prompt exactly as they did before; no downstream
LLM path receives a learner-profile-specific parameter. Learners can inspect,
replace, clear, or voluntarily regenerate the profile without MarkdownFlow
configuration edits ever forcing them through onboarding again.

The visible outcome is a single onboarding entry question: whether the learner
already has a familiar AI agent. A yes answer opens a copy-and-paste flow; a no
answer starts the official MarkdownFlow runtime. Existing legacy completed and
skipped users receive the new experience once when the feature is enabled, with
no cohort rollout.

## Progress

- [x] 2026-08-03 06:43 CST: Synced local `main` to `origin/main` and created
  `sunner/profile-onboarding-markdownflow`.
- [x] 2026-08-03 06:43 CST: Revalidated the current profile onboarding,
  MarkdownFlow preview runtime, prompt assembly, settings, and state contracts.
- [x] 2026-08-03 07:03 CST: Implemented canonical user learner-profile
  persistence, migration, 1000-code-point validation, and atomic fixed-v2 state;
  21 focused repository/service tests pass.
- [x] 2026-08-03 07:04 CST: Replaced operator config variable allowlisting with
  official runtime validation, a config revision with no eligibility semantics,
  and a platform-owned five-area summary prompt whose result is saved as plain
  text.
- [x] 2026-08-03 08:05 CST: Extracted a course-neutral transient MarkdownFlow
  runtime with snapshotted Redis sessions, owner/purpose fencing, non-billable
  usage, and no course-state writes.
- [x] 2026-08-03 08:12 CST: Replaced learner and operator regex flows with the
  official MarkdownFlow parser/runtime and `markdown-flow-ui`; deleted the local
  syntax parser and its tests.
- [x] 2026-08-03 08:18 CST: Added the familiar-agent paste route, guided route,
  editable review, settings replace/clear/rerun controls, mobile full-screen UI,
  accessibility status, privacy notice, i18n parity, and content-free metrics.
- [x] 2026-08-03 08:24 CST: Made the canonical profile the final section of the
  effective course prompt returned by the existing runtime and formal-preview
  resolvers, with an explicit lower-priority, untrusted-data contract;
  onboarding preview remains exempt.
- [x] 2026-08-03 08:33 CST: Added per-user paste-draft isolation and
  request-identity replay for ambiguous SSE completion.
- [x] 2026-08-03 14:55 CST: Removed learner-profile-specific observability
  redaction so ordinary course-prompt logging, metering, and Langfuse behavior is
  unchanged; moderation audit copies and transient-onboarding local logs remain
  redacted by their existing independent policies.
- [x] 2026-08-03 08:48 CST: Completed focused backend/frontend validation,
  translation, formatting, type, lint, and architecture checks. Browser E2E and
  a live MySQL upgrade remain environment-limited as documented below.
- [x] 2026-08-03 19:29 CST: Closed the final review gaps: the profile column stays
  nullable for schema compatibility, transient sessions fail closed without
  shared Redis, stream consumers require an explicit terminal event, and profile
  changes refresh preview/settings state.
- [x] 2026-08-03 19:50 CST: Aligned all frontend length checks with the trimmed
  canonical profile sent to the backend.
- [x] 2026-08-05 CST: Centralized the two built-in backend model prompts, made the
  generated profile explicitly plain text, and removed all learner-profile
  read/write/deletion coupling to deprecated `sys_user_background` and
  `sys_user_style` values while preserving those rows for old courses.

## Surprises & Discoveries

- The current onboarding `version` is metadata only: eligibility checks for any
  legacy sentinel row and never compares its version.
- The normal learner MarkdownFlow runner cannot be reused directly because it
  owns course progress, generated blocks, payment gates, and teacher billing.
- The preview runner already contains the useful official MarkdownFlow and
  element-SSE core, but its public API is creator/course-specific.
- A freely editable single text profile cannot be structurally guaranteed to
  contain five headings without recreating a parser. The five areas therefore
  belong to the platform-owned generation contract, while persistence validates
  only type, non-empty content, length, and safety.
- Configuration edits must not invalidate active sessions. Each session owns a
  complete configuration snapshot, and edits apply only to future sessions.
- Preview billing scenes still default to billable usage and preview providers
  log full model output. The transient profile runtime must therefore use an
  explicit `billable=0` usage context, a non-preview scene, and redacted logs;
  reusing the preview label alone is not safe.
- Ask formats the course prompt after retrieving it. Because the profile is now
  already part of that template, its JSON representation must encode braces as
  well as XML-like delimiters so user-authored text cannot become an Ask/course
  template variable.
- Alembic cannot safely give a MySQL `TEXT` column a default, and making the new
  column non-null in the same rollout would break old application writers that
  omit it. The migration therefore keeps the column nullable while the model and
  repository normalize missing values to an empty profile.
- Browser session storage must be keyed by the current user and reconciled even
  while the modal is closed. A global draft key can leak pasted profile text when
  a second account uses the same browser session.
- The new endpoint contract must not imply that `learner_profile` is a variable
  map. Completion accepts one text value, and the fixed five-area shape belongs
  only to the generation prompt rather than to the persistence or response
  schema.
- Deprecated global background/style values are still resolved by old courses.
  Completing, editing, or clearing the new learner profile must therefore neither
  delete those rows nor change the generic legacy variable read/write paths.
- Reusing the existing moderation persistence helper would duplicate the full
  profile in the risk audit table. The provider still receives the full content,
  but local audit rows retain only a redacted marker, SHA-256 linkage, length,
  and allowlisted verdict fields.
- Losing the terminal SSE event after the server has committed a cursor creates
  an ambiguous completion. Each run now carries a stable request ID and expected
  block index; the server caches the complete response and replays an identical
  request without advancing or calling the model again.
- External Ask providers retain their prior course-prompt behavior. Dify already
  consumes the course-prompt system message and therefore sees the fused prompt;
  Coze workflows and retrieval-only Volc/GetBiji requests continue to receive
  only the inputs they consumed before this feature.
- The Playwright harness could not start the full app in this workspace: after
  resolving the locally available browser binary, Next.js exhausted the process
  file-watch limit with `EMFILE`. This is an environment limitation, not a passing
  browser assertion. The live MySQL migration test is also skipped without its
  opt-in database environment.

## Decision Log

- Store the profile on the canonical user entity, not in `var_variable_values`.
- The canonical profile covers: preferred form of address, professional
  background and identity experience, preferred expression style, preferred
  slide style, and recent interests.
- The external-agent path stores the learner-confirmed text without a second AI
  rewrite.
- Operator-authored MarkdownFlow owns the research conversation; a locked
  platform MarkdownFlow summary block owns the five-area final draft.
- Use a fixed `profile-v2` onboarding state forever. Config revisions never
  reset completed or skipped state.
- Roll out to all eligible users at once when enabled; do not add cohort logic.
- Legacy handled users see a non-blocking one-time upgrade prompt; users without
  any handled state retain the blocking pre-course gate with an explicit skip.
- Page refresh starts a new guided conversation. Paste-form draft text is kept
  in browser session storage so switching to an external AI app does not lose it.
- Append the profile exactly once at the end of the effective course prompt and
  state that every preceding instruction has higher priority. Downstream LLM and
  provider code must not inspect, append, redact, or separately transport it.
- Formal course preview uses the current logged-in user's profile and shows that
  fact in the preview UI. Onboarding-config preview does not inject an existing
  profile.
- Treat saved profile text as untrusted learner data. Send it through content
  safety, keep local moderation audit copies redacted, JSON-quote and delimiter-
  escape it inside the prompt boundary, and state that it cannot override
  preceding instructions. Ordinary course-prompt logging, metering, and Langfuse
  behavior remains unchanged.
- Keep the collection kill switch scoped to new collection: disabling onboarding
  suppresses new prompts but does not remove an existing profile or stop it from
  personalizing learning.
- Expose only the versioned `profile-v2` completion contract. It accepts one
  `learner_profile` string or an explicit skip and never accepts the retired
  questionnaire's `variables` payload.
- Treat deprecated global background/style rows as historical course data. The
  new profile flow neither reads, converts, writes, deletes, nor fences them;
  generic legacy course variable handling remains unchanged.
- Persist only redacted moderation audit metadata locally even though content
  safety must inspect the full candidate profile.
- Let normal observability record the same effective course prompt and resulting
  output that the model receives; do not add learner-profile-specific redaction
  or trace overrides.
- Make SSE retries idempotent with `(request_id, expected_block_index, input)`.
  Replaying an identical request returns its cached event sequence; reusing an ID
  with different input or submitting a stale cursor is rejected.

## Outcomes & Retrospective

The implementation now has one canonical, user-owned learner profile and two
collection paths behind the same confirmation editor. The guided path is parsed,
executed, and rendered entirely through official MarkdownFlow capabilities; the
deleted `profileOnboardingFlow.ts` parser is no longer part of the contract. The
external-agent prompt is limited to the five approved areas. Config changes only
affect new sessions and never reset fixed profile-v2 completion state.

The normal runtime course-prompt getter and formal-preview course-prompt resolver
share one composer. It JSON-quotes and delimiter-escapes the profile, marks it as
untrusted background data, and explicitly gives every preceding course
instruction higher priority. Teaching and Ask inherit the result through their
existing getter. Providers inherit it only where they already consumed the course
prompt. Formal preview uses the current learner's profile and discloses that fact;
configuration preview does not. Existing saved profiles remain active when the
collection kill switch is disabled.

The transient runtime is isolated from course progress, generated blocks, orders,
and teacher-billable usage. Redis sessions snapshot the validated document and
model settings, expire after 30 minutes, enforce owner and purpose authorization,
and support exact event replay after an ambiguous network failure.
Transient onboarding keeps its independent non-billable, locally redacted LLM
runtime. Saved learner profiles use ordinary course-prompt observability, while
moderation audit copies remain content-free.

Verification completed on the final focused surface:

- Backend coverage includes migration structure, canonical profile/state
  services, transient runtime and replay, prompt placement, Ask/provider paths,
  content-safety audit, and preservation of legacy course variable behavior.
- Frontend coverage includes learner/admin API contracts, both onboarding routes,
  retry identity, settings, preview disclosure, account isolation, and hiding of
  deprecated profile fields.
- `npm run type-check`, `npm run lint`, targeted Prettier, translation parity and
  usage checks, `git diff --check`, and architecture-boundary validation passed.
  Lint reports only the repository's existing warnings.
- The all-files Lefthook run passed its architecture, harness, translation,
  JSON/YAML, frontend formatting/lint, and hygiene commands. Its transaction
  ratchet initially caught two new direct commits; both services now use the
  shared Unit of Work and the ratchet passes at 156 grandfathered sites. The
  aggregate hook still cannot finish cleanly because Ruff reports the repository's
  existing file-wide violations in touched legacy modules, while `stage_fixed`
  cannot write `.git/index.lock` in this workspace. Full Ruff passes on every new
  Python module and test added by this plan; the hook's unrelated all-file
  auto-fixes were reverted.
- The opt-in live MySQL upgrade and full Playwright browser journey were not
  validated in this environment. The migration has focused structure coverage;
  browser launch was blocked by Next.js `EMFILE` file-watch exhaustion. These are
  the remaining verification limitations, not known product defects. Mobile,
  visual, and accessibility behavior therefore has source and Jest coverage but
  not a completed real-browser pass in this workspace.

## Context and Orientation

The existing backend onboarding contract lives in
`src/api/flaskr/service/profile/onboarding.py` and
`src/api/flaskr/service/common/profile_onboarding.py`; learner routes are exposed
from `src/api/flaskr/route/user.py`. The retired implementation saved three global
variable values and an append-only `_sys_profile_onboarding_state` sentinel; only
the sentinel is read to classify existing users for the non-blocking upgrade
experience.

The current learner UI is
`src/cook-web/src/components/profile-onboarding/ProfileOnboardingModal.tsx`.
`profileOnboardingFlow.ts` parses a narrow syntax subset with regular expressions.
The operator page repeats that parser for validation and preview.

Official MarkdownFlow execution is wrapped by `MdflowContextV2` and
`RUNLLMProvider` in `src/api/flaskr/service/learn/context_v2.py`. The lesson
preview hook and `ContentBlock` demonstrate the canonical element SSE and
`markdown-flow-ui` renderer contracts.

Course teaching and Ask both retrieve the course prompt through
`RunScriptContextV2.get_system_prompt()`. Formal preview resolves the same concept
through `RunScriptPreviewContextV2._resolve_document_prompt()`. These two
resolvers call one shared composer; downstream MarkdownFlow, Ask, provider,
logging, metering, and Langfuse code remains profile-agnostic.

## Plan of Work

1. Add `learner_profile` and `learner_profile_updated_at` to the canonical user
   model, repository aggregate, migration, and dedicated read/replace/clear
   service. Add fixed profile-v2 state upsert/query helpers with legacy-state
   classification for blocking versus non-blocking presentation.
2. Extract a transient MarkdownFlow execution core from the preview path. Add a
   shared-Redis-only session store that fails closed when Redis is unavailable,
   snapshots the validated operator document and locked summary block, owns
   cursor/context/variables, and exposes canonical element SSE without course
   progress or teacher billing.
3. Redesign user routes around status, session start/run, complete, skip, and
   learner-profile management. Keep the learner-profile API text-only and leave
   deprecated course-variable data outside this feature.
4. Replace the modal with a route selector, guided renderer, paste editor, and
   final confirmation state. Add mobile full-screen layout, session draft
   preservation, accessible streaming announcements, and settings controls.
5. Replace operator regex validation and preview with server-side official
   MarkdownFlow validation and a non-persistent runtime preview. Preserve the
   global enabled kill switch.
6. Add one course-prompt composer and call it from the existing runtime and formal
   preview resolvers. Keep all downstream course-prompt consumers unchanged, add
   visible preview disclosure, and ensure onboarding-config preview is exempt.
7. Add focused backend/frontend tests, browser coverage, i18n parity, and
   repository-wide gates.

## Concrete Steps

From the repository root:

1. Add and review the Alembic migration for canonical user profile columns.
2. Implement backend services and focused tests under `src/api/tests/service/`.
3. Implement frontend APIs, components, settings, operator config, and i18n.
4. Run focused tests after each subsystem, then:

       python scripts/check_architecture_boundaries.py
       python scripts/check_repo_harness.py
       python scripts/check_dev_tools.py
       cd src/cook-web && npm run type-check
       cd src/cook-web && npm run lint
       cd src/cook-web && npm run test:e2e
       lefthook run pre-commit --all-files

## Validation and Acceptance

- A user is first asked whether they have a familiar AI agent. Yes opens the
  copy/paste flow; no starts official MarkdownFlow questions.
- Both paths save only `user_users.learner_profile`; guided interaction variables
  never create profile variable values.
- Completing, editing, or clearing a learner profile leaves all historical
  `sys_user_background` and `sys_user_style` rows unchanged so old courses can
  continue resolving them.
- Confirmed text is at most 1000 Unicode code points, can be multiline, and is
  safety checked. Clearing is explicit and does not re-trigger onboarding.
- Existing legacy completed and skipped users are presented once without cohort
  gating. Config edits never re-present completed/skipped users.
- Active sessions finish against their creation-time config snapshot even after
  an operator edits the live config.
- The runtime and formal-preview course-prompt resolvers append the current
  user's profile exactly once at the end of a non-empty course prompt, with clear
  lower-priority and untrusted-data instructions. Teaching, Ask, and providers
  reuse that effective course prompt only through their pre-existing paths.
- Langfuse records the same profile-enriched generation input sent to the model
  and the actual resulting output; no profile-specific trace override replaces
  either value.
- Formal preview visibly states whether the current user's profile is active.
- Onboarding-config preview never injects an existing profile.
- No onboarding request creates course progress, generated blocks, orders, or
  teacher-billable usage.
- Mobile, keyboard, screen-reader status, copy feedback, retry, skip, and error
  recovery are covered by focused tests or documented manual verification.

## Idempotence and Recovery

- Fixed `(user_bid, profile_onboarding, profile-v2)` state writes are upserts and
  tolerate concurrent complete/skip requests.
- Complete atomically updates the canonical profile and v2 state. A failed write
  leaves the previous profile and state unchanged.
- Skip deletes transient session data and never clears an existing profile.
- Re-running profile replacement with the same text is a no-op except where the
  explicit source/state transition requires an update.
- If an SSE run stops before the state commit, retry addresses the same expected
  block. If the state commit succeeds but the terminal event is lost, retrying the
  same request identity replays the cached full event sequence without another
  cursor advance or model call.
- New sessions do not depend on orphaned sessions, which expire by TTL.
- Operator rollback remains possible through the enabled kill switch; disabling
  collection never deletes profiles or stops existing profiles from personalizing
  course prompts.

## Interfaces and Dependencies

- Canonical user model: `learner_profile`, `learner_profile_updated_at`.
- Learner APIs: onboarding status, create session, request-identified run session
  SSE, complete, skip, and GET/PUT/DELETE learner profile.
- Admin API: enabled, MarkdownFlow document, document prompt, config revision,
  update metadata; no completion-version control.
- SSE reuses the existing `element`, `done`, and `error` event family and stable
  `element_bid` semantics. Run requests optionally carry the backward-compatible
  pair `expected_block_index` and `request_id`; the new clients always send both.
- Backend depends on installed `markdown-flow` and the existing LLM/provider,
  metering, Redis, request trace, and content-safety services.
- Frontend depends on installed `markdown-flow-ui/renderer`, `remark-flow`, the
  shared request layer, existing dialog/full-screen primitives, and i18n JSON.

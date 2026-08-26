# Give operators and learners explicit control of AI-assisted onboarding

## Purpose / Big Picture

Apply the user's six corrections to PR #2669: editable operator assistant
prompts, a floating lower-right learner entry, concise assistant instructions,
no copy-section heading, explicit processing after paste, and correct speaker
conversion of MarkdownFlow interaction text. These supersede the initial
read-only prompt and automatic-paste decisions in the earlier completed plans.

## Progress

- [x] 2026-08-26 UTC: Inspect current feature branch, guidance, admin save and
  session/view contracts. Read the new request as operator editing of the saved
  public prompt, not per-learner rewriting of public configuration.
- [x] 2026-08-26 UTC: Add validated editable prompt publication and admin editor.
  Focused backend tests: 151 passed; admin page Jest: 16 passed.
- [x] 2026-08-26 UTC: Move learner entry, remove auto-processing and copy title,
  update five locale strings and compiler speaker rules.
- [x] 2026-08-26 UTC: Verify related backend tests (342 passed) and full
  frontend Jest (177 suites / 1,517 tests passed), plus translation validation,
  translation usage and architecture (zero new violations).
- [x] 2026-08-26 UTC: Inspect the actual conversation, shared collection wrapper
  and official renderer in an isolated local Dialog fixture at 1440x900,
  360x640, 390x844 and 844x390 in Chinese and Arabic RTL. Confirm button
  clearance, early copy access, editable drafts, explicit processing, input
  retention and zero horizontal overflow. Remove the temporary route, restore
  the browser viewport/language and leave the user's frontend server running.
- [x] 2026-08-26 UTC: Complete final types, lint, repository harness and
  lefthook verification before publication to the existing ready PR.
- [x] 2026-08-26 UTC: Publish implementation as 3e1f1ed6a. All CI passed:
  backend 7m04s, frontend 1m48s, runtime harness 6m42s, static/format/lint,
  CodeQL and security checks. Natural CodeRabbit review completed.
- [x] 2026-08-26 UTC: Fix copied feedback after a failed retry; all 13 assistant
  view tests and focused ESLint passed. Keep this review fix in its own commit.
- [x] 2026-08-26 UTC: Reject truncated or incomplete compiler responses without
  publishing. The expanded backend suite passed 356 tests, including missing
  terminal metadata; the full frontend suite still passed 1,517 tests, and
  TypeScript and Ruff passed. Keep this second review fix separate.

## Surprises & Discoveries

The previous save route rejected assistant_prompt, and the admin editor always
replaced its prompt with the response. Both changed together so an edit made
during a save is not lost. The 600ms paste scheduler was deleted completely;
the view's remaining timer only clears copy feedback.

The saved public prompt's language is independent of the interface. Its preview
now uses automatic text direction, keeping a Chinese prompt readable inside
Arabic UI without changing the copied text. Browser viewport captures can lag
a resize by one frame; final captures were checked after layout had settled.

Natural review found a clipboard feedback mismatch after success followed by
failure. Clear the copied state immediately in the failure handler; the existing
clipboard regression now asserts the retry label without advancing any timer.
The [review](https://github.com/ai-shifu/ai-shifu/pull/2669#pullrequestreview-5029668284)
is outside the diff range and has no resolvable inline thread. It is handled as
an independent verified follow-up commit.

The [truncation review](https://github.com/ai-shifu/ai-shifu/pull/2669#discussion_r3862124509)
exposed a shared-wrapper limitation: content-free terminal chunks, including
their finish reason, do not reach callers. The compiler now requests one strict
JSON envelope containing the public text and a trailing completion flag. It
rejects visible truncation metadata and incomplete/invalid envelopes, including
partial output without terminal metadata. It consumes the entire response
iterator so shared usage accounting and tracing still finish. Only the extracted
plain prompt is published; manual edits, stored JSON, user APIs and frozen
sessions retain their contract. The shared LLM wrapper is unchanged, and there
is no plaintext fallback or second compiler protocol.

A [nickname-only observation](https://github.com/ai-shifu/ai-shifu/pull/2669#discussion_r3862118393)
matches the previously approved explicit-replacement contract. It was explained
with the prior decision link and left open as an observation, not resolved as
a code fix. No old introduction is silently merged into the reviewed result.

## Decision Log

- Only operators may save the optional assistant_prompt field. Explicit
  nonblank text wins without LLM compilation after official document validation;
  explicit blank text regenerates for a nonempty document. Omitted text retains
  source-change/missing-result generation and unchanged-result reuse. Nonblank
  prompts with empty documents are invalid. Keep one JSON and the same byte
  limit, publication lock, DB comparison, revision and cache-failure semantics.
- The admin UI submits the field only when edited, including deliberate blank
  text. Preserve edits made while saving and all input on failure. An unchanged
  prompt does not prevent automatic regeneration after document edits.
- The floating entry stays within the MarkdownFlow viewport at physical bottom
  right (also in RTL); reserve scroll padding so it cannot cover the last input.
  Show as soon as a frozen public prompt is available, even before the question.
- Paste and typing only edit the draft. Only the processing button submits;
  request replay, import locks, account isolation and confirmation remain.
- Interaction text inside ?[] is displayed to the learner: its "you" means the
  learner, while an option such as "I won't tell you" already uses learner "I".
  Preserve that speaker identity when compiling first-person questions. Do not
  mechanically swap every pronoun, parse custom syntax or invent fixed topics.
- Work is confined to this worktree. Backend config/route/tests and admin
  UI/tests are delegated separately; the primary owns learner UI, i18n, compiler,
  integration and this plan. No dev/main push or live config write is implied.

## Outcomes & Retrospective

All six requested behaviors are implemented, with deterministic service/UI
regressions and real-browser fixture checks. The tests exercise explicit edits,
blank regeneration, unchanged omission, publication failure/CAS/cache semantics,
edits during save, paste/typing/composition/restoration without submission,
same-session retry and existing profile confirmation. The compiler contract now
describes the interviewer-versus-learner roles inside ?[] and preserves choices
that already speak as the learner. No live model was asked to regenerate an
existing config; stored prompts and sessions do not change until an operator
saves a new version and the learner starts a new collection.

Local implementation and verification are complete, including all repository
gates and lefthook. GitHub PR #2669 is the delivery surface; its description
records publication, CI and natural-review status for the published commit,
independently of the earlier green head. No live administrator configuration,
dev branch, main branch or deployment is changed by this work.

## Context and Orientation

`service/common/profile_onboarding.py` publishes the public config through the
existing DB helper; `route/admin_profile_onboarding.py` owns operator input.
The admin route's controller owns editor snapshots. `ProfileOnboardingConversation`
keeps the real renderer mounted; `ProfileAssistantAnswersView` owns copy/paste.
`src/api/prompts/profile_onboarding_assistant_compiler.md` owns compilation rules.
Existing source-hunk provenance remains in the original completed PR3 ExecPlan.

## Plan of Work

Extend the existing optional config field without adding an endpoint or schema.
Expose controlled admin editing and preserve concurrent editor changes. Reshape
only the learner question wrapper to anchor the button and provide clearance.
Delete automatic paste scheduling and obsolete locale keys. Explain the ?[]
speaker roles in the compiler template, including name, profession and choices.

## Concrete Steps

Focused pytest used official MarkdownFlow 0.3.1 and covered config, publication,
routes, profile research, request validation, profile storage, optimizer and
legacy compatibility. Full frontend `npm run test:ci`, `npm run type-check`,
`npm run lint`, Ruff check/format, `check_translations.py`,
`check_translation_usage.py --fail-on-unused`, `check_architecture_boundaries.py`,
`check_repo_harness.py`, `check_dev_tools.py` and
`lefthook run pre-commit --all-files` passed. Reused the running local frontend
for real-browser fixture checks without saving live administrator configuration.

## Validation and Acceptance

Manual prompt edits persist and reach fresh sessions unchanged; existing sessions
retain their version. Empty/omitted/invalid/oversized prompt inputs and failed or
concurrent publication preserve the existing guarantees. Admin edits survive
save races and failure. The entry is visible and reachable at all four prior
viewports in Chinese and Arabic RTL, without covering the final input. Paste,
typing, composition and draft restoration never submit, even after timers;
manual processing submits once. The copy section has no redundant heading and
the exact requested Chinese instructions use 千问, not 千问工作. Prompt compiler
instructions distinguish learner-facing questions from learner-voiced choices.

## Idempotence and Recovery

Do not interrupt or recreate sessions when switching subviews. Keep request
fingerprints, replay and uncertain-result controls. Keep the publication
transaction and byte limit for manual and generated prompts alike. No migrations,
library updates or unrelated shared-module refactors. Do not publish live config
through browser QA. Keep the user's local frontend server running when finished.

## Interfaces and Dependencies

The only wire change is accepting optional string assistant_prompt on the
existing operator POST; learner endpoints and save contracts are unchanged.
Backend support must deploy before frontend operator edits are saved. Prompt
updates, whether manual or regenerated, apply to new sessions only. A deliberate
blank prompt plus Save now provides a way to regenerate unchanged documents.

# Localize profile-onboarding assistant prompts for every supported language

## Purpose / Big Picture

Generate one public assistant prompt for every application-supported locale when
an operator saves the profile-onboarding configuration. Learners keep sending
their current interface locale when starting a session; the backend selects and
freezes one matching prompt so copying, importing, replay, and existing sessions
retain their current single-string contract.

## Progress

- [x] 2026-08-30 CST: Inspected the current compiler, config publication,
  locale resolution, session snapshot, admin editor, and focused tests.
- [x] 2026-08-30 06:52 CST: Added strict master-prompt localization and
  persisted locale mappings with legacy fallback.
- [x] 2026-08-30 06:58 CST: Selected and froze the localized prompt when a
  learner session starts.
- [x] 2026-08-30 07:21 CST: Updated operator copy and completed focused,
  repository, and development-mode generation verification.

## Surprises & Discoveries

- The learner frontend already sends `i18n.resolvedLanguage` when creating the
  session. The missing behavior is entirely after language resolution: the
  backend previously froze the same scalar prompt for every locale.
- The existing operator editor intentionally exposes one editable prompt. It
  remains the document-language master rather than becoming five editors.
- `PROFILE_ONBOARDING_FLOW` is one versioned JSON value in a MySQL `TEXT`
  column, so the locale map needs no schema migration but remains subject to
  the existing 65,535-byte serialized limit.
- A disabled first save can include the editor's default MarkdownFlow while
  still being uninitialized. That path must persist without either model call.
- Source-locale aliases such as `zh`, `zh-cn`, and `zh-TW` can otherwise evade
  source-text preservation. Unique primary-language matches are canonicalized
  to the shared registry key before byte-for-byte comparison.

## Decision Log

- Generate every locale from the shared application locale registry rather
  than maintaining a second hard-coded list.
- Keep `assistant_prompt` as the editable master and add
  `assistant_prompts` as generated locale-to-text data.
- Select prompt text in the backend and keep learner/session APIs on one
  `assistant_prompt` string.
- Resolve missing versions in this order: exact locale, generated `en-US`,
  legacy master, then unavailable.
- Do not backfill live configuration on deployment. The next ordinary operator
  save generates the locale map; an unchanged disable remains independent of
  the LLM.
- If a disabled configuration has no master prompt, save its document directly
  without initialization. A disabled legacy configuration that already has a
  master still localizes that master on its next ordinary save.
- Treat exact, case-insensitive, and unique primary-language source-locale
  matches as the corresponding supported locale for source preservation.

## Outcomes & Retrospective

Implemented the complete save-time localization stage and learner-session
selection without changing the single-string learner or Redis contract. Old
configurations remain untouched until an operator saves; old sessions retain
their frozen scalar prompt.

Focused backend configuration, compiler, publication, and route coverage
passed with 199 tests, and the profile-research runtime passed 80 tests.
Frontend profile-onboarding coverage passed with 83 tests; TypeScript, ESLint,
translation validation, architecture boundaries, repository harness, developer
tooling, and the complete lefthook gate also passed. A development-mode live
generation smoke returned exactly `ar-SA`, `en-US`, `fr-FR`, `th-TH`, and
`zh-CN`, with all values nonblank and the Chinese master unchanged. The smoke
called only the localizer and did not publish an operator configuration.

## Context and Orientation

`service/common/profile_onboarding.py` owns canonical configuration and save
semantics. `service/common/profile_onboarding_prompt.py` owns the LLM compiler.
`route/profile.py` resolves the learner locale and creates the frozen session.
The operator page under `cook-web` continues to edit only the master prompt.

## Plan of Work

Keep the existing document-to-master compiler, then localize that master in one
strict LLM call for every supported locale. Persist both artifacts atomically.
On session creation, resolve the locale once, select the best available prompt,
and pass only that string into the unchanged profile-research session runtime.

## Concrete Steps

1. Add and validate the localization envelope, including complete locale keys,
   nonblank values, truncation handling, and exact preservation of a detected
   source-locale master.
2. Extend config normalization, serialization, reuse/regeneration conditions,
   legacy reads, size checks, and admin responses with `assistant_prompts`.
3. Select the localized prompt before starting learner sessions while keeping
   existing Redis and response shapes unchanged.
4. Clarify the operator master-prompt copy in every supported UI locale and run
   focused tests before repository-wide gates.

## Validation and Acceptance

Compiler tests must reject incomplete or malformed maps. Config tests must
cover document edits, explicit master edits and resets, legacy-map backfill,
unchanged reuse, emergency disable, atomic failure, and byte limits. Route tests
must prove Chinese, French, and Arabic selection plus English and legacy
fallback. Existing sessions must remain frozen. Translation, frontend type/lint,
backend lint, architecture, harness, development-tool, and lefthook checks must
pass before completion.

## Idempotence and Recovery

No persisted value changes until both master generation (when needed) and all
locale generation succeed. Publication retains the existing full-value CAS,
named lock, revision, and post-commit cache semantics. Retrying after a failed
generation is safe because the old value remains durable.

## Interfaces and Dependencies

The persisted/admin-read configuration adds
`assistant_prompts: Record<locale, string>`. Operator writes continue to accept
only the existing `assistant_prompt` master. Learner session responses and Redis
payloads remain unchanged. The implementation reuses the default LLM wrapper,
shared Langfuse helpers, and shared i18n locale registry; it adds no dependency
or database migration.

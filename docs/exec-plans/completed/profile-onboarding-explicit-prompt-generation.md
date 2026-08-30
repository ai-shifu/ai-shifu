# Make profile-onboarding prompt generation explicit

## Purpose / Big Picture

Give operators one predictable workflow for personalization setup: edit the
interactive-question document, explicitly generate or rewrite the public
"Let my AI answer" prompt, then save both together. Saving must never silently
rewrite the visible master prompt. The administrator language follows the
learner journey: Personalization setup, interactive questions, Let my AI
answer, and the personal introduction the learner reviews and saves.

This plan supersedes the completed assistant-controls decision that an empty
prompt plus Save regenerates the master. It preserves the later multilingual
decision: one operator-editable master is localized atomically when the
configuration is saved, and already-started learner sessions keep their frozen
prompt.

## Progress

- [x] 2026-08-30 CST: Rechecked the clean detached checkout against current
  `origin/main` and created
  `sunner/profile-onboarding-explicit-prompt-generation` at
  `011a4abc45d62dfe8c5f5d70ee5f0bf73afdf3a3`.
- [x] 2026-08-30 CST: Inspected the operator page/controller, API wrappers,
  configuration publication service, prompt compiler/localizer, learner prompt
  selection, existing tests, translation keys, and analytics contract.
- [x] 2026-08-30 CST: Added the non-persisting master-generation endpoint,
  removed implicit master generation from every save path, and kept rollout
  compatibility without allowing omitted legacy fields to erase prompts.
- [x] 2026-08-30 CST: Implemented the explicit generate/edit/save draft
  workflow, snapshot/concurrency protection, dirty-state protection, modal
  failure feedback, and versioned fail-open analytics.
- [x] 2026-08-30 CST: Unified all five locales, corrected the learner loading
  residue, regenerated translation types, and preserved every locale's default
  MarkdownFlow document byte-for-byte.
- [x] 2026-08-30 CST: Completed focused and full backend/frontend verification,
  translation/type/lint/architecture/harness checks, the complete 19-hook
  pre-commit gate, and isolated desktop plus Arabic RTL browser QA.
- [x] 2026-08-30 CST: Applied the product follow-up that the sidebar menu uses
  the shorter "Personalization Guide" concept without a configuration suffix;
  the page title and breadcrumb continue to identify the configuration page.

## Surprises & Discoveries

- The current prompt textarea is already editable, but the controller sends it
  only when changed and the backend may still regenerate it merely because the
  MarkdownFlow document changed. The frontend and service semantics must move
  together.
- Save-time master compilation and save-time localization are separate model
  operations. Only the former moves to the explicit endpoint; localization
  remains part of atomic publication.
- The existing JSON configuration already contains revision and localized
  prompt fields, so no schema migration is required.
- A failed initial GET currently leaves a writable default form. The revised
  controller must make load failure a locked state with an explicit retry.
- Source inspection is complete, but browser capture of the existing dev page
  timed out during planning. Visual acceptance therefore remains an explicit
  implementation gate rather than a claimed baseline result.
- Independent backend review found that an old client could omit the prompt
  while clearing the document and thereby erase a saved master/map. The
  compatibility path now rejects that orphaned combination unless the client
  explicitly clears the prompt while disabled.
- Repairing one missing localization initially invoked the model for all
  locales and discarded the extra results. The localizer now accepts an exact
  registered-locale subset, so repair requests include only missing locales
  and strictly validate that subset.
- Frontend review found two navigation races: bubble-phase link interception
  could lose to Next navigation, and the dirty-dialog actions could race an
  in-flight save. Capture-phase interception and ref-guarded, frozen dialog
  decisions now preserve the original draft and destination.
- Browser QA found the shared textarea reset removed its visible keyboard
  outline without adding a ring. Both editors now add a page-scoped focus ring
  without changing the shared component.

## Decision Log

- Use `个性化引导` for the sidebar menu and `个性化引导配置` for the page title
  and breadcrumb. Preserve the learner concepts `个性化设置`,
  `让我的 AI 帮我回答`, and `个人介绍` across every locale.
- Put one outline generate/regenerate button directly below the MarkdownFlow
  editor. A later accepted click may replace the current prompt without a
  confirmation dialog.
- Generate only the master prompt. Generation does not publish configuration,
  update revision/cache metadata, localize text, or affect learner sessions.
- Keep inputs editable during generation. Apply a response only when both the
  document and prompt still match the request snapshot; otherwise classify it
  as superseded and preserve the newer draft.
- Enabled configurations require both a nonblank valid document and a nonblank
  prompt. Disabled configurations may retain a document with a blank prompt.
  A nonblank prompt without a document is always invalid.
- Save submits full values plus `config_revision`. Omission remains temporarily
  compatible for old clients, but omission never authorizes master compilation.
- Save localizes a changed nonblank master or repairs an incomplete locale map.
  A document-only edit reuses the existing master and complete locale map.
- Reuse the existing admin design system and route. Do not change the default
  MarkdownFlow questions, persisted schema, menu machine ID, learner endpoint,
  locale fallback, or frozen-session behavior.
- Reuse the existing admin before-unload and same-origin-link warning pattern.
  Browser history `popstate` blocking remains a shared App Router limitation
  and is intentionally not solved differently on this one page.

## Outcomes & Retrospective

The operator now has one explicit, editable draft workflow: generate or
regenerate beneath the current document, keep editing either field, and publish
the complete visible pair with one revision-checked save. Generation has no
persistence or localization side effects. Save never recompiles the master;
it reuses complete maps, localizes a changed master, or requests only missing
locales before atomic publication. Legacy omissions remain accepted only when
they can preserve the existing prompt contract safely.

Focused backend verification passed 311 tests, and the complete API suite
passed 3,554 tests with 17 skipped. The complete Cook Web suite passed 186
suites / 1,702 tests; the focused admin/API set passed 29 tests. TypeScript,
frontend lint (with repository-baseline warnings only), translation validation
and usage, architecture boundaries, repository harness, and developer-tool
checks passed.

Browser QA used an isolated local mock API and the actual page at a 1440x1000
desktop viewport. It verified the loaded Chinese layout, explicit generation
without a revision change, document-sync warning, manual combined save and
revision update, locked load-failure controls plus successful reload, Arabic
RTL with no horizontal overflow, and a visible keyboard focus ring. Evidence
is stored under the task's Codex visualization directory; no production
configuration or real user session was read or changed.

The complete 19-hook lefthook pre-commit gate passed after these code and
contract changes. The only frontend lint output was the repository's existing
warning baseline; no new warning was introduced in the touched files.

## Context and Orientation

The Flask operator route owns GET, save, preview, and the new generate endpoint.
The common profile-onboarding service owns normalized JSON, validation,
revisioned publication, and the distinction between master generation and
localization. The Cook Web route controller owns loaded/saved baselines,
request snapshots, dirty state, and UI error state. Shared i18n JSON owns every
visible string, while Cook Web's shared tracking hook owns Umami delivery.

The persisted object remains `enabled`, `markdownflow`, `assistant_prompt`,
`assistant_prompts`, revision, and update metadata. The application-wide locale
registry remains the sole target-locale source.

### Operator prompt-generation analytics

- Business question: how often do authenticated operators explicitly generate
  or regenerate the prompt, and what share of accepted attempts is applied,
  fails, or becomes obsolete because the draft changed?
- Metric definition: raw result events divided by raw attempt events over the
  same reporting window, grouped by `mode` and `outcome`. Counts are aggregate,
  not exact row-level joins because no correlation identifier is collected.
- Events: `operator_profile_prompt_generate_attempt` and
  `operator_profile_prompt_generate_result`.
- Actor and surface: authenticated operators on
  `/admin/operations/profile-onboarding`; learner and preview flows are
  excluded.
- Trigger: attempt after local validation and the in-flight guard, immediately
  before the request; exactly one result when that request is applied, fails,
  or is superseded.
- Count unit and deduplication: one accepted request. Concurrent re-entry is
  blocked; later deliberate retries/regenerations count separately. No
  persisted deduplication.
- Consumer: aggregate operator adoption and generation-reliability reporting.
- Compatibility: additive event family with no historical backfill.

| Field | Type | Allowed values | Privacy class | Why required |
| --- | --- | --- | --- | --- |
| `mode` | string | `generate`, `regenerate` | non-personal enum | distinguish initial use from deliberate replacement |
| `outcome` | string | `success`, `failed`, `superseded` | non-personal enum | measure the terminal result without prompt or error text |

Feature producers send only these fields. The shared helper may add its
grandfathered transport metadata; tests cover the feature-owned allowlist and
must not claim that mocked-hook coverage proves the final provider payload.
Tracking is fail-open and never changes generation behavior.

### Operator dirty-navigation analytics

- Business question: how often do authenticated operators encounter the
  unsaved-draft navigation guard, which decision do they make, and what is the
  outcome when they choose Save and leave?
- Metric definition: count raw shown, decision, and save-result events over the
  same reporting window. Group decisions by `decision` and save results by
  `outcome`; compare aggregate save-result counts with aggregate
  `save_and_leave` decisions. These are not exact row-level conversions because
  no correlation identifier is collected and deliberate retries can produce
  more than one decision within one shown lifecycle.
- Events: `operator_profile_dirty_navigation_shown`,
  `operator_profile_dirty_navigation_decision`, and
  `operator_profile_dirty_navigation_save_result`.
- Actor and surface: authenticated operators on
  `/admin/operations/profile-onboarding` with a dirty draft. Clean navigation,
  learner/preview flows, external/new-tab/download/modifier/same-page links,
  clicks rejected by the in-flight guard, and native `beforeunload` are
  excluded. Native browser prompts and their user decisions cannot be observed
  or delivered reliably.
- Trigger: shown after the custom dialog is committed open; decision after a
  guarded Cancel, Discard, or Save and leave action is accepted; exactly one
  save result after each accepted Save and leave action finishes.
- Count unit and deduplication: one custom dialog-open lifecycle for shown and
  one accepted user action for decision. A Save and leave retry after failure
  or supersession is a new decision and result. Disabled re-entry produces no
  event, and there is no persisted cross-visit deduplication.
- Consumer: aggregate operator workflow-completion and draft-protection
  reporting.
- Compatibility: additive v1 event family with no historical backfill.

| Event | Feature-owned payload |
| --- | --- |
| `operator_profile_dirty_navigation_shown` | `{}` |
| `operator_profile_dirty_navigation_decision` | `{decision}` |
| `operator_profile_dirty_navigation_save_result` | `{outcome}` |

| Field | Type | Allowed values | Cardinality | Privacy class | Why required |
| --- | --- | --- | --- | --- | --- |
| `decision` | string | `cancel`, `discard`, `save_and_leave` | low | non-personal enum | distinguish the operator's guarded choice |
| `outcome` | string | `success`, `failed`, `superseded` | low | non-personal enum | measure the terminal save result without drafts or errors |

The feature-owned payload must not include the destination URL/path/query/hash,
document or prompt text, locale, revision, error text, or any resource or
correlation identifier. The shared helper still adds its grandfathered
`user_type`, `user_id`, `device`, and localized `timeStamp` fields; these are
inherited transport behavior and are not approved consumer dependencies for
this event family. Producer tests verify the feature-owned allowlist only.
Tracking remains fail-open and never delays or changes dialog, save, or
navigation behavior.

## Plan of Work

1. Add strict request/response contracts and focused route tests for explicit
   generation. Make the save service treat submitted prompt text as final,
   validate revision before model work, and preserve atomic localization.
2. Replace the controller's one-field saved ref with a full saved baseline.
   Add request mutexes, request snapshots, dirty-state/leave protection,
   locked load-failure recovery, combined save, and typed analytics calls.
3. Insert the generate button and state notices beneath the document editor.
   Keep preview isolated and use the existing operator page components.
4. Replace operator-facing terminology in all supported locales, correct the
   learner loading residue, and regenerate the typed translation inventory.
5. Run narrow tests first, widen to repository gates, then verify the actual
   desktop and Arabic RTL page states in the available browser without saving
   production configuration.

## Concrete Steps

- Add `POST /api/shifu/admin/operations/profile-onboarding/assistant-prompt/generate`
  with request `{markdownflow}` and response `{assistant_prompt}` in the shared
  envelope.
- Change save requests to full `{enabled, markdownflow, assistant_prompt,
  config_revision}` values. Accept old omissions temporarily; validate a
  supplied revision against the loaded database revision before localizing.
- Delete every save-time call to the master compiler. Reuse complete locale
  maps, localize changed masters, repair incomplete maps, and clear prompt/maps
  when the disabled configuration is explicitly cleared.
- Track and render `loading`, `loadFailed`, `generating`, `saving`, saved
  baseline, document-needs-prompt-review, generation status, and preview state
  without allowing stale asynchronous responses to overwrite newer input.
- Add exact translation keys for generation labels/status, validation,
  load retry, dirty confirmation, and the unified operator terminology.
- Regenerate `docs/exec-plans/index.md` through the repository knowledge-index
  generator after this active plan exists.

## Validation and Acceptance

- An operator can generate a prompt without issuing the save request; the
  visible revision/update metadata and persisted config remain unchanged.
- A second accepted generation replaces an unchanged draft. Manual prompt or
  document edits made during generation survive, and the response is reported
  as superseded.
- Saving publishes exactly the visible document and master together. Enabled
  missing-field cases fail locally and server-side; disabled blank-prompt saves
  clear the locale map. Failed localization, size validation, CAS, transaction,
  or cache publication never publishes a partial document/prompt pair.
- A changed document never invokes the master compiler. A changed master
  localizes all supported locales; an unchanged complete map avoids model work;
  an incomplete map is repaired.
- Load failure cannot mutate configuration until retry succeeds. Save and
  generation double-clicks do not create duplicate operations. Unsaved drafts
  trigger the existing leave-protection pattern.
- Analytics tests assert exact names/payloads, trigger order, invalid/double
  click exclusions, every terminal outcome, prohibited-field absence, and
  business behavior when tracking throws or rejects.
- All five locales pass translation validation and key-usage checks. Visible
  operator text contains no generic learning-profile/master/runtime jargon.
- Focused Jest and pytest pass, followed by type-check, frontend/backend lint,
  architecture boundaries, repository harness, developer-tool verification,
  and the complete lefthook pre-commit gate.
- Browser QA verifies button placement, long-copy wrapping, loading/error and
  keyboard-focus states, and Arabic RTL at the same desktop viewport before
  claiming complete visual validation.

## Idempotence and Recovery

Generation is intentionally non-persisting and safe to retry. The UI accepts at
most one request at a time and ignores obsolete responses. Save retains the
existing database comparison, named lock, transaction, revision, and cache
refresh-pending recovery semantics. A failed save leaves the complete local
draft available for retry. No migration, live configuration write, or session
restart is part of implementation or browser QA.

## Interfaces and Dependencies

- New operator API: `POST
  /api/shifu/admin/operations/profile-onboarding/assistant-prompt/generate`.
- Changed operator save request: optional-for-rollout `assistant_prompt` and
  `config_revision`; the new UI always sends both.
- Existing config response, preview/session endpoints, saved JSON schema,
  MarkdownFlow validator, shared LLM wrapper, locale registry, Redis session
  shape, and learner response contracts remain stable.
- Backend compatibility must deploy before the frontend begins using the new
  endpoint. No external package or database dependency changes.

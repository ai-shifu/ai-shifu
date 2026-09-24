# German (Germany) Product Localization

## Purpose / Big Picture

Add `de-DE` as an AI-Shifu interface language. A learner or teacher choosing
German should receive German application copy and API messages, with correct
language selection, persistence, formatting, and legal-document fallback.
Keep authored course language independent of the interface. The pinned
MarkdownFlow UI library has no German controls; its translations are separate
library work and are outside this change.

## Progress

- [x] 2026-09-24 16:37 CST: Fetched merged `main`, created an isolated German
  branch and worktree, read the new product-locale checklist, and counted 58
  Chinese source files containing about 4,320 strings.
- [ ] 2026-09-25: Review all German shared translations against the Chinese
  source and relevant product context. The first pass has been corrected for
  structural errors and several high-risk terms; semantic review remains.
- [x] 2026-09-25: Register German across frontend, backend, legal URL handling,
  existing saved onboarding prompts, and explicit locale contracts.
- [ ] 2026-09-25: Verify translations, language selection, backend behavior,
  legal fallback, independent content language, and latest-head CI. Targeted
  tests, frontend build, Arena browser smoke, and all-files pre-commit passed;
  final PR CI and broader copy review remain.

## Surprises & Discoveries

- `src/i18n` has 58 JSON files per locale and about 4,320 string values.
- The pinned `markdown-flow-ui` release lists six control locales and does not
  list `de-DE`; the host's locale bridge already falls back to English for an
  unsupported control locale.
- An existing Spanish-specific onboarding prompt backfill provides the
  previewable, idempotent pattern for adding a locale to saved installations.
- Initial machine-translated text contained incorrect billing terminology and
  repeated phrases that parity checks cannot detect. German copy needs a
  Chinese-source semantic pass before the PR is ready to merge.

## Decision Log

- 2026-09-24: Use Germany German (`de-DE`) for the request for German; do not
  add Austrian or Swiss variants as separately selectable locales.
- 2026-09-24: Translate application-owned text from Chinese with call-site
  context. Preserve keys, ICU argument names, markup, links, technical IDs,
  and saved authored course data.
- 2026-09-24: Do not translate, publish, or upgrade dependency libraries for
  this product-language task. State the actual MarkdownFlow control fallback.

## Outcomes & Retrospective

Pending implementation and verification.

## Context and Orientation

The canonical inventory is `src/i18n/locales.json`; each locale has matching
JSON under `src/i18n/<locale>/`. `docs/references/i18n.md` is the delivery
checklist. `src/web/src/i18n.ts` selects the browser language, while backend
i18n loads the same files. Explicit locale unions also exist in billing,
email, legal URLs, and the MarkdownFlow host bridge.

## Plan of Work

1. Produce `src/i18n/de-DE/` from the Chinese source structure. Review high
   impact copy such as billing, permissions, error recovery, onboarding,
   legal references, and role terminology against call sites.
2. Register `de-DE` in locale metadata and explicit frontend/backend
   allowlists. Keep the pinned library version and its English control fallback.
3. Add or adapt the saved-onboarding prompt backfill with preview, idempotence,
   and preservation of existing custom values.
4. Add focused tests for the new selectable language, API behavior, legal
   fallback, and interface versus authored-content language.
5. Run translation parity and usage checks, metadata generation, focused tests,
   frontend type/lint/build, browser smoke where available, and repository
   commit gates. Recheck after any rebase and verify the final PR head and CI.

## Concrete Steps

Read `AGENTS.md` at each edited subtree. Keep translation preparation tools
outside the repository unless a reusable project tool is genuinely needed.
Compare the new locale's file/key structure and ICU placeholders to `zh-CN`.
Inspect calls for context-sensitive copy and normalize the new locale through
the existing language-selection path. Run `python scripts/check_translations.py`,
`python scripts/check_translation_usage.py --fail-on-unused`, and
`python scripts/generate_languages.py`; run the focused frontend and backend
checks named by touched modules.

## Validation and Acceptance

`de-DE` appears as Deutsch in all language selectors; browser detection and
saved preference restore it. The API accepts German and produces German
application messages. Every shared JSON file and key matches the current
inventory, with valid ICU syntax. Legal links visibly fall back to an existing
approved language when no German document exists. German UI does not relabel
English or unknown authored lessons as German. Embedded MarkdownFlow controls
use the currently pinned package's documented fallback. No dependency package
version changes in this PR. Focused tests, repository gates, and PR CI pass.

## Idempotence and Recovery

Keep source locales unchanged. Translation generation is repeatable and its
output is reviewed before commit. Any persisted-prompt backfill previews
changes, preserves custom prompts, and can be rerun safely. If deployment
does not apply it, record that limitation in the PR.

## Interfaces and Dependencies

- Shared locale files and metadata under `src/i18n/`
- Cook Web selector, locale normalization, billing, legal documents, and
  MarkdownFlow host adapter
- Backend locale loading, user/email language validation, billing DTOs, legal
  URL configuration, and persisted onboarding prompt backfill
- Existing published `markdown-flow-ui` package only; no library work

# Arabic and Thai Product i18n

## Purpose / Big Picture

Add Arabic (`ar-SA`) and Thai (`th-TH`) as first-class product locales across
the shared translation source, Cook Web runtime, backend message loader, and
user-visible layout behavior. Every translated value will be derived from the
Chinese source and checked against the code path that renders or formats it,
while preserving translation keys, ICU placeholders, MarkdownFlow syntax, and
technical identifiers.

## Progress

- [x] 2026-08-25 CST: Confirmed the worktree was clean and based on current `origin/main`.
- [x] 2026-08-25 CST: Created branch `sunner/add-arabic-thai-i18n`.
- [x] 2026-08-25 CST: Inventory locale metadata, namespaces, runtime registration, and visible untranslated text.
- [x] 2026-08-25 CST: Add Arabic and Thai translations and register both locales.
- [x] 2026-08-25 CST: Implement and verify Arabic RTL behavior and locale-sensitive layout handling.
- [x] 2026-08-25 CST: Run focused and repository-wide validation.

## Surprises & Discoveries

- The worktree started at detached `HEAD` on `origin/main`; no user changes were present.
- The repository already has a shared `src/i18n/` contract consumed by both backend and Cook Web, with locale metadata in `src/i18n/locales.json` and generated frontend key types.
- The legal-content source currently contains Chinese and English MDX only. Arabic, Thai, and French legal routes therefore use the English reference with an explicit localized notice until separately reviewed legal translations are supplied.
- The pinned `markdown-flow-ui@0.2.10` renderer exposes only `en-US`, `fr-FR`, and `zh-CN` built-in UI locales. Host-product translations and backend output-language selection can support Arabic and Thai now; the embedded renderer's own chrome needs a later library release and pin update.

## Decision Log

- Use the existing locale identifiers and metadata contract rather than introducing a second translation source.
- Treat Chinese values as the translation source of truth for this feature, but inspect each key's call site when wording depends on action, role, status, count, error semantics, or embedded syntax.
- Keep machine-facing keys, placeholders, URLs, identifiers, and MarkdownFlow tokens unchanged across locales.
- Prefer Arabic Saudi Arabic (`ar-SA`) and Thai Thailand (`th-TH`) metadata unless the existing locale contract or product conventions demonstrate a different supported tag.
- Add RTL only where the product's runtime and styling architecture support it safely; verify direction-sensitive controls and embedded code/content separately.
- Do not use an external translation service or translation API. Author Arabic and Thai values from the Chinese source with the model, using each key's call site and formatting contract to choose terminology and preserve placeholders/tokens.

## Outcomes & Retrospective

The product now has first-class `ar-SA` and `th-TH` locale bundles across all
56 shared JSON files, selectable metadata, backend language handling, Cook Web
loading, native output-language labels, legal URL slots, and document language
attributes. Arabic sets `dir="rtl"`; Thai remains LTR. All translation values
were authored from Chinese plus code-context review without an external
translation interface. Technical identifiers, placeholders, React tags, and
MarkdownFlow syntax remain unchanged. Legal MDX intentionally falls back to
English with a localized notice, and the pinned MarkdownFlow renderer remains
limited to its existing three built-in chrome locales until that dependency is
released with Arabic and Thai resources.

## Context and Orientation

- Shared locale source: `src/i18n/`.
- Locale registration and namespace metadata: `src/i18n/locales.json`.
- Cook Web i18n singleton and backend bridge: `src/cook-web/src/i18n.ts` and `src/cook-web/src/lib/`.
- Generated frontend key types: `src/cook-web/src/types/i18n-keys.d.ts`.
- Validation: `scripts/check_translations.py`, `scripts/check_translation_usage.py`, and the frontend i18n tests.
- Locale selection and document direction must be traced from the real app route/layout entry points before editing.

## Plan of Work

1. Inspect metadata, all locale files, language picker/selection code, backend
   loading and fallback behavior, and direction-sensitive shared styles.
2. Build a key inventory from the Chinese bundles and call sites. Classify
   values by UI purpose so action labels, statuses, errors, roles, plurals,
   placeholders, and rich-text fragments are translated appropriately.
3. Add `ar-SA` and `th-TH` bundles with full key parity, register metadata,
   and regenerate derived key types or other generated surfaces.
4. Add direction handling for Arabic, preserving LTR treatment where required
   for numbers, code, URLs, email addresses, and technical content. Check
   long Arabic/Thai labels in shared buttons, tables, dialogs, navigation, and
   mobile layouts.
5. Add regression coverage for locale registration, fallback/selection,
   placeholder parity, direction, and any newly discovered unlocalized
   user-visible path. Run focused checks first, then broader frontend,
   backend, harness, and translation checks.

## Concrete Steps

- [x] Inspect `src/i18n/locales.json`, all namespaces, and locale selection paths.
- [x] Search production code for hardcoded user-visible Chinese/English strings and locale-specific assumptions.
- [x] Map shared translation keys to rendering functions and formatting rules.
- [x] Create Arabic and Thai locale directories and translate every required key.
- [x] Register locale labels, fallback rules, and language picker entries.
- [x] Add document `lang`/`dir` synchronization and targeted RTL CSS or component adjustments.
- [x] Regenerate `i18n-keys.d.ts` and any locale metadata generated by repository scripts.
- [x] Add/update tests and run translation, usage, type, lint, frontend, backend, harness, and architecture checks as applicable.
- [x] Review the final diff for scope, placeholder stability, JSON validity, and accidental changes to source/technical text.

## Validation and Acceptance

The feature is accepted when:

- Both locales appear in the supported-language metadata and are selectable through the real product language flow.
- Shared locale files have complete key/file parity and pass ICU placeholder validation.
- Backend and Cook Web resolve the new locales through the existing shared source and fall back safely for unsupported or missing values.
- Arabic pages set the correct language/direction semantics without reversing code, URLs, numeric inputs, or embedded course content.
- Thai and Arabic labels render without obvious clipping or broken action ordering in the touched shared layouts.
- `python3 scripts/check_translations.py`, `python3 scripts/check_translation_usage.py --fail-on-unused`, generated-key checks, focused tests, and relevant type/lint/build checks pass.
- `git diff --check`, repository harness checks, and architecture-boundary checks pass. `python3 scripts/check_dev_tools.py` passes except for the environment's missing exact `ruff 0.16.3`; the installed global Ruff is `0.16.4`.

Recorded verification: Cook Web full Jest passed with 166 suites and 1,324
tests; `npm run type-check` and `npm run build` passed; the focused backend
i18n, billing-contract, language-context, and learner-language tests passed;
translation parity/usage, architecture, harness, JSON, formatting, and
whitespace checks passed.

## Idempotence and Recovery

All locale additions are additive and can be rerun by regenerating derived
metadata/key types. If translation generation or validation fails, preserve the
source JSON files, inspect the first reported key/file mismatch, and rerun the
generator after correcting the source. Do not overwrite existing environment
files or discard unrelated worktree changes.

## Interfaces and Dependencies

- `src/i18n/locales.json` is the shared locale/namespace contract.
- JSON locale bundles are consumed by both backend and frontend loaders.
- `src/cook-web/src/i18n.ts` and `src/cook-web/src/lib/unified-i18n-backend.ts` define frontend loading/fallback behavior.
- `src/cook-web/src/types/i18n-keys.d.ts` is generated from locale keys and must not drift from the source bundles.
- ICU/i18next formatting, React `Trans` content, and MarkdownFlow interaction syntax impose placeholder and token-preservation constraints.
- Browser/CSS direction support may affect shared layout components, tables, icons, and third-party editor/player surfaces.

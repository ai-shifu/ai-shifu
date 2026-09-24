# Spanish (Spain) Product Localization

## Purpose / Big Picture

Add `es-ES` as a selectable product language. A learner or teacher who chooses Spanish should receive Spanish application copy, API messages, and locale-aware formatting without losing existing language behavior. With the currently selected stable `markdown-flow-ui@0.2.27`, embedded component controls use English until a Spanish-capable release is available.

## Progress

- [x] 2026-09-24 06:31 CST: Fetched `origin/main`, created `sunner/add-es-es-locale`, and inspected the shared i18n contract and locale inventory.
- [x] 2026-09-24: Translated and checked all 58 shared JSON files (57 namespaces) against the Chinese source and their call sites.
- [x] 2026-09-24: Wired `es-ES` through frontend, backend, and legal URL configuration; prepared the native MarkdownFlow locale in [markdown-flow-ui PR #245](https://github.com/ai-shifu/markdown-flow-ui/pull/245).
- [x] 2026-09-24: Previously validated translation parity and usage, focused backend/frontend tests, architecture boundaries, repository harness, MarkdownFlow browser smoke, and the frontend production build against `markdown-flow-ui@0.2.28-dev.1`.
- [x] 2026-09-24: Opened [AI-Shifu PR #2942](https://github.com/ai-shifu/ai-shifu/pull/2942) for review with the development-package merge blocker called out.
- [x] 2026-09-24: Pinned stable `markdown-flow-ui@0.2.27` in Cook Web and the Arena, routed embedded controls to English, and verified both installed packages, frontend tests and build, and Arena browser smoke.
- [x] 2026-09-24: Added a separate known output-language field for built-in guide courses, stopped inferring document language from the interface, and added a language-selection analytics contract.

## Surprises & Discoveries

- The shared inventory has 58 JSON files per locale and roughly 4,200 user-facing strings.
- The currently pinned `markdown-flow-ui@0.2.27` exposes only five built-in locales and falls back to English for `es-ES`. This dependency needs a Spanish release before the embedded UI can be fully localized.
- Its content components derive HTML `lang` from the control locale unless supplied separately. The English guide must explicitly use `lang=en-US` under a Spanish interface; content without a known language uses `lang=""` to avoid an incorrect English fallback.
- The component repository requires explicit human confirmation of the exact version, source branch, and full commit SHA before publishing a stable npm release. Its development package `0.2.28-dev.1` verified native Spanish controls but cannot be merged into AI-Shifu `main`.
- The built-in guide course has Chinese and English authored variants only; Spanish users receive the English guide course until a Spanish course is authored separately.

## Decision Log

- 2026-09-24: Add Spain Spanish as the single requested locale. Do not add Latin American variants in this change.
- 2026-09-24: Preserve existing translation keys, ICU argument names, markup, technical identifiers, and course data. Translate user-facing values from Chinese with usage context.
- 2026-09-24: The user deferred the formal `markdown-flow-ui@0.2.28` release. Keep the AI-Shifu feature branch on the validated development package until a stable package is published and pinned.
- 2026-09-24: The user subsequently requested an AI-Shifu PR now. Open a ready review PR and state that its release-pin check is expected to fail; do not merge while the development pin remains.
- 2026-09-24: The user then chose the existing stable `markdown-flow-ui@0.2.27` for this PR. Keep Spanish application localization, with English embedded controls as a documented temporary limitation; do not publish the component as part of this change.

## Product Analytics Contract: Language Selection

- Business question: among deliberate language selections, how often is Spanish chosen, and on which entry surface? This informs whether to prioritize Spanish copy improvements and where to make language switching easier to find.
- Metric definition: weekly count of `user_language_selected` events with `selected_locale=es-ES`, divided by the weekly count of all `user_language_selected` events; segment both counts by `surface`. This is a share of deliberate selections, not a conversion rate from eligible views or a count of successfully persisted preferences.
- Event: `user_language_selected`.
- Actor and surface: any guest, learner, or teacher using the login selector (`login`), learner menu (`learner_menu`), or admin menu (`admin_menu`). Learner preview is included when its menu is shown. Internal and test traffic is not filtered by the producer; consumers must apply their existing traffic filters or state this limitation.
- Trigger: once in `LanguageSelect.onValueChange` when the user chooses a supported locale different from the selector's current value, before changing the interface language. Browser detection, account preference hydration, and a selection of the current locale are excluded.
- Count unit and deduplication: one accepted selector change. There is no persisted or session-wide deduplication; later deliberate changes count again. The current-value guard and in-flight target guard prevent same-language and rapid repeat selections from counting. A failed language change releases its in-flight guard for a retry.
- Correlation and privacy: no resource or user ID is attached. `selected_locale` is checked against the supported-locale inventory and `surface` is a fixed enum; the shared tracking path handles identity separately. No labels, text, URLs, or errors are included.
- Consumers: aggregate weekly language-selection report by selected locale and surface. No checked-in query or dashboard consumes this new event; it is additive and does not change historical event meanings.
- Verification: focused selector tests cover exact event name and payload, Spanish and other locales, all three surfaces, automatic/duplicate/unsupported selection exclusions, retry after a failed language change, and synchronous or asynchronous tracking failure without changing the selected language.

| Field             | Type   | Allowed values                               | Cardinality | Privacy class     | Why required                         |
| ----------------- | ------ | -------------------------------------------- | ----------- | ----------------- | ------------------------------------ |
| `selected_locale` | string | supported codes from `src/i18n/locales.json` | low         | non-personal enum | compare Spanish with other languages |
| `surface`         | string | `login`, `learner_menu`, `admin_menu`        | low         | non-personal enum | compare entry points                 |

## Outcomes & Retrospective

All 58 locale files and the application wiring are implemented. AI-Shifu PR #2942 is open for review. The earlier development package demonstrated native Spanish component text in a browser; this PR now uses stable `0.2.27`, which displays embedded controls in English. Built-in guide content uses its known output language; other content remains unmarked when its language is unknown. A future stable Spanish-capable MarkdownFlow release can remove the control fallback.

## Context and Orientation

`src/i18n/locales.json` declares supported locales. Files under `src/i18n/<locale>/` serve both Flask API and Next.js. `docs/references/i18n.md` describes parity and ICU checks. `src/web/src/lib/markdown-flow-locale.ts` bridges the product locale into `markdown-flow-ui`.

## Plan of Work

1. Create all `src/i18n/es-ES/**/*.json` files, retaining the existing structure and translating every user-visible value.
2. Register the locale and update explicit locale unions, allowlists, legal URL configuration, and any other runtime surface that consumes the list.
3. Add focused tests for language selection, API acceptance, and embedded MarkdownFlow locale handling.
4. Pin the existing stable MarkdownFlow release and map Spanish to its English control locale while keeping authored content language separate; verify the installed package behavior in this product.
5. Run translation parity/usage checks, focused tests, type checks, lint, build, and required commit gates. Review the changed copy for untranslated Chinese, unintended English fallbacks, and ICU errors.

## Concrete Steps

Work from the clean branch based on current `origin/main`. Keep translated file ownership disjoint while editing in parallel. After all files land, run `python3 scripts/check_translations.py` and `python3 scripts/check_translation_usage.py --fail-on-unused`; regenerate metadata with `python3 scripts/generate_languages.py`. Run the relevant frontend Jest and backend pytest targets, then wider checks as required by changed shared contracts.

## Validation and Acceptance

The language menu offers Español (`es-ES`), browser and saved preferences resolve to it, API messages and localizable billing content render Spanish, and switching to Spanish keeps HTML direction LTR. Every locale file and key matches the existing inventory and ICU placeholders are valid. The English built-in guide retains `lang=en-US` under a Spanish interface; MarkdownFlow content without known language uses `lang=""`, while controls from stable `0.2.27` use English. No locale-specific legal URL or page silently presents itself as a Spanish legal translation.

## Idempotence and Recovery

Translation file generation and metadata generation are deterministic. Re-running validation must not change source locales. The embedded UI fallback is explicit and covered by tests until a Spanish-capable stable component release is selected.

## Interfaces and Dependencies

- `src/i18n/locales.json` and `src/i18n/es-ES/**`
- Flask i18n, user-language validation, billing DTOs and localized URL maps
- Next.js locale selection, legal URL types, MarkdownFlow locale bridge
- `markdown-flow-ui@0.2.27` stable package pin and English embedded-control fallback

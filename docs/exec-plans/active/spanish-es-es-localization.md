# Spanish (Spain) Product Localization

## Purpose / Big Picture

Add `es-ES` as a selectable product language. A learner or teacher who chooses Spanish should receive Spanish application copy, API messages, locale-aware formatting, and native Spanish MarkdownFlow controls without losing existing language behavior. The product uses the published `markdown-flow-ui@0.2.29` release.

## Progress

- [x] 2026-09-24 06:31 CST: Fetched `origin/main`, created `sunner/add-es-es-locale`, and inspected the shared i18n contract and locale inventory.
- [x] 2026-09-24: Translated and checked all 58 shared JSON files (57 namespaces) against the Chinese source and their call sites.
- [x] 2026-09-24: Wired `es-ES` through frontend, backend, and legal URL configuration; prepared the native MarkdownFlow locale in [markdown-flow-ui PR #245](https://github.com/ai-shifu/markdown-flow-ui/pull/245).
- [x] 2026-09-24: Previously validated translation parity and usage, focused backend/frontend tests, architecture boundaries, repository harness, MarkdownFlow browser smoke, and the frontend production build against `markdown-flow-ui@0.2.28-dev.1`.
- [x] 2026-09-24: Opened [AI-Shifu PR #2942](https://github.com/ai-shifu/ai-shifu/pull/2942) for review with the development-package merge blocker called out.
- [x] 2026-09-24: Pinned stable `markdown-flow-ui@0.2.27` in Cook Web and the Arena, routed embedded controls to English, and verified both installed packages, frontend tests and build, and Arena browser smoke.
- [x] 2026-09-24: Added a separate known output-language field for built-in guide courses, stopped inferring document language from the interface, and added a language-selection analytics contract.
- [x] 2026-09-24: Rebased onto `main`, which pins published `markdown-flow-ui@0.2.29`; updated Cook Web and the Arena to pass `es-ES` through to its native Spanish controls. The published npm archive was checked for the six product-supported locales, and [markdown-flow-ui PR #245](https://github.com/ai-shifu/markdown-flow-ui/pull/245) has merged.
- [x] 2026-09-24: Revalidated native Spanish controls with focused tests and Chrome browser smoke against the rebased `0.2.29` integration.
- [x] 2026-09-24: Confirmed the rebased frontend production build against published `0.2.29`.
- [ ] 2026-09-24: Confirm PR checks after pushing the rebased branch.

## Surprises & Discoveries

- The shared inventory has 58 JSON files per locale and roughly 4,200 user-facing strings.
- The earlier `markdown-flow-ui@0.2.27` pin exposed only five built-in locales and fell back to English for `es-ES`. Published `0.2.29` includes native Spanish among the six product-supported locales, so the host now passes `es-ES` through directly.
- MarkdownFlow content components derive HTML `lang` from the control locale unless supplied separately. The English guide must explicitly use `lang=en-US` under a Spanish interface; content without a known language uses `lang=""` to avoid incorrectly marking authored content as Spanish.
- The component repository required explicit human confirmation of the exact version, source branch, and full commit SHA before publishing a stable npm release. Its development package `0.2.28-dev.1` previously verified native Spanish controls; the current integration uses the published `0.2.29` release from merged PR #245.
- The built-in guide course has Chinese and English authored variants only; Spanish users receive the English guide course until a Spanish course is authored separately.

## Decision Log

- 2026-09-24: Add Spain Spanish as the single requested locale. Do not add Latin American variants in this change.
- 2026-09-24: Preserve existing translation keys, ICU argument names, markup, technical identifiers, and course data. Translate user-facing values from Chinese with usage context.
- 2026-09-24: The user deferred the formal `markdown-flow-ui@0.2.28` release. The development package remained a temporary validation pin while no stable Spanish-capable package was available.
- 2026-09-24: The user subsequently requested an AI-Shifu PR before that stable release. The ready review PR documented the development-pin merge blocker at that time.
- 2026-09-24: The user then chose the existing stable `markdown-flow-ui@0.2.27` for this PR. The branch temporarily kept Spanish application localization with English embedded controls.
- 2026-09-24: After `main` adopted published `markdown-flow-ui@0.2.29`, the user chose `0.2.29` for the rebased PR. Keep the interactive-option escaping fix from `main` and use native Spanish embedded controls; authored guide content language remains independent of the interface locale.

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

All 58 locale files and the application wiring are implemented. AI-Shifu PR #2942 is open for review. The earlier development package demonstrated native Spanish component text in a browser; the rebased PR now selects published `0.2.29` and passes `es-ES` to embedded controls. Focused tests, Chrome browser smoke, and the frontend production build pass. Built-in guide content uses its known output language; other content remains unmarked when its language is unknown. PR checks remain to be confirmed after pushing the rebased branch.

## Context and Orientation

`src/i18n/locales.json` declares supported locales. Files under `src/i18n/<locale>/` serve both Flask API and Next.js. `docs/references/i18n.md` describes parity and ICU checks. `src/web/src/lib/markdown-flow-locale.ts` bridges the product locale into `markdown-flow-ui`.

## Plan of Work

1. Create all `src/i18n/es-ES/**/*.json` files, retaining the existing structure and translating every user-visible value.
2. Register the locale and update explicit locale unions, allowlists, legal URL configuration, and any other runtime surface that consumes the list.
3. Add focused tests for language selection, API acceptance, and embedded MarkdownFlow locale handling.
4. Pin published `markdown-flow-ui@0.2.29` in Cook Web and the Arena, pass Spanish to its native control locale, and keep authored content language separate; verify the installed package behavior in this product.
5. Run translation parity/usage checks, focused tests (including Spanish MarkdownFlow controls and the independent content `lang`), type checks, lint, build, Arena browser smoke, and required commit gates. Review the changed copy for untranslated Chinese, unintended English fallbacks, and ICU errors.

## Concrete Steps

Work from the feature branch rebased onto current `origin/main`. Keep translated file ownership disjoint while editing in parallel. After all files land, run `python3 scripts/check_translations.py` and `python3 scripts/check_translation_usage.py --fail-on-unused`; regenerate metadata with `python3 scripts/generate_languages.py`. Verify both package pins and the installed `0.2.29` locale behavior, then run the relevant frontend Jest, backend pytest, Arena browser smoke, and wider checks required by changed shared contracts.

## Validation and Acceptance

The language menu offers Español (`es-ES`), browser and saved preferences resolve to it, API messages and localizable billing content render Spanish, and switching to Spanish keeps HTML direction LTR. Every locale file and key matches the existing inventory and ICU placeholders are valid. The English built-in guide retains `lang=en-US` under a Spanish interface; MarkdownFlow content without known language uses `lang=""`, while controls from published `0.2.29` render in Spanish. Focused tests and Arena browser smoke confirm the native Spanish controls without changing the authored content language. No locale-specific legal URL or page silently presents itself as a Spanish legal translation.

## Idempotence and Recovery

Translation file generation and metadata generation are deterministic. Re-running validation must not change source locales. The Spanish control locale is passed directly to the published component release; tests must protect this mapping and the independent authored-content language.

## Interfaces and Dependencies

- `src/i18n/locales.json` and `src/i18n/es-ES/**`
- Flask i18n, user-language validation, billing DTOs and localized URL maps
- Next.js locale selection, legal URL types, MarkdownFlow locale bridge
- `markdown-flow-ui@0.2.29` published package pin in Cook Web and the Arena, with native `es-ES` embedded controls

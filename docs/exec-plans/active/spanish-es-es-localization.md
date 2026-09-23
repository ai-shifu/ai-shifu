# Spanish (Spain) Product Localization

## Purpose / Big Picture

Add `es-ES` as a complete selectable product language. A learner or teacher who chooses Spanish should receive Spanish application copy, API messages, and locale-aware formatting without losing existing language behavior.

## Progress

- [x] 2026-09-24 06:31 CST: Fetched `origin/main`, created `sunner/add-es-es-locale`, and inspected the shared i18n contract and locale inventory.
- [x] 2026-09-24: Translated and checked all 58 shared JSON namespaces against the Chinese source and their call sites.
- [x] 2026-09-24: Wired `es-ES` through frontend, backend, legal URL configuration, and the native MarkdownFlow locale in [markdown-flow-ui PR #245](https://github.com/ai-shifu/markdown-flow-ui/pull/245).
- [x] 2026-09-24: Validated translation parity and usage, focused backend/frontend tests, architecture boundaries, repository harness, MarkdownFlow browser smoke, and the frontend production build against `markdown-flow-ui@0.2.28-dev.1`.
- [ ] 2026-09-24: After explicit formal-release confirmation required by the component repository, publish the stable MarkdownFlow package, replace both development pins, rerun install/build checks, and open the AI-Shifu pull request.

## Surprises & Discoveries

- The shared inventory has 58 JSON files per locale and roughly 4,200 user-facing strings.
- The currently pinned `markdown-flow-ui@0.2.27` exposes only five built-in locales and falls back to English for `es-ES`. This dependency needs a Spanish release before the embedded UI can be fully localized.
- The component repository requires explicit human confirmation of the exact version, source branch, and full commit SHA before publishing a stable npm release. Its development package `0.2.28-dev.1` verified the product integration but cannot be merged into `main`.
- The built-in guide course has Chinese and English authored variants only; Spanish users receive the English guide course until a Spanish course is authored separately.

## Decision Log

- 2026-09-24: Add Spain Spanish as the single requested locale. Do not add Latin American variants in this change.
- 2026-09-24: Preserve existing translation keys, ICU argument names, markup, technical identifiers, and course data. Translate user-facing values from Chinese with usage context.

## Outcomes & Retrospective

All 58 locale files and the application wiring are implemented. The development package passes local frontend build and focused tests, and the Arena confirms native Spanish component text in a browser. The remaining delivery step is the stable MarkdownFlow release and replacement of both development dependency pins, followed by the AI-Shifu pull request.

## Context and Orientation

`src/i18n/locales.json` declares supported locales. Files under `src/i18n/<locale>/` serve both Flask API and Next.js. `docs/references/i18n.md` describes parity and ICU checks. `src/web/src/lib/markdown-flow-locale.ts` bridges the product locale into `markdown-flow-ui`.

## Plan of Work

1. Create all `src/i18n/es-ES/**/*.json` files, retaining the existing structure and translating every user-visible value.
2. Register the locale and update explicit locale unions, allowlists, legal URL configuration, and any other runtime surface that consumes the list.
3. Add focused tests for language selection, API acceptance, and embedded MarkdownFlow locale handling.
4. Resolve the MarkdownFlow dependency limitation using the library's native locale path, then verify the installed package behavior in this product.
5. Run translation parity/usage checks, focused tests, type checks, lint, build, and required commit gates. Review the changed copy for untranslated Chinese, unintended English fallbacks, and ICU errors.

## Concrete Steps

Work from the clean branch based on current `origin/main`. Keep translated file ownership disjoint while editing in parallel. After all files land, run `python3 scripts/check_translations.py` and `python3 scripts/check_translation_usage.py --fail-on-unused`; regenerate metadata with `python3 scripts/generate_languages.py`. Run the relevant frontend Jest and backend pytest targets, then wider checks as required by changed shared contracts.

## Validation and Acceptance

The language menu offers Español (`es-ES`), browser and saved preferences resolve to it, API messages and localizable billing content render Spanish, and switching to Spanish keeps HTML direction LTR. Every locale file and key matches the existing inventory, ICU placeholders are valid, and MarkdownFlow controls render in Spanish. No locale-specific legal URL or page silently presents itself as a Spanish legal translation.

## Idempotence and Recovery

Translation file generation and metadata generation are deterministic. Re-running validation must not change source locales. If a dependency release is unavailable, retain the branch and document the exact embedded UI fallback before publishing the feature.

## Interfaces and Dependencies

- `src/i18n/locales.json` and `src/i18n/es-ES/**`
- Flask i18n, user-language validation, billing DTOs and localized URL maps
- Next.js locale selection, legal URL types, MarkdownFlow locale bridge
- `markdown-flow-ui` native locale support and package pin

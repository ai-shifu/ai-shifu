# I18n Refactor Tasks

## Workflow Expectations
- [ ] After completing any chunk of work, create the smallest reasonable atomic commit.
- [ ] Commit promptly so progress is captured incrementally and reviewable.
- [ ] Keep the working tree clean by staging, committing, or discarding leftovers before starting the next task.

## Phase 0 – Decisions
- [x] Lock unified key naming convention across API and Cook Web (flat `MODULE.KEY` vs nested)
- [x] Adopt ICU MessageFormat for placeholders and confirm runtime libraries (front-end `i18next` + `i18next-icu` or `FormatJS`; back-end Babel/MessageFormat)
- [x] Decide how Cook Web obtains shared JSON (build-time copy, runtime proxy, or static serving)
- [x] Choose the authoritative source for locale metadata (supported list, default) and consumption pattern
- [x] Agree on migration sequencing and rollback strategy (parallel loaders vs big bang)

## Phase 1 – Migration MVP

### Repository Structure
- [x] Create `src/i18n/` with locale subfolders (`src/i18n/en-US`, `src/i18n/zh-CN`, ...)
- [x] Split translations by business domain JSON (e.g. `order.json`, `common.json`)
- [x] Move Cook Web `public/locales/*.json` content and language metadata into the new structure
- [x] Convert API-side Python translation modules under `src/api/flaskr/i18n/<locale>/` into JSON and retire the old files once references are updated

### Backend (API)
- [x] Update `src/api/flaskr/i18n/__init__.py` loader to consume JSON from `src/i18n/<lang>/`
- [x] Keep `_`, `set_language`, `get_i18n_list` APIs stable while reading the new data format
- [x] Replace direct Python constants with the new keys (e.g. `src/api/flaskr/service/order/consts.py`)
- [x] Add startup validation to catch malformed JSON or duplicate keys and surface actionable errors
- [x] Run `python scripts/list_python_i18n_modules.py` to track remaining Python-defined translations and migrate them to shared JSON
- [ ] Add/adjust unit tests covering translation loading and language selection

### Cook Web
- [x] Refactor `src/cook-web/src/i18n.ts` to read supported locales/fallback from the unified metadata
- [x] Configure i18next HTTP backend to fetch modular JSON (`/api/i18n?lng={lng}&ns={ns}`) instead of `public/locales` bundles
- [x] Ensure build/runtime pipeline exposes `src/i18n` assets to Next.js (copy step, API route, or shared package)
- [ ] Run regression checks so components still resolve translations; update keys where necessary
- [ ] Add automated tests or integration checks for language detection and loading

### Docker & Environment Parity
- [x] During image builds, `COPY src/i18n ./src/i18n` (and any equivalent path) into each service image so runtime code reads the same files as local dev.
- [x] Keep loaders identical between dev and containers—Flask should resolve JSON from `src/i18n/<lang>/<namespace>.json`, and Cook Web should serve them via the new API bridge in both environments.
- [x] Add a lightweight startup check (script or import-time assertion) that fails fast if `src/i18n` is missing so build and dev inconsistencies surface immediately.

### Validation & Tooling (MVP)
- [ ] Implement a shared CLI (e.g. `scripts/check_translations.py`) that validates JSON schema and ensures key parity across locales/modules
- [ ] Wire the CLI into pre-commit and one GitHub Action workflow to gate commits/PRs
- [ ] Document how to run the checks locally and interpret failures

### Documentation
- [ ] Update developer docs (e.g. `AGENTS.md`) with the new directory layout and workflow
- [ ] Publish a short migration playbook instructing how to add/modify translations under the new system

## Phase 2 – Enhancements

### Repository & Runtime Enhancements
- [ ] Add a pseudo-locale (e.g. `qps-ploc`) for visual QA and truncation detection
- [ ] Generate TypeScript definitions from `src/i18n` for key autocompletion (`src/cook-web/src/types/i18n-keys.d.ts`)
- [ ] Introduce ICU formatting helpers server-side (Babel) and ensure API responses use them consistently
- [ ] Enable `i18next-icu` (or chosen alternative) in Cook Web to match server formatting features

### Key Standardization
- [ ] Inventory existing i18n keys across API, Cook Web, and legacy modules to identify duplicates and inconsistencies.
- [ ] Finalize and document the canonical key naming rules (namespacing, separators, casing) for every surface.
- [ ] Provide tooling or scripts to migrate legacy keys to the approved convention.
- [ ] Update translation JSON and code references to the standardized keys and validate lookups end-to-end.

### Observability & Quality Gates
- [ ] Extend the CLI with ICU placeholder validation, unused-key detection, and duplicate key checks
- [ ] Add lint rules to block hardcoded non-i18n user-facing strings (ESLint for front-end, Flake8/pytest or grep hook for backend)
- [ ] Implement missing-key logging/reporting on both API and Cook Web (with sampling to avoid noise)
- [ ] Consider smoke tests that load every namespace via API/Cook Web runtimes to catch runtime parsing issues

### Documentation & Enablement
- [ ] Document pseudo-locale usage, ICU plural/select/date/number patterns, and common pitfalls
- [ ] Provide examples for adding a new module or locale, including running validation tooling

## Optional Integrations
- [ ] Integrate with a translation platform (Weblate/Crowdin/Lokalise) and sync via CI
- [ ] Add runtime telemetry dashboards summarizing missing keys and translation coverage
- [ ] Plan RTL locale smoke tests or visual diff tooling if future locales require it

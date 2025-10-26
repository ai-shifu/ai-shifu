# Scripts Overview

This repository includes a small set of scripts focused on internationalization consistency and code quality. Here’s what each script does and when to use it.

- scripts/check_translation_usage.py
  - Scans backend (Flask) and frontends (web, cook-web) to find all translation key usages and ensures they exist in shared JSON under `src/i18n/`.
  - Options:
    - `--fail-on-unused`: exit non‑zero if there are defined keys that are not referenced anywhere (helps keep JSON clean).
  - Resilient to legacy allowlist paths and treats missing allowlists as empty.

- scripts/check_translations.py
  - Validates that every locale has the same files and JSON structure, and that values are strings.
  - Prevents shape drift between `en-US`, `zh-CN`, and the pseudo‑locale `qps-ploc`.

- scripts/create_translation_namespace.py
  - Scaffolds a new namespace across locales with the correct `__namespace__` header.
  - Use this when introducing a new i18n domain.

- scripts/generate_languages.py
  - Generates/refreshes `src/i18n/locales.json` from existing locale folders.
  - CI ensures this file stays in sync.

- scripts/generate_pseudo_locale.py
  - Builds or refreshes the pseudo‑locale (`qps-ploc`) from `en-US` for visual QA of missing/concatenated strings.

- scripts/generate_i18n_keys.js
  - Generates a TypeScript union of translation keys for Cook Web at `src/cook-web/src/types/i18n-keys.d.ts`.
  - Helps with editor autocomplete and prevents typos.

- scripts/list_python_i18n_modules.py
  - Lists Python modules expected to reference shared translations; used to keep migration checklists tidy.

- scripts/update_i18n.py
  - Batch update helper for moving keys between namespaces while preserving structure; advanced usage during large refactors.

- scripts/check_backend_hardcoded_cn.py
  - Fails if Chinese (CJK) characters are found hardcoded in backend Python. All user‑facing text must use i18n keys.

Notes
- Legacy allowlists for unused/missing translations have been removed; CI enforces clean state by default.
- See `docs/i18n.md` for the complete i18n workflow and conventions.

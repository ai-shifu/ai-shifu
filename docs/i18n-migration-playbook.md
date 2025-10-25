# I18n Migration Playbook

This playbook captures the agreed workflow for adding, modifying, and verifying translations under the unified `src/i18n` structure used by both the backend (Flask) and Cook Web (Next.js).

## Directory Structure

- Authoritative translations are stored under `src/i18n/<locale>/.../*.json`.
- Every translation file uses the JSON format with two optional helpers:
  - `__namespace__`: overrides the default inferred namespace (recommended)
  - `__flat__`: allows defining flat keys under the namespace without extra nesting

Example:

```json
{
  "__namespace__": "server.order",
  "__flat__": {
    "orderNotFound": "Order Not Found"
  }
}
```

## Add or Modify Keys

1) Choose the correct namespace and file
   - Backend business domains use `server.<domain>.*`, e.g. `server.order.*`, `server.profile.*`, etc.
   - UI components or modules on Cook Web use `component.*` / `module.*` namespaces.

2) Edit per-locale files
   - Update both locales in `src/i18n/en-US/...` and `src/i18n/zh-CN/...`.
   - Keep keys aligned across locales to maintain parity.

3) If adding a new namespace, add it to `src/i18n/locales.json`
   - Append the namespace to the `namespaces` array.
   - Do not add a new namespace unless the per-locale files exist for it.

## Validate

Run these from the repository root:

```bash
python scripts/check_translations.py
python scripts/check_translation_usage.py --fail-on-unused \
  --unused-allowlist scripts/translation_unused_allowlist.txt \
  --missing-allowlist scripts/translation_missing_allowlist.txt
```

The first script enforces JSON parity (same files and keys) across locales. The second cross-checks all usages in backend (`src/api`) and frontends (`src/web`, `src/cook-web`). Our CI and pre-commit already run both.

## Pseudo-locale (qps-ploc)

We support generating a pseudo-locale for visual QA. It helps surface truncation and layout issues by transforming strings.

1) Generate `qps-ploc` from `en-US`:

```bash
python scripts/generate_pseudo_locale.py --source en-US --target qps-ploc --overwrite
```

2) Add the locale to `src/i18n/locales.json` if desired:

```json
{
  "default": "en-US",
  "locales": {
    "en-US": { "label": "English" },
    "zh-CN": { "label": "中文" },
    "qps-ploc": { "label": "Pseudo" }
  }
}
```

3) Validate parity and usage as usual.

## TypeScript key generation (Cook Web)

For improved developer ergonomics in `src/cook-web`, generate a union type of available translation keys:

```bash
node scripts/generate_i18n_keys.js
```

This produces `src/cook-web/src/types/i18n-keys.d.ts` with:

```ts
export type I18nKey = 'server.order.orderNotFound' | 'server.profile.nickname' | ...;
```

You can import `I18nKey` in Cook Web code for stronger typing of translation calls.

## ICU MessageFormat (Cook Web)

Cook Web enables the `i18next-icu` plugin to support advanced formatting, aligning with server-side capabilities.

- Use ICU syntax in JSON, for example:

```json
{
  "__namespace__": "module.example",
  "__flat__": {
    "files": "You have {count, plural, =0 {no files} one {# file} other {# files}}.",
    "due": "Due on {ts, date, medium} at {ts, time, short}"
  }
}
```

- No extra setup is required; ICU is enabled in `src/cook-web/src/i18n.ts` via:

```ts
import ICU from 'i18next-icu';
i18n.use(ICU());
```

Tip: prefer ICU for plural, select, and date/number formatting to keep parity with backend behavior.

## Conventions

- Use English for code comments and keys; user-facing strings live only in JSON.
- Keep keys flat and semantic (e.g., `server.profile.profileKeyRequired`).
- Do not add `module.backend.*` keys—use `server.*` namespaces.

## CI / Pre-commit Checks

- The following run automatically in CI and pre-commit:
  - JSON parity check
  - Translation usage check (no missing, no unused)
  - ESLint and formatting
  - Backend guard against hardcoded CJK in Python routes

## Troubleshooting

- Parity failures: ensure both locales define the same files and keys.
- Missing keys: confirm the namespace is declared in `locales.json` and the keys exist in both locales.
- Unused keys: remove them or confirm they’ll be used imminently.

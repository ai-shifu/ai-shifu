# I18n Key Naming Standard

This document standardizes how we name translation keys across API and frontends to ensure consistency and maintainability.

## Namespaces

- server.<domain>[.<subdomain>].<key>
  - Backend business and error messages (e.g., `server.user.invalidToken`, `server.order.courseNotPaid`).
- module.<feature>[.<subfeature>].<key>
  - Frontend module UIs and flows (e.g., `module.chat.copySuccess`, `module.auth.getOtp`).
- component.<name>[.<part>].<key>
  - Reusable UI components (e.g., `component.header.title`, `component.fileUploader.dropHint`).
- common.core|errors|language
  - Shared cross-cutting strings (e.g., `common.core.submit`, `common.errors.noPermission`).

Use `src/i18n/locales.json` to register namespaces that are intended to be served to the frontends.

## Key Style

- Use dot-separated segments; do not use underscores.
- Segment case: lowerCamelCase for keys, lowercase for namespace segments.
- Keep keys short but descriptive (avoid unnecessary abbreviations).
- Prefer positive, action-oriented names (e.g., `requestSuccess`, not `requestOk`).

## ICU MessageFormat

- Prefer ICU for placeholders and plurals to align API and frontends.
  - Variables: `Hello, {name}`
  - Plural: `{count, plural, one {# item} other {# items}}`
- Variable names must match across locales for the same key.
- Avoid positional placeholders; always use named variables.

## Do’s and Don’ts

- Do keep keys consistent across locales and files.
- Do co-locate related keys in the same namespace file.
- Don’t hardcode user-facing strings in code; always use an i18n key.
- Don’t use mixed languages for keys; English only.

## Examples

- `server.profile.nicknameNotAllowed`
- `module.chat.invalidSmsCode`
- `component.navigation.toggle`
- `common.errors.unauthorized`

## Migration Guidance

- Use `scripts/create_translation_namespace.py` to create a new namespace skeleton.
- Use `scripts/update_i18n.py` to backfill missing keys or prune unused keys.
- Run `scripts/check_translations.py` and `scripts/check_translation_usage.py` locally (or via pre-commit) to validate.

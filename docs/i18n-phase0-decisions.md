# I18n Phase 0 Decisions

These decisions align the repository with the Phase 0 tasks in `tasks.md` and unblock the move toward a unified translation workflow.

## Unified Key Naming Convention
- **Decision**: Use lowercase, dot-delimited keys (`domain.feature.message`) across all runtimes.
- **Rationale**:
  - Works natively with i18next (`keySeparator='.'`) and can be consumed by Flask by returning the dotted key literally.
  - Keeps parity with current Cook Web namespaces while avoiding uppercase constants from the Python modules.
  - Encourages predictable merging because every key is a single string entry in JSON.

## Placeholder & Formatting Strategy
- **Decision**: Adopt ICU MessageFormat placeholders (`{count, plural, ...}`) everywhere.
- **Runtime Libraries**:
  - Cook Web: `i18next-icu` plugin (SSR-compatible) for Next.js.
  - Backend: Babel with `messageformat` support via `flask-babel` utilities (or a lightweight helper around `babel.messages`), so API responses render the same plural/date/number forms.
- **Follow-up**: Add lint/validation to ensure placeholders exist in every locale and match the ICU schema.

## Shared JSON Distribution
- **Decision**: Store canonical translation JSON under `src/i18n/<locale>/<namespace>.json`.
- **Cook Web Access**:
  - Expose `src/i18n` through a lightweight Next.js `app/api/i18n/[lng]/[ns]/route.ts` file system bridge.
  - The Next.js build copies nothing; instead, the API route streams JSON directly from the shared directory so dev and prod stay in sync.
- **API Access**:
  - Backend loader reads the same JSON files from the filesystem (no module imports) at application boot, caching them in memory.

## Locale Metadata Source
- **Decision**: Author the locale list and defaults in `src/i18n/locales.json` with shape:
  ```json
  {
    "default": "en-US",
    "locales": {
      "en-US": { "label": "English", "rtl": false },
      "zh-CN": { "label": "中文", "rtl": false }
    }
  }
  ```
- **Consumers**:
  - Cook Web reads this file during Next.js runtime (server components) and injects it into the HTTP backend configuration.
  - Backend exposes the same metadata via `GET /i18n/locales` for other clients.
  - Future tooling (CLI validation) relies on this single source of truth.

## Migration Sequencing & Rollback
- **Sequencing**:
  1. Create `src/i18n` structure and copy existing Cook Web JSON (namespaced per domain) and locale metadata.
  2. Update Cook Web to load JSON through the new API route while keeping legacy bundles as a fallback.
  3. Convert backend Python modules into JSON namespaces, reusing the same keys.
  4. Remove legacy files once parity tests pass.
- **Rollback Plan**:
  - Each step lands in atomic commits so we can revert to the previous revision without affecting other services.
  - Keep legacy loaders (Python modules and `public/locales/*.json`) until the new path is fully validated; toggling an environment flag (e.g., `USE_LEGACY_I18N`) allows quick fallback during deployment.
  - CLI validation targets both storages during transition, so a regression in new JSON fails fast before rollout.

## Immediate Action Items
- Scaffold the shared `src/i18n` directory and metadata file from the decisions above.
- Implement the shared validation CLI noted in `tasks.md` so JSON schemas stay aligned.
- Draft migration documentation for contributors once the structure exists.

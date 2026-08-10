# Add arbitrary rate entries to Rate Management

## Purpose / Big Picture

Operators can add an LLM or TTS billing-rate identity from
`/admin/operations/config`, including identities that are not in the current
runtime model catalog. The page is named Rate Management in user-facing copy.
Adding a rate must not enable a model, change provider credentials, or alter any
runtime allowlist.

## Progress

- [x] 2026-08-10 09:27 CST: Inspected the existing rate page, versioned rate
  writer, model catalogs, permissions, translations, and focused tests.
- [x] 2026-08-10 09:27 CST: Locked product decisions for derived display names,
  create-only duplicate handling, and editable catalog suggestions.
- [x] 2026-08-10 10:42 CST: Implemented the backend catalog/database union,
  strict create-only validation, duplicate handling, and transactional writes.
- [x] 2026-08-10 10:42 CST: Implemented the Rate Management create dialog,
  confirmation flow, refresh, and created-row reveal behavior.
- [x] 2026-08-10 10:42 CST: Added backend/frontend coverage and aligned English,
  Chinese, and French translations.
- [x] 2026-08-10 10:42 CST: Completed focused and repository verification and
  recorded the outcome below.

## Surprises & Discoveries

- The existing POST writer already creates versioned rate rows, but the GET
  response is built only from current runtime model options, so a database-only
  identity disappears after refresh.
- `display_name` is response-only and is not stored. Database-only entries must
  derive their label from the provider/model identity.
- LLM writes treat the submitted price as the output-token price and maintain
  the input/cache/output metric relationship; TTS writes use output characters.
- French operators commonly enter a decimal comma. Multiplier normalization
  must treat `1,5` as `1.5`, not strip the comma and turn it into `15`.
- This is an operator-only, low-frequency workflow. The implementation uses the
  existing transaction directly instead of adding process-local or database
  locks for rare cross-client concurrent writes.

## Decision Log

- Keep the route `/admin/operations/config`, but rename all user-facing page
  language from Config Management to Rate Management.
- Reuse the existing GET/POST route. Extend POST with optional create-only
  semantics instead of adding another write endpoint.
- Reject duplicate active exact identities and direct operators to the existing
  edit action.
- Do not add a schema migration or a model-availability column. Explain in the
  create and confirmation dialogs that a rate entry does not enable a model.
- Keep the write path simple: rely on the existing unit of work and active-rate
  duplicate check, accepting that simultaneous writes from different clients
  are outside the guaranteed workflow.

## Outcomes & Retrospective

The page and navigation now present Rate Management while preserving the
existing route. Operators can add arbitrary LLM or TTS rate identities from the
active tab, confirm the derived credit price, and see the created entry after a
refresh. Database-only identities remain visible and editable, while the dialog
states that adding a rate does not enable a model.

The backend preserves legacy edit behavior, adds strict create-only semantics,
rejects existing exact active identities and non-finite prices, and writes
through the existing unit-of-work transaction without an additional lock layer.

Verification completed with 21 focused backend tests and 15 focused frontend
tests. Frontend type checking, focused lint/format checks, translation parity and
usage checks, backend import/format checks, architecture boundaries, unit-of-work
ratchet, repository harness, developer tooling, and `git diff --check` passed.
The full focused-file Ruff scan retains 18 pre-existing warnings and adds none.

## Context and Orientation

The frontend route is
`src/cook-web/src/app/admin/operations/config/page.tsx`. It reads and writes
`/shifu/admin/operations/config/rates`. Backend serialization and versioned
writes live in
`src/api/flaskr/service/shifu/admin_operations/config_rates.py`, with focused
coverage in `src/api/tests/service/shifu/test_admin_config_rates.py`. Shared
translations use the `module.operationsConfig` and `server.billing`
namespaces under `src/i18n/`.

## Plan of Work

1. Broaden the GET result to union current catalog rows with current active
   exact database identities, preserve catalog labels, deduplicate canonical
   identities, and synthesize provider/model labels for database-only rows.
2. Add strict create-only validation to the existing writer and a localized
   duplicate-rate business error while preserving existing edit/upsert calls.
3. Add a title action named Add Rate, an adjacent form dialog with editable
   provider/model suggestions, and a protected async confirmation step.
4. Refresh and reveal the created row after success; retain form state after
   failures and keep the existing inline edit path unchanged.
5. Add focused regression coverage, update all locales and generated i18n key
   types, and run repository checks.

## Concrete Steps

- Add helpers in the backend rate service for canonical active identities,
  database-only row serialization, strict identity validation, and create-only
  conflict detection.
- Add the next billing error code and aligned English, Chinese, and French
  translations.
- Extract reusable rate types/conversion helpers as needed and add an adjacent
  create-dialog component rather than expanding the route entry indefinitely.
- Update the page title, description context, add action, confirmation copy,
  refresh/focus behavior, and nine locale JSON files across English, French,
  and Chinese.
- Add backend service tests and frontend dialog/page tests.

## Validation and Acceptance

- A catalog model and an arbitrary provider/model identity can each be added
  from the active LLM or TTS tab.
- A database-only entry remains visible after a full GET refresh and can be
  edited with the existing row action.
- A duplicate create is rejected without closing an existing rate window or
  inserting another version.
- LLM creates maintain all three metrics; TTS creates maintain the output-char
  metric, including a provider-default empty model.
- Pending confirmation is single-flight and cannot be dismissed; failures keep
  the form available for retry.
- No model allowlist, provider credentials, or invocation configuration changes.

## Idempotence and Recovery

The active-rate precheck rejects sequential duplicate submissions, and the
frontend confirmation is single-flight. Simultaneous writes from separate
clients are intentionally not serialized for this low-frequency operator flow.
Existing edit calls remain versioned and idempotent within the current
same-second behavior. If a frontend request fails, keep the form values and allow
retry. Failed validation or commit rolls back the whole rate version.

## Interfaces and Dependencies

- GET `/shifu/admin/operations/config/rates` keeps its top-level response shape
  but may return active exact identities outside the runtime model catalog.
- POST `/shifu/admin/operations/config/rates` accepts optional
  `create_only: true`; omitted/false preserves the current edit contract.
- No new provider, environment variable, database column, or runtime model
  dependency is introduced. The already-installed transitive `decimal.js`
  10.6.0 package is promoted to a direct frontend production dependency for
  exact rate derivation.

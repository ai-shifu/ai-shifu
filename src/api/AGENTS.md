# Backend AI Collaboration Rules

This file owns backend-wide AI execution rules for the Flask API, service
modules, Alembic migrations, backend configuration, and shared backend tests.

## Scope

- Apply this file to `src/api/`, including `flaskr/`, `migrations/`, `tests/`,
  backend scripts, and backend environment workflows.

- Service-specific rules belong in `src/api/flaskr/service/<module>/AGENTS.md`.
  Keep this file focused on backend patterns shared by multiple services.

- Backend engineering conventions live in the
  [engineering baseline](../../docs/engineering-baseline.md), especially:
  [Architecture](../../docs/engineering-baseline.md#architecture),
  [Database Model Conventions](../../docs/engineering-baseline.md#database-model-conventions),
  [API Contract Baseline](../../docs/engineering-baseline.md#api-contract-baseline),
  [Testing Expectations](../../docs/engineering-baseline.md#testing-expectations),
  [Environment Configuration](../../docs/engineering-baseline.md#environment-configuration),
  and [Internationalization Rules](../../docs/engineering-baseline.md#internationalization-rules).

- Shared translation files live under `src/i18n/`, not under
  `src/api/flaskr/i18n/`, and backend code should reference them by namespace
  key.

## Do

- Inspect the owning service code, neighboring helpers, and matching pytest
  coverage before changing backend behavior so you preserve the actual current
  contract.

- Reuse existing repositories, DTOs, response envelopes, provider wrappers,
  and helper modules before introducing a new backend abstraction.

- Use `FLASK_APP=app.py` from `src/api/` for Flask commands, and update module
  imports so new models or routes participate in the app factory and migration
  discovery paths.

- Keep database models, response envelopes, auth-error behavior, migration
  workflow, and environment changes aligned with
  [docs/engineering-baseline.md](../../docs/engineering-baseline.md).

- Register new or changed environment variables in
  `src/api/flaskr/common/config.py`, then regenerate
  `docker/.env.example.full` with `python scripts/generate_env_examples.py`.

- Use shared response envelopes, error-code registration, LiteLLM integration,
  and backend i18n helpers instead of inventing per-service patterns.

## Avoid

- Do not add parallel backend helper layers when shared repositories,
  provider wrappers, or service utilities already cover the use case.

- Do not edit applied migration files. Generate a new Alembic revision and
  review it before committing any schema change.

- Do not add hard database foreign-key constraints for business-key
  relationships unless the architecture decision changes explicitly.

- Do not bypass the LiteLLM wrapper or shared backend helper layers when
  integrating new OpenAI-compatible providers or external service calls.

- Do not add primary backend translations in Python modules. Use shared JSON
  namespaces under `src/i18n/` and keep locale inventories aligned.

## Commands

- `cd src/api && FLASK_APP=app.py flask run` starts the backend dev server.

- `cd src/api && pytest -q` runs the backend test suite; narrow to
  `tests/service/<module>/` for focused verification while iterating.

- `cd src/api && FLASK_APP=app.py flask db migrate -m "message"` creates a
  migration after model changes, and `flask db upgrade` applies it.

- `cd src/api && python scripts/generate_env_examples.py` refreshes the Docker
  environment example after configuration changes.

## Tests

- Extend service tests under `src/api/tests/service/` whenever behavior, DTO
  shape, permission rules, or persistence logic changes.

- Review generated migration files in `src/api/migrations/versions/` manually
  before accepting schema changes.

- Run the shared translation checks when shared translation namespaces or backend usage change: `python scripts/check_translations.py && python scripts/check_translation_usage.py --fail-on-unused`.

- When a change touches provider calls, auth, or configuration, cover both the
  success path and the highest-risk failure path in tests or mocks.

## Related Skills

- `src/api/SKILL.md` lists backend skills and the split between durable rules
  and workflow-specific runbooks.

- `src/api/skills/shifu-authoring-flow/SKILL.md` covers backend authoring,
  history, and publish/import workflows.

- `src/api/skills/user-auth-flows/SKILL.md` covers verification codes,
  credential state, and auth-provider changes.

- `src/api/skills/gen-mdf-proxy/SKILL.md` covers the MDF proxy boundary,
  validation, and frontend/backend ownership split.

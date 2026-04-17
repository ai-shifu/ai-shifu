# Backend AI Collaboration Rules

This file routes backend work to the right source documents and keeps the
hard backend constraints close to `src/api/`.

## Scope

- Apply this file to `src/api/`, including `flaskr/`, `migrations/`, `tests/`,
  and backend scripts.
- Use `../../ARCHITECTURE.md` for the repository map and
  `../../docs/engineering-baseline.md` for the backend engineering handbook.
- Service-specific rules still live in `src/api/flaskr/service/<module>/AGENTS.md`.

## Do

- Inspect the owning service code, DTOs, helper modules, and pytest coverage
  before changing backend behavior.
- Reuse the shared response envelope with `code`, `message`, and `data`, the
  existing provider wrappers, and the shared backend helper layers.
- Keep new or changed environment variables aligned with
  `src/api/flaskr/common/config.py` and regenerate Docker env examples when
  configuration changes.
- Keep backend execution context in ExecPlans when the task is complex or
  cross-cutting.
- Use the request-id and Langfuse helpers in existing shared paths instead of
  inventing parallel diagnostics logic.

## Avoid

- Do not edit applied Alembic migrations.
- Do not add hard foreign-key constraints for business-key relationships
  unless the architectural contract changes deliberately.
- Do not bypass the LiteLLM wrapper or shared provider helpers for
  OpenAI-compatible integrations.
- Do not place backend translations in ad-hoc Python modules; use shared JSON
  namespaces under `src/i18n/`.

## Commands

- `cd src/api && FLASK_APP=app.py flask run`
- `cd src/api && pytest -q`
- `cd src/api && FLASK_APP=app.py flask db migrate -m "message"`
- `cd src/api && python scripts/harness_diagnostics.py --request-id <id>`

## Tests

- Add or update targeted pytest coverage in `src/api/tests/service/` when
  service behavior changes.
- Review generated migration files manually before accepting schema changes.
- Run broader backend tests when request flow, provider integration, or shared
  config behavior changes.

## Related Skills

- `src/api/SKILL.md`
- `src/api/skills/shifu-authoring-flow/SKILL.md`
- `src/api/skills/user-auth-flows/SKILL.md`
- `src/api/skills/gen-mdf-proxy/SKILL.md`

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
- Define the intended schema in SQLAlchemy models first, then generate schema
  revisions with `FLASK_APP=app.py flask db migrate -m "message"` and review
  the candidate migration before accepting it.
- Own database transactions with `with unit_of_work():` from
  `flaskr/dao/uow.py`: helpers add and flush but never commit or roll back,
  nested blocks join the caller, and external side effects (notifications,
  celery enqueue, cache writes, background threads) go through
  `uow.on_commit`.
- Reuse the caller's app context with `uow.app_context_scope(app)`; push
  `app.app_context()` only at real entry points (celery tasks, CLI commands),
  because a nested context switches Flask-SQLAlchemy sessions and breaks the
  caller's transaction boundary.

## Avoid

- Do not edit applied Alembic migrations.
- Do not use SQLAlchemy or Flask-SQLAlchemy `create_all()` calls, or custom
  schema-introspection guards, as a substitute for versioned Alembic
  migrations. Add a narrowly scoped guard only when a documented
  non-transactional DDL recovery requirement makes it necessary.
- Do not add hard foreign-key constraints for business-key relationships
  unless the architectural contract changes deliberately.
- Do not bypass the LiteLLM wrapper or shared provider helpers for
  OpenAI-compatible integrations.
- Do not place backend translations in ad-hoc Python modules; use shared JSON
  namespaces under `src/i18n/`.
- Do not add `db.session.commit()` or `db.session.rollback()` outside
  `flaskr/dao/`; `scripts/check_uow_commit_sites.py` only lets the
  grandfathered baseline in `docs/generated/uow-commit-baseline.json` shrink.
  Multi-step flows use one unit of work per persistence step and never span a
  generator `yield` or a provider HTTP call.

## Commands

- `cd src/api && FLASK_APP=app.py flask run`
- `cd src/api && pytest -q`
- `cd src/api && FLASK_APP=app.py flask db migrate -m "message"`
- `cd src/api && python scripts/harness_diagnostics.py --request-id <id>`
- `python scripts/check_uow_commit_sites.py` (repository root) verifies no new
  direct commit sites appeared; `--update` ratchets the baseline down after a
  migration removes sites.

## Tests

- Add or update targeted pytest coverage in `src/api/tests/service/` when
  service behavior changes.
- Pair every migration to `unit_of_work()` with a mid-flow failure test
  (pattern: `src/api/tests/service/order/test_uow_failure_paths.py`) proving
  partial writes roll back and `on_commit` side effects do not fire.
- Review generated migration files manually before accepting schema changes.
- Run broader backend tests when request flow, provider integration, or shared
  config behavior changes.

## Related Skills

- `src/api/SKILL.md`
- `src/api/skills/shifu-authoring-flow/SKILL.md`
- `src/api/skills/user-auth-flows/SKILL.md`

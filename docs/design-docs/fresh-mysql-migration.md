---
title: Fresh MySQL Migration Replay Repair
status: implemented
owner_surface: backend
last_reviewed: 2026-11-09
canonical: true
---

# Fresh MySQL Migration Replay Repair

## Context

Fresh MySQL upgrades used to fail at revision `6b603528dac8_add_system_profile.py`.
That revision depended on current profile-service helpers that no longer matched
the legacy schema. The repaired revision is self-contained, and the smoke test
replays the full Alembic history against an isolated MySQL schema.

## Historical Repair

- This repair was applied to the broken historical revision to restore fresh replay.
- Rewrite revision `6b603528dac8` to use only Alembic and SQLAlchemy Core.
- Preserve the original intent of the revision by inserting the system profile
  rows directly into the legacy tables.
- Add an automated fresh-MySQL smoke test that runs the full upgrade path in
  an isolated subprocess.

## Implementation Notes

### Historical migration repair

- Remove runtime imports from `6b603528dac8_add_system_profile.py`.
- Replace helper-driven logic with direct inserts or updates into:
  - `profile_item`
  - `profile_item_i18n`
- Make the migration idempotent by keying on `parent_id = ''`,
  `profile_key`, and i18n language.
- Keep downgrade self-contained as well by using direct SQL updates instead of
  importing removed ORM models.

### Smoke test

- Add a MySQL-only pytest smoke test under `src/api/tests/migrations/`.
- Provision a temporary schema from `TEST_SQLALCHEMY_DATABASE_URI`.
- Run `flask_migrate.upgrade("migrations")` inside a subprocess with
  `SKIP_LOAD_DOTENV=1` and runtime-only dependencies stubbed before app import.
- Assert the database reaches the current Alembic head and that a minimal set
  of current tables exists.

## Verification

Example local command:

```bash
cd src/api
RUN_MYSQL_MIGRATION_SMOKE=1 \
TEST_SQLALCHEMY_DATABASE_URI='mysql+pymysql://root:pass@127.0.0.1:33067/mysql?charset=utf8mb4' \
pytest -q tests/migrations/test_fresh_mysql_upgrade.py
```

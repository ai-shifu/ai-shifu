# Backend Service: config

This module owns persisted application configuration, encryption helpers, and
cached backend configuration access.

Entry files in this directory: `funcs.py`, `models.py`.

## Do

- Route reads and writes through the config helper functions so encryption,
  caching, and locking stay consistent.
- Preserve the contract between database-backed config values and
  environment-driven defaults in `flaskr.common.config`.
- Keep sensitive values encrypted at rest and invalidate caches when writes
  happen.

## Avoid

- Do not read or write encrypted config rows directly from unrelated services
  when helper functions already own that behavior.
- Do not add new config keys without updating env metadata or documentation
  where the value is expected.
- Do not bypass cache-key and lock-key helpers when changing config
  persistence behavior.

## Tests

`cd src/api && pytest tests/service/config/ -q`

# Backend Service: profile

This module owns profile-variable definitions, value persistence, profile
mapping, and profile route handling.

Entry files in this directory: `routes.py`, `funcs.py`, `models.py`,
`profile_manage.py`.

## Do

- Preserve the mapping between profile variables, stored values, and derived
  aggregate fields updated for users.
- Keep route payloads, DTOs, and persistence helpers in sync when profile
  definitions evolve.
- Treat profile schema and value semantics as shared data contracts used by
  authoring and runtime flows.

## Avoid

- Do not update profile values in ad-hoc code paths that bypass the
  aggregation and normalization helpers.
- Do not rename variable mappings or profile DTO fields without coordinated
  frontend and backend updates.
- Do not spread profile-definition constants across unrelated modules when
  this service already owns them.

## Tests

`cd src/api && pytest tests/service/profile/ -q`

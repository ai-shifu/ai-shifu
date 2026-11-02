# Backend Service: profile

This module owns the learner's account-backed profile fields (nickname,
language, learner profile), the learner profile and its optimizer, onboarding,
and course variable definitions (`profile_manage.py`). Course-scoped learner
memory values live in `flaskr/service/memory/`.

Entry files in this directory: `api.py`, `routes.py`, `account_fields.py`,
`learner_profile.py`, `models.py`, `profile_manage.py`.

## Do

- Preserve the mapping between system profile keys and the user entity fields
  they are stored on (`account_fields.py`).
- Keep route payloads, DTOs, and persistence helpers in sync when profile
  definitions evolve.
- Treat profile schema and value semantics as shared data contracts used by
  authoring and runtime flows.
- Export what other services need through `api.py`; the memory service reads
  account fields only from there.

## Avoid

- Do not update profile values in ad-hoc code paths that bypass the
  aggregation and normalization helpers.
- Do not rename variable mappings or profile DTO fields without coordinated
  frontend and backend updates.
- Do not import `flaskr.service.memory` from this package: memory depends on
  profile, not the other way round.
- `funcs.py`, `course_values.py`, `course_memory.py` and `course_references.py`
  here are one-release aliases of the memory service; do not add code to them
  or import them.

## Tests

`cd src/api && pytest tests/service/profile/ -q`

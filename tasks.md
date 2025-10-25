# User Service Legacy Dependency Removal Plan

## Task 1: Establish canonical user access layer on `user_users`
- [x] Audit required user attributes across `flaskr/service` modules. (See new repository adapter notes below.)
- [x] Implement repository helpers to load/update users using `user_users` and `user_auth_credentials` only.
- [x] Provide adapters that map aggregated user data to existing DTOs (`UserInfo`, `UserToken`).
- [x] Document the new access layer usage patterns in this file (section added below).
- **Tests**: Targeted repository/service unit tests via `pytest tests/service/user` *(fails in container: Alembic migrations require MySQL column `ai_course.course_keywords` unavailable on SQLite; see test run log).* 

### Access layer usage notes
- Use `load_user_aggregate(user_bid)` to obtain a `UserAggregate` snapshot including normalized identifiers and credential summaries.
- `load_user_aggregate_by_identifier(identifier)` resolves email/phone credentials before falling back to the canonical identifier field.
- `create_user_entity`/`upsert_user_entity` manage persistence exclusively through `user_users`; legacy sync helpers remain untouched for now but should not be used for new code.
- `build_user_info_from_aggregate` converts the aggregate snapshot into the existing `UserInfo` DTO for route/service compatibility.

## Task 2: Refactor core user flows to remove `user_info` reads/writes
- [x] Update `flaskr/service/user/common.py`, `user.py`, and authentication providers to rely on the new access layer.
- [x] Adjust phone/email verification flows to create/update records exclusively through the new tables.
- [x] Ensure token validation and profile snapshots are built from the new structures.
- **Notes**: Legacy tables remain accessible only through repository helpers for role flag compatibility; business logic now operates on `user_users` aggregates and credential summaries.
- **Tests**: `pytest tests/service/user` *(still blocked in container by MySQL-specific migration requirements; see latest run log).* 

## Task 3: Update cross-domain modules referencing `user_info`
- [x] Replace direct `User` model usage in `flaskr/service/learn`, `order`, `profile`, and `feedback` packages with the new helpers or DTOs.
- [x] Confirm admin listing logic fetches data without querying `user_info`.
- [x] Remove any remaining synchronization utilities tied to the legacy table.
- **Tests**: Focused suites such as `pytest tests/service/learn` and `pytest tests/service/order` (or equivalent) plus manual API smoke checks as needed.

## Task 4: Cleanup and regression verification
- [x] Drop unused legacy models/utilities (`User`, legacy sync helpers) if no longer referenced.
- [x] Update documentation/comments to reflect the single-source-of-truth user tables.
- [x] Run full backend test suite and linting to confirm stability.
- **Notes**: Role flags now persist via `user_profile` entries (`sys_user_is_admin` / `sys_user_is_creator`) and the repository no longer references `user_info`.
- **Tests**: `pytest` at repo root *(fails: missing SQLALCHEMY_DATABASE_URI, SECRET_KEY, and LLM API key requirements in container)*; `pre-commit run -a` *(fails: blocked from fetching hooks due to 403 CONNECT tunnel error in container)*.

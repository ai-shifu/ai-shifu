# User Role Flag Consolidation Plan

The refactor must shift creator role state into the canonical `user_users` table, eliminate the unused admin flag across the codebase, and land with a reviewed Alembic migration ready for deployment.

## Task 1: Schema Alignment
- [x] Review `user_users` SQLAlchemy model and related enums to confirm current columns and defaults.
- [x] Extend `user_users` model with an `is_creator` boolean column (default `False`, indexed, matches DB conventions).
- [x] Remove any lingering SQLAlchemy field definitions or metadata that still expose `is_admin`.
- [x] Verify dependent models (`UserInfo`, legacy tables) no longer rely on the admin flag.

## Task 2: Repository & Service Updates
- [ ] Refactor `UserAggregate` loading to read/write the `is_creator` flag from `user_users` instead of `user_profile`.
- [ ] Delete admin-role plumbing (`ROLE_PROFILE_KEY_ADMIN`, DTO fields, service helpers) and update callers.
- [ ] Update API serializers/DTOs to drop `is_admin` and ensure responses only expose `is_creator`.
- [ ] Audit downstream modules (`shifu`, `order`, `profile`, etc.) for admin checks and replace them with creator semantics or remove when obsolete.

## Task 3: Migration Authoring
- [ ] Draft Alembic migration adding `is_creator` to `user_users` with proper defaults, indexes, and comments.
- [ ] Backfill the new column from existing role data (e.g., `user_profile` entries) where available.
- [ ] Drop the unused `is_admin` column/constraints from legacy tables or data stores to keep schema clean.
- [ ] Provide a downgrade path and validate the script locally (`flask db upgrade`/`downgrade`).

## Task 4: Tests & Documentation
- [ ] Update unit/integration tests and fixtures to align with the new column and removed admin flag.
- [ ] Confirm API contract changes with frontend (document response shape adjustments if any).
- [ ] Run targeted `pytest` suites covering user service flows.
- [ ] Execute `pre-commit run -a` to satisfy linters and formatters.

## Task 5: PR Finalization
- [ ] Summarize schema changes and migration steps in PR description/release notes.
- [ ] Capture deployment sequencing or data-migration caveats for operations.
- [ ] Ensure no orphaned admin-profile records remain in production data snapshots (migration or follow-up script).

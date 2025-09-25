# Refactor User Management Tasks

> Each task must be completed and committed in an individual git commit.

## Discovery & Planning
- [x] Inventory legacy user tables, repository classes, and service entry points touching user data; document findings in `docs/user-refactor-notes.md`.
- [x] Confirm new SQLAlchemy models `User` and `UserAuthCredential` structure, indexes, and relationships in `src/api/flaskr/service/user/models.py`.
- [x] Map legacy authentication providers to the new provider schema (phone, email, google, facebook, apple) and note required data transformations.
- [x] Review existing DTOs and response envelopes for user endpoints to identify required updates or additions.

## Data Migration Strategy
- [x] Locate current Alembic migration history and plan a migration script to move legacy user rows into `user_users`.
- [x] Design migration logic to populate `user_auth_credentials` with provider-specific fields and raw profile persistence.
- [x] Ensure WeChat credentials migrate as two records (subject_format `open_id` and `unicon_id`, subject_id matching each value).
- [x] Draft a rollback plan for the migration to ensure safe deployment (document assumptions and limitations).

## Service Layer Refactor
- [x] Extract a shared authentication provider interface (factory contract) describing required methods (e.g., `authenticate`, `link`, `to_credential_payload`).
- [x] Refactor phone authentication service to implement the factory contract and persist credentials via `user_auth_credentials` repository functions.
- [x] Refactor email authentication service to use the factory contract, enforcing identifier uniqueness and proper DTO usage.
- [x] Update user creation/update flows to interact with the new `User` repository and detach from legacy table abstractions.
- [x] Adjust service-level DTOs and domain objects to align with the refactored persistence layer.

## Google OAuth Implementation
- [x] Add Google OAuth configuration entries to `src/api/flaskr/common/config.py`, including client ID, client secret, redirect URI, and scopes metadata.
- [x] Extend `.env.example.full` (and regenerate if required) with the new Google OAuth variables and descriptions.
- [x] Introduce Authlib Google client registration within the user auth module, wiring configuration values.
- [x] Implement a Google provider class conforming to the factory interface, returning normalized credential payloads and storing `raw_profile` JSON.
- [x] Create API routes/handlers for Google OAuth initiation and callback flow in the existing user auth blueprint, using DTOs for request/response bodies.
- [x] Ensure callback handler persists or updates `user_auth_credentials` using the Google provider implementation and links to the corresponding `User` record.

## Repository & Persistence Updates
- [x] Implement repository helpers for `User` and `UserAuthCredential` to encapsulate CRUD operations and credential lookups by provider/identifier.
- [x] Add raw profile JSON serialization/deserialization utilities consistent with current project patterns.
- [ ] Update transaction management to guarantee atomic writes when creating users with multiple credentials.

## API & DTO Adjustments
- [x] Define request/response DTOs for Google OAuth endpoints and revised email/phone flows following existing API standards.
- [ ] Update schema validation and marshmallow (or pydantic) definitions used by affected endpoints.
- [ ] Document response examples and error codes for new/updated endpoints in API docs or inline comments where appropriate.

## Testing & Validation
- [x] Add unit tests for the authentication provider factory and each provider implementation (phone, email, google).
- [ ] Write integration tests covering the Google OAuth callback handler, including raw profile persistence and user linkage.
- [ ] Add migration tests or smoke scripts verifying data transfer correctness for representative legacy rows.
- [ ] Update or create test fixtures for new configuration values and provider metadata.
- [ ] Run `pytest` suites impacted by the refactor and ensure all tests pass after changes.

## Documentation & Cleanup
- [ ] Update developer documentation detailing the new user management architecture and factory usage.
- [ ] Verify `.env.example.full` and any other generated config artifacts reflect the new variables (rerun generator if necessary).
- [ ] Perform final linting (`pre-commit run`) and code style checks prior to submitting changes.

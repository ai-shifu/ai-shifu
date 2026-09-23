# Skill Platform Attribution and Journey Events

## Purpose / Big Picture

AI Shifu must identify the AI host platform that brought a Skill user (for
example WorkBuddy, Doubao, Lobster, Codex, or a direct install), the Skill and
version used, and the user's progression from device authorization through
registration, course creation/import, and publication. The database is the
source of truth for attributable user and course paths; Umami receives only
aggregated, low-cardinality event dimensions and is never the authority for a
user or course.

This first backend PR defines and persists the contract. The following Skills
PR is the producer for `ai-shifu-course-creator`; per-platform package values
are deliberately excluded until the third rollout PR.

## Progress

- [x] 2026-09-22 11:00 CST: Created the backend branch from current `main`.
- [x] 2026-09-22 11:15 CST: Confirmed the existing device authorization flow,
  explicit `AuthResult.is_new_user` signal, course-creation entry point, and
  existing analytics boundaries.
- [x] 2026-09-22 14:42 CST: Defined the validated attribution/event contract,
  persistence models, and single-head migration.
- [x] 2026-09-22 14:48 CST: Bound accepted device authorization attribution
  to explicit new-user results across SMS, email, and Google login.
- [x] 2026-09-22 14:53 CST: Persisted immutable course attribution and
  authenticated Skill journey
  events with idempotency.
- [x] 2026-09-22 14:57 CST: Added an operator-safe aggregate reporting query
  and focused backend/frontend tests.
- [x] 2026-09-22 15:02 CST: Validated the Alembic revision directly against
  SQLite and confirmed it is the repository's sole migration head.
- [x] 2026-09-22 15:08 CST: Completed the focused attribution suites, type
  checking, architecture/UoW ratchets, repository harness, and the
  repository-wide pre-commit gate available in the branch environment. After
  the final main-branch sync, the newly introduced dependencies were not fully
  installed and exercised locally, and the frontend was not rebuilt in a
  complete lockfile environment; do not describe this as a full latest-stack
  application validation.
- [ ] Complete the following Skills producer PR.

## Surprises & Discoveries

- Current device authorization uses Redis and already keeps a server-side
  request record until the CLI collects a token. It can safely retain validated
  attribution metadata without placing it in the browser URL.
- Phone, email, and Google authentication all expose an explicit
  `AuthResult.is_new_user`; timestamps must not be used to infer registration.
- Existing browser Umami tracking has privacy sanitization, but a CLI event
  cannot provide a browser visitor identity. The backend event table is thus
  required for per-user paths.
- The former Lobster-only PRs #2800 and skills#152 were closed and are not
  available as branches. Their broad retry implementation is not reused; only
  the safe handoff principle is retained.

## Decision Log

- Decision: use `host_platform` values `workbuddy`, `doubao`, `qclaw`,
  `lobster`, `codex`, and `direct` as an explicit backend allowlist. Rationale:
  readable, stable reporting dimensions are safer than numeric or
  caller-defined values, and QClaw has its own independently built package.
- Decision: the Skill identity is the existing `SKILL.md` `name`, and its
  version is the existing `version`; the producer supplies both. Rationale:
  do not duplicate identity fields in every channel package.
- Decision: `handoff_id` is a canonical UUID, stored only in the application
  database and never emitted to Umami, logs, URLs, or user-visible output.
- Decision: first-acquisition attribution is immutable. Reactivation after an
  inactivity period is a later, append-only attribution-epoch feature and is
  outside this PR.
- Decision: the event endpoint accepts only a fixed event-name allowlist and
  derives `user_bid` from the authenticated token. Rationale: callers cannot
  forge another user's path or create unbounded analytics dimensions.
- Decision: event recording must not block course operations. The server
  persists accepted authenticated events transactionally when the request is
  made; the Skill producer treats reporting delivery as best effort.

## Outcomes & Retrospective

The backend contract now covers immutable new-user and course attribution,
authenticated allowlisted journey milestones, idempotent retries, and
aggregate operator reporting. Focused validation passed 53 backend tests and
26 frontend tests. The isolated Alembic revision created and removed all three
tables successfully and remains the sole migration head. The CLI producer and
Umami delivery remain intentionally assigned to the following Skills PR.

## Context and Orientation

- Device authorization routes: `src/api/flaskr/route/user.py`; Redis session
  implementation: `src/api/flaskr/service/user/device_auth.py`.
- Explicit new-user signals originate from `AuthResult` in
  `src/api/flaskr/service/user/auth/` and are consumed in the login route.
- Course creation route: `src/api/flaskr/service/shifu/route.py`; persistence
  transaction: `src/api/flaskr/service/shifu/shifu_draft_funcs.py`.
- User and course persistence models live in their respective service
  `models.py` files. Migrations live under `src/api/migrations/versions/`.
- Existing browser analytics is intentionally separate in
  `src/web/src/lib/tracking.ts`.

## Plan of Work

Create one shared, strict attribution parser for the two optional payloads:
`registration_attribution` during device authorization and
`creation_attribution` during new-course creation. It validates exactly
`host_platform`, `skill_id`, `skill_version`, and `handoff_id`.

Persist three low-content records: one immutable first-acquisition record per
new user, one immutable creation record per course, and an append-only Skill
journey event record. A unique event id prevents client retry double counts.
Attach registration attribution only after the same device handoff is approved
by an authentication flow that explicitly reports a newly created user.

Expose a narrowly scoped authenticated Skill-event endpoint for post-login
steps. Store only the platform, Skill/version, fixed event name, server-derived
user/course IDs, event id, and UTC timestamp. Do not store titles, prompts,
errors, URLs, contact details, or tokens.

The initial operator aggregation returns counts grouped by platform, Skill,
version, and event within a UTC time range. It is intentionally aggregate-only;
individual path investigation stays in trusted database operations, not a new
public analytics endpoint.

## Concrete Steps

1. Add the shared parser, constants, and DTO-like immutable inputs.
2. Add models and an Alembic migration based on the single current head.
3. Extend the device authorization cache payload with validated attribution;
   bind it after `is_new_user` is known and before approval consumes the
   handoff.
4. Extend new-course creation with optional immutable attribution and derive
   the authoritative `course_creation_completed` aggregate from that record;
   client delivery remains a best-effort supplement rather than the source of
   truth.
5. Add the authenticated fixed-event route for Skill start/import/publish
   milestones and aggregate query support for operators.
6. Add HTTP, transaction rollback, duplicate retry, invalid-contract, and
   no-sensitive-log regression tests.
7. Run focused user/shifu/common tests, migration checks, architecture/UoW
   checks, and pre-commit before committing.

## Validation and Acceptance

- An un-attributed browser login and normal course creation retain existing
  behavior and create no attribution records.
- A valid device authorization that creates a new user creates exactly one
  first-acquisition record; approving with an existing user does not recolor
  that account.
- Invalid platform, Skill id/version, UUID, unexpected field, or mismatched
  handoff is rejected before user/course side effects.
- A valid attributed course creates one course record owned by the authenticated
  creator. Repeated event delivery with the same event id counts once.
- A caller cannot submit a different user id, arbitrary event name, course
  title/prompt/error, or a course they do not own.
- Aggregate results accurately group fixed events over UTC boundaries; no
  raw user content appears in the response or logs.

## Idempotence and Recovery

All new payloads are optional for compatibility. User and course attribution
are immutable and have unique handoff constraints. Event delivery uses a UUID
dedupe key so CLI retry after a timeout is safe. Failed transactions leave no
partial attribution/event rows. The producer may retry reporting but never
retries an operation by inventing a new handoff id.

## Interfaces and Dependencies

The producer contract is:

```json
{
  "host_platform": "workbuddy",
  "skill_id": "ai-shifu-course-creator",
  "skill_version": "1.2.9",
  "handoff_id": "<canonical UUID>"
}
```

The device authorization endpoint receives this object as
`registration_attribution`; the new-course endpoint receives it as
`creation_attribution`. Post-login event delivery additionally carries a
canonical `event_id`, an allowlisted `event_name`, and only a course BID where
the event requires one. The Skills PR must be released only after this backend
migration and API are deployed.

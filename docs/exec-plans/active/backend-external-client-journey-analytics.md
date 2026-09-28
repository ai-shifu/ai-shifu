# Backend External Client Journey Analytics

## Purpose / Big Picture

Measure the portion of an external Skill or client journey that reaches AI
Shifu's backend after host platforms restricted Skill installation. The
backend will send best-effort Umami events for device authorization, token
collection, course creation, and publication. Analytics remains separate from
business correctness: no user or course table changes, no migrations, and no
request may fail or wait for Umami.

## Progress

- [x] 2026-09-28 12:35 CST: Audited the merged Skill attribution, device
      authorization, token storage, course creation, and publication paths.
- [x] 2026-09-28 12:40 CST: Limited the measurable journey to backend-observed
      milestones and excluded installation and import classification.
- [x] 2026-09-28 12:50 CST: Added fail-open backend Umami delivery and ephemeral
      token attribution.
- [x] 2026-09-28 12:55 CST: Instrumented device authorization, course creation,
      and publication with focused regression coverage.
- [x] 2026-09-28 13:10 CST: Ran focused and repository gates and completed the
      local self-review; delivery is waiting for user approval.

## Surprises & Discoveries

- The course-creator CLI implements import through the same course creation and
  outline mutation APIs as ordinary authoring. Without a client contract
  change, the backend cannot truthfully classify an operation as import.
- The existing registration attribution expires with the Redis device session
  immediately after token collection. Continuing the journey therefore needs
  a separate token-scoped Redis value with the token's lifetime.
- Existing Umami configuration exposes the script URL and website ID. The
  server collector URL can be derived from the script origin without adding a
  deployment secret or database configuration.
- The first adjacent-suite run exposed a test-only configuration leak: the new
  Redis TTL test changed the session-scoped Flask config without restoring it.
  Using pytest's restoring monkeypatch removed the order dependency; 188
  focused and adjacent tests then passed.
- Placing token attribution under the user service created a new cross-service
  import from course authoring. Moving the shared analytics-only context to the
  common service preserved the architecture baseline with zero new violations.

## Decision Log

- Decision: change only the AI Shifu repository. Rationale: the merged Skills
  producer already supplies the optional attribution object, while this change
  moves observable milestones to the backend.
- Decision: do not add database columns or tables. Rationale: product analytics
  is best effort and must not become a business source of truth.
- Decision: retain attribution in Redis only for the issued device token's
  lifetime. Rationale: this measures one external-client session rather than
  permanently coloring a user.
- Decision: report course creation and publication, but not import. Rationale:
  the backend has no reliable import discriminator in the current protocol.
- Decision: treat the allowlisted channel as client-asserted, not
  cryptographically trusted. Rationale: the public device endpoint validates
  shape and values but does not authenticate a package identity.

## Outcomes & Retrospective

The backend now observes attributed device authorization through token
collection, course creation, and publication without adding business storage.
The token-scoped Redis context expires and revokes with its session, while a
bounded fail-open sender isolates Umami from product behavior. All 188 focused
and adjacent tests passed, as did the architecture, unit-of-work, repository
harness, diff, developer-tooling, and full pre-commit gates. The local change
is complete; commit and pull-request delivery remain pending user approval.

## Context and Orientation

Skill attribution validation is in
`src/api/flaskr/service/common/skill_attribution.py`. Device authorization and
one-shot token issuance are in `src/api/flaskr/service/user/device_auth.py`.
Token cache behavior is owned by `src/api/flaskr/service/user/token_store.py`,
while the shared analytics-only token context lives in
`src/api/flaskr/service/common/session_attribution.py`.
Course creation and publication routes are in
`src/api/flaskr/service/shifu/route.py`. Runtime Umami configuration is exposed
as `ANALYTICS_UMAMI_SCRIPT` and `ANALYTICS_UMAMI_SITE_ID`.

## Plan of Work

Add one shared backend analytics sender that accepts only fixed event names and
allowlisted low-cardinality dimensions. Delivery uses a bounded background
executor, a short network timeout, and complete exception isolation. Copy the
validated three-field Skill identity from the expiring device request to a
separate token-scoped Redis key after token persistence succeeds. Read that
context only for authenticated course creation and publication requests.

Emit distinct backend event names so existing browser and Skills events are
not double-counted accidentally. Authorization request and decision events use
the device-session context; token collection and course events use the same
normalized dimensions. Course start, success, and failure events contain only
the operation, result, host platform, Skill ID, and major version bucket.

## Concrete Steps

1. Add the shared fail-open Umami sender and strict event payload contract.
2. Add token-scoped Redis attribution storage, lookup, expiry, and cleanup.
3. Copy device attribution after a token is durably issued and emit device
   journey milestones.
4. Wrap course creation and publication routes with attributed start and
   terminal events without changing their responses or transactions.
5. Add privacy, failure-isolation, expiry, and route outcome tests.
6. Update the canonical analytics contract and complete repository checks.

## Validation and Acceptance

- Ordinary browser sessions and unattributed device sessions emit no external
  client course events and retain their existing behavior.
- An attributed device request produces the same normalized channel dimensions
  through token collection, course creation, and publication.
- Failed creation or publication emits a failed terminal event and preserves
  the original application error.
- Umami timeout, malformed configuration, executor saturation, or Redis
  failure never changes authorization, token issuance, course creation, or
  publication.
- Event payloads exclude tokens, pairing and handoff identifiers, user/contact
  data, course identifiers or titles, raw errors, URLs, referrers, and authored
  content.
- No SQLAlchemy model or Alembic migration changes.

## Idempotence and Recovery

Umami delivery is intentionally at-least-best-effort: process termination may
lose queued events, and retried business requests may produce repeated start
or failure events. Reports aggregate outcomes and must not use events for
auditing or exact billing. The token attribution expires automatically and is
safe to recreate from a still-live device request during token collection.

## Interfaces and Dependencies

The existing device request accepts `host_platform`, `skill_id`,
`skill_version`, and a private `handoff_id`. Only the first three fields are
copied to token-scoped Redis storage. Umami receives a fixed major-version
bucket rather than the caller-controlled raw version. The collector uses the
origin of `ANALYTICS_UMAMI_SCRIPT`, posts to `/api/send`, and uses
`ANALYTICS_UMAMI_SITE_ID`; missing configuration makes tracking a no-op.

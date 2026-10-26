# Password Login Account Rate Limit

> Lifecycle review, 2026-09-26: Completed original scope. The recorded real-Redis concurrent acceptance completes the password limiter. A broader IP-policy follow-up is tracked separately. Merge evidence: [#2897](https://github.com/ai-shifu/ai-shifu/pull/2897) (`8be7b6536`)

## Purpose / Big Picture

Password login currently allows unlimited guesses and returns early for unknown or passwordless accounts. Add an account-scoped Redis guard so repeated failures enter a short cooldown while legitimate users retain alternate login methods and Redis failures never bypass password verification.

## Progress

- [x] 2026-09-20 11:10 CST: Confirmed product thresholds, privacy requirements, concurrency semantics, and staged IP follow-up.
- [x] 2026-09-20 11:15 CST: Inspected the password provider, user repository, Redis ownership, route contract, and existing tests.
- [x] 2026-09-20 19:55 CST: Implemented the account-scoped limiter and integrated it with password verification.
- [x] 2026-09-20 20:00 CST: Added focused contract, timing-path, failure, privacy, alias, and recovery tests.
- [x] 2026-09-20 20:08 CST: Verified 20 focused route tests, 93 configuration tests, translations, and a 20-request real Redis concurrency probe.
- [x] 2026-09-20 21:35 CST: Passed final repository gates, committed, pushed, and opened #2897.
- [x] 2026-09-20 22:05 CST: Addressed review findings for database connection retention, renewable lock ownership, cooldown analytics, and the CodeQL identifier-digest alert.
- [x] 2026-09-21 10:01 CST: Kept identifier response budgets consistent while an account is blocked and deferred response cleanup until account-lock ownership is confirmed.

## Surprises & Discoveries

- The shared cache provider silently falls back to process memory. Password protection must use the owned Redis client directly so a Redis outage is observable and is not misrepresented as a cross-process limit.
- Phone and email identifiers already resolve through `load_user_aggregate_by_identifier`; an existing account can therefore use its stable `user_bid` as the shared limit identity.
- The full user-service suite remains blocked by the known local `markdown_flow` version mismatch: 410 tests pass and 36 profile-onboarding tests fail because `USER_ANSWER_CONTEXT_KEY` is absent. The password-focused tests do not import that incompatible path.
- The first review found that resolving the account inside the route-owned transaction retained a database connection while waiting for Redis. Account resolution now completes before waiting, and account state is re-read after lock acquisition.

## Decision Log

- Decision: use a 15-minute fixed failure window, 10 failures, and a separate 10-minute cooldown.
  Rationale: this is the reviewed initial policy and avoids permanent account lockout.
- Decision: derive Redis keys with HMAC-SHA256 using the application secret and a purpose string.
  Rationale: low-entropy phone and email identifiers must not be recoverable from a Redis snapshot.
- Decision: fail open only for the limiter when Redis is unavailable.
  Rationale: availability is preserved, but password verification and all other authentication errors remain authoritative.
- Decision: perform a fixed dummy bcrypt verification for unknown and passwordless accounts.
  Rationale: removes the obvious fast path used for account discovery.
- Decision: renew the account lock while password verification runs and reject the attempt if ownership is lost.
  Rationale: bcrypt duration can vary under load, so a fixed lease alone cannot preserve serialization.
- Decision: count blocked-account requests only in the submitted identifier's public-response budget.
  Rationale: linked and unknown identifiers must expose the same error sequence without extending or clearing the authoritative account cooldown.

## Outcomes & Retrospective

The implementation now enforces one failure budget across an account's phone and email aliases, starts cooldown atomically at the tenth failure, performs dummy bcrypt work for missing credentials, and keeps Redis keys and logs free of plaintext identifiers. A real Redis probe submitted 20 concurrent failures and observed exactly 10 recorded failures with the remaining requests blocked. Password-IP protection remains a separate follow-up because it depends on trusted proxy parsing and production traffic observations.

## Context and Orientation

`src/api/flaskr/service/user/auth/providers/password.py` owns password verification. `repository.py` resolves phone or email credentials to a user aggregate. `password_utils.py` owns bcrypt helpers. Redis is owned by `flaskr.dao.get_redis_client()`. HTTP routing and the existing response envelope remain unchanged except for a localized cooldown error.

## Plan of Work

Create a password-specific limiter module. It will compute opaque account keys, serialize attempts for the same account with a bounded Redis lock, atomically count failures and create the cooldown, clear only that account after success, and emit privacy-safe structured events. Integrate the limiter around password verification and use the same bcrypt work for missing credentials. Add configuration defaults and translations, then cover all observable boundaries in focused tests.

## Concrete Steps

1. Add rate-limit configuration and the password-specific Redis helper.
2. Refactor the password provider so account resolution selects a stable limit identity and every invalid path performs bcrypt verification.
3. Add translations and an error code for cooldown responses.
4. Add tests for threshold boundaries, cooldown recovery, aliases, missing accounts, Redis failure, success reset, opaque keys, and concurrent attempts.
5. Run focused tests, Ruff/format, translation checks, architecture/UoW checks, and the repository pre-commit gate before requesting commit approval.

## Validation and Acceptance

- Attempts one through nine return the normal invalid-credentials contract; attempt ten starts cooldown and returns the cooldown contract.
- Correct credentials cannot pass during cooldown, and work again after cooldown expires.
- Phone and email credentials linked to one user share the same counter.
- Unknown, passwordless, and wrong-password paths all execute bcrypt and expose the same invalid-credentials response before cooldown.
- Concurrent failures cannot all pass a stale pre-threshold check.
- Redis absence or command failure still performs password verification and permits a correct password.
- Redis keys and logs contain no plaintext identifier or password.

## Idempotence and Recovery

The change requires no database migration. Redis records expire automatically. A deployment rollback leaves only purpose-scoped expiring keys. Re-running tests is safe because each test uses isolated keys or a fake Redis instance.

## Interfaces and Dependencies

- Redis commands and locks supplied by the repository-owned redis-py client.
- Existing bcrypt helpers and user aggregate repository.
- Existing common API error envelope and backend i18n JSON files.
- [x] 2026-09-20 22:45 CST: Closed follow-up review gaps: alias-safe public cooldown responses, failure-budget reset when cooldown starts, and CodeQL/test-fixture compatibility for keyed verification-state digests.
- [x] 2026-09-21 08:50 CST: Made counter mutation and success cleanup conditional on the live Redis lock token, bounded limiter-only Redis I/O, and equalized blocked-account bcrypt work.
- A shared account cooldown cannot be returned verbatim for every alias: doing so reveals that two identifiers resolve to the same account. A separate identifier-scoped response budget now controls only the public error while the account-scoped limiter remains authoritative.
- The failure counter must be deleted atomically only when the request creates the cooldown; otherwise its older TTL can cause an immediate second cooldown after the first one expires.
- A renewal thread's local event can lag behind an expired Redis lease. Every state mutation must therefore compare the Redis lock token inside the same Lua operation that changes failure or cooldown keys.
- Redis lock contention timeouts do not bound a silent socket read. Password protection uses an isolated connection pool with finite connect/read timeouts and no retries so the reviewed fail-open policy remains timely.

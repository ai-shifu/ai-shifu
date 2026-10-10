# Simple lesson reset limit

## Purpose / Big Picture

Replace the oversized implementation proposed in PR #3065 with a focused learner cost-control change based on current main. Use one deployment setting, `LESSON_RESET_LIMIT`, default 9999. Each ordinary learner has an independent limit for each course lesson. Course owners and all active course collaborators, including read-only collaborators, are exempt; global teacher/operator roles alone are not exemptions.

## Progress

- [x] 2026-10-10 Asia/Shanghai: User authorized a new PR and the simpler rule: a successful reset consumes one use; subsequent text or TTS generation failure does not refund it.
- [x] 2026-10-10 Asia/Shanghai: Created a clean branch from main, now fast-forwarded to `2ba2420f7`; the original PR and its branch remain intact.
- [x] 2026-10-10 Asia/Shanghai: Checked existing progress creation, reset, preview and course permission paths.
- [x] 2026-10-10 Asia/Shanghai: Isolated in-memory SQLite proof using current main showed one reset retires two sibling progress records. Repeating a no-op reset returns success without adding records. Counting retired rows therefore does not directly count successful operations.
- [x] 2026-10-10 Asia/Shanghai: User declined a schema change for now and requested further assessment. No counter table or migration may be implemented.
- [x] 2026-10-10 Asia/Shanghai: User authorized isolated Redis validation. Built official Redis 7.2.5 in a temporary directory and ran 15 experimental assertions against real Redis and synthetic SQLite. Verified atomic cap and duplicate receipts, and reproduced cross-store undercount, expired-lock over-admission and loss of nonpersistent counters. These are feasibility experiments, not product acceptance.
- [ ] 2026-10-10 Asia/Shanghai: Verify actual deployed Redis persistence, eviction and cross-environment prefix isolation. Read-only CICD confirms Redis is configured for dev02, but does not expose runtime CONFIG/INFO or cleartext prefix; the actual conditions remain unverified.
- [x] 2026-10-10 Asia/Shanghai: User approved Redis, successful-reset counting and exceptional undercount after a service interruption, with no SQL schema change.
- [x] 2026-10-10 Asia/Shanghai: User approved temporarily blocking reset when Redis cannot be reached; keep existing content and ordinary learning available.
- [x] 2026-10-10 Asia/Shanghai: Implemented the backend guard and availability contract. Real service tests with synthetic SQLite and FakeRedis verified first study, effective resets, cap preservation, retry receipts, scope, exemptions and rollback.
- [x] 2026-10-10 Asia/Shanghai: Implemented learner dialogs and update notices; frontend acceptance tests remain pending.
- [x] Implement configuration, course-specific exemption, transactional reset admission and exhausted UI.
- [x] Local verification: effective-reset boundaries, successful request retries, actual Redis concurrency/lease renewal, SQL rollback, authenticated HTTP identity and preview permission, exhausted/outage dialogs, updated-lesson review and analytics failure isolation. Deployed acceptance remains pending.
- [ ] Run repository gates, commit the focused implementation and verify dev02 before proposing production. Preserve #3065 until the replacement PR is ready.
- [ ] Separately plan dev02 deployment, accounting for old test-only tables and migration revisions; do not drop them or downgrade automatically.

## Surprises & Discoveries

Existing `learn_progress_records` are learning-state records, not reset operations. Current main explicitly handles sibling rows created by concurrent Ask. One reset retires all live rows; no-op resets also return true. An unqualified status-row count can overcount genuine resets or miss no-op successes. No existing general-purpose persisted reset audit was found in the inspected model paths. Redis counters avoid schema changes but introduce eviction/persistence and cross-store transaction gaps. The user accepted exceptional post-commit undercount; actual environment durability remains to be checked.

Local Redis experiment: Lua admitted exactly 10 of 100 concurrent unique requests and charged once for 50 concurrent identical request IDs. Count keys had no TTL; experiment receipts lasted one hour, so this is not proof of indefinite retry protection. Post-SQL counting missed a durable reset when the accounting step was interrupted. A short lock expired between admission and reset; another worker reset and new learning resumed before the first worker continued, yielding two durable resets against a limit of one. Atomic Redis writes alone do not enforce SQL reset admission. AOF with `appendfsync=always` retained an acknowledged count after a local process kill; an instance without persistence lost it. No disk failure, real MySQL, permission, frontend, TTS or deployed runtime acceptance was performed.

## Decision Log

- New implementation starts from current main, without cherry-picking the old backend ledger or its three migrations.
- Count an effective reset when its database transaction succeeds. Reset transaction failure consumes nothing. Later generation failure does not refund it.
- Duplicate successful requests must not clear newly resumed learning or consume another use. Store successful request receipts with the count in one Redis value, without TTL. The web client retains its request ID across an uncertain response until success, within the current page lifecycle.
- First study, continuation, Ask, saved-text review and saved-audio replay are unaffected.
- Teachers cannot configure limits. Learners do not see counts; exhaustion preserves current content and offers continued study/review/Ask.
- Use reset for new technical names, following existing reset helpers; learner-facing Chinese remains shared translations.
- Config documents scope and staff exemptions. Default 9999 is a finite high allowance, not a separate enable switch. Reject invalid configuration rather than silently bypassing the rule.
- Preview remains unlimited with existing permission checks and current-main preview handling preserved.
- Redis is approved; no schema change or counter table is authorized. Do not borrow unrelated config or learning fields as hidden counters. Temporarily block only reset on a Redis failure before SQL commits. After commit, accounting failure may miss a use; do not claim that SQL can be rolled back then.
- Admission-time counting is an alternative for abuse control, not an approved replacement for successful-reset counting. It can reject excess requests before SQL changes, but an interrupted reset may occupy a use. Known SQL failures could be compensated; crash-proof compensation would reintroduce recovery complexity and is outside the simple proposal.

## Outcomes & Retrospective

Backend and learner UI implementation are in progress. No schema migration, environment deployment or new PR exists yet. Local service tests use synthetic SQLite and FakeRedis, not deployed Redis/MySQL. The experiment script and JSON results are in `/private/tmp/lesson-reset-redis-validation.py` and `/private/tmp/lesson-reset-redis-validation-result.json`; these temporary artifacts are not repository tests or release evidence. The simpler scope removes the need to track generation producers, refund failed generation or intercept normal teaching writes.

## Context and Orientation

The reset entry is `src/api/flaskr/service/learn/learn_funcs.py:reset_learn_record`, called by the existing DELETE records route in `routes.py`. Progress models live in `models.py`; course permissions are resolved through existing course owner/collaboration paths. Frontend reset calls live in `src/web/src/api/lesson.ts`, with catalog and updated-lesson entry points. Reuse their appropriate copy and tests from the old PR selectively rather than importing its service architecture.

## Plan of Work

Use the approved Redis design within the user's no-schema-change scope. A Redis counter could protect reset frequency, but cannot be committed atomically with SQL progress changes. The existing on_commit callback runs after the SQL commit and logs callback exceptions; it does not roll back that commit. Redis pre-increment can overcount a failed SQL reset, while post-commit increment can miss a successful reset if the process stops or Redis fails. Do not silently redefine successful-reset counting or add a reservation/recovery system to hide this tradeoff. Do not add ordinary-study producer locks, generation settlement hooks, course policies, rollout namespaces or course allowlists. Keep necessary learner UI, shared translations, analytics and regression coverage.

## Concrete Steps

1. Record the approved storage and failure semantics; do not assume Redis can provide an atomic SQL transaction.
2. Add only the reset-limit configuration and accurate generated Docker example.
3. Check current course permissions and lesson ownership on the server.
4. Implement the approved admission/accounting order and narrowly documented failure behavior. Atomic rollback of both SQL and Redis is unavailable.
5. Reuse exhausted-dialog and updated-lesson review behavior with no visible balance.
6. Update the relevant existing analytics contract without new unrelated event families.
7. Run focused tests, shared contract gates and necessary frontend/learning regression.
8. Submit a focused new PR with an explicit schema and rollback assessment, preserving the original review record by linking the superseded PR.

## Validation and Acceptance

Test a small limit locally: first study is free, exactly N effective resets succeed, the next reset leaves current content unchanged. Verify independent learners/lessons/courses, owner and all active collaborator exemptions, revoked access, preview authorization, guest identity behavior, repeated/no-op resets, concurrent admission, and rollback on mid-reset failure. Verify no generation callback changes the count. Existing backend unit-of-work, frontend translation and analytics rules remain required. SQLite feasibility proof is not MySQL concurrency acceptance.

## Idempotence and Recovery

Reset rollback is owned by the existing database transaction. Post-reset generation failures retain the consumed use; there is no automatic refund or producer-recovery subsystem in this feature. Retrying an uncertain request must not repeat its reset or charge. A per-learner/lesson Redis lock spans SQL and post-commit accounting. Renew its lease during normal slow SQL work and recheck it before committing; without that protection the local experiment reproduced over-admission. Write the count and receipt atomically after SQL commits. This is not a crash-proof cross-store transaction or generation recovery system. Do not modify or delete legacy dev02 ledger data during code preparation.

## Interfaces and Dependencies

One environment setting: `LESSON_RESET_LIMIT=9999`. Keep existing authentication, course permission, response envelope, UTC, shared translations and request transport. Redis assessment uses existing Redis prefix and learner/course/lesson scope, counters with no automatic TTL, atomic quota checks and scoped retry identity. Do not rely on a short operation lock as the only admission guarantee: the experiment reproduced its lease-expiry gap. Actual deployed persistence and eviction are unverified; a Compose volume alone is not proof of durable production counters. No new SQL schema is authorized. The new PR has no permission to merge main or deploy production. Official reference: [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).

## Complexity assessment

- Redis state and one setting: required to enforce a cap without SQL migrations. Without state every reset is unlimited. A SQL counter would improve durability but is outside the approved scope.
- Per-lesson operation lock, renewal and pre-commit check: prevent simultaneous or normally slow requests from exceeding the cap. A bare increment or short lock was experimentally insufficient; no normal-learning lock is added.
- Successful request receipt: prevents an uncertain-response retry from clearing new learning or charging twice. Stored with the count, with no separate table, reservation or recovery worker. A simpler counter alone cannot distinguish retries.
- Availability GET and shared UI hook: prevent the exhausted dialog from still asking to clear content and prevent an unusable course-update link. DELETE remains authoritative, so a stale browser cannot bypass the cap. No count is exposed.
- Blocked analytics: required by the repository user-facing feature contract; best-effort and never a source of quota truth. No new dashboard is included.
- Future optional work: persistent counter storage, quota gifts after course updates, appeals and stricter guest identity. None is implemented or approved in this change.

## Scenario evidence and release state (2026-10-10)

| User scenario | Evidence | State |
| --- | --- | --- |
| First study / empty reset | Real service creates no counter until learning records are effectively reset | Local SQLite + FakeRedis passed |
| Learner uses last allowance | Next reset returns 4021; current progress stays in progress; availability exposes only a boolean | Local service and UI passed |
| Several progress rows belong to one lesson | One reset retires both rows and consumes one use | Local service passed |
| Successful response is lost, then retried | Same receipt does not clear newly resumed progress or charge again; client retains pending request ID | Local service and transport passed |
| Other learner / lesson / course | Independent counters | Local service passed |
| Owner / active collaborator, including read-only | Exempt; revoked and other-course collaborator not exempt | Local service passed |
| Preview flag / forged learner query | Existing preview permission required; authenticated request identity is forwarded | Local HTTP contract passed |
| Redis unavailable before reset | 4022; current progress retained; staff reset bypasses counter | Local service and UI passed |
| SQL failure / lost guard before commit | Reset rolls back, count unchanged | SQLite + actual isolated Redis passed |
| Concurrent / normally slow admission | Actual production guard/Lua admits only two of 24 concurrent calls at a test cap of two; lease renewal survives a shortened test lease | Actual isolated Redis passed, not deployed MySQL concurrency |
| Redis accounting fails after SQL commit | SQL reset succeeds but count can remain zero | Accepted exceptional undercount reproduced |
| Course updated after exhaustion | Friendly existing-content notice; no unusable reset link; exhausted dialog has no clear-content question | Local UI passed |

Focused backend/config validation: 110 cases passed with real Redis available. Focused UI, state and transport validation: 42 cases passed. Full `lefthook run pre-commit --all-files` passed after correcting a new cross-service import rather than expanding the baseline. Translation parity/usage and the unit-of-work ratchet passed.

The repository-wide TypeScript check remains red due to unchanged main tests in `src/web/src/app/admin/operations/users/[user_bid]/page.test.tsx`: an untyped mock `this` and deletion of a nonoptional property. The dev02 Dockerfile runs `npm run build`, so this is a build-readiness gap. Do not silently mix that unrelated fix into the reset PR. A proposed two-line test-only correction is held for the user's scope decision.

Implemented and locally tested; not pushed to dev02, not deployed, not production-released. Redis persistence/eviction and environment isolation remain unverified in the actual deployment. No test/production SQL tables or migration markers have been modified.

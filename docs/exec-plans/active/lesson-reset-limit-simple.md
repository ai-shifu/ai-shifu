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
- [ ] 2026-10-10 Asia/Shanghai: Complete actual Redis durability and environment-isolation assessment. The approved read-only check confirms reachability, noncluster mode and noeviction; persistence fields are unavailable and the default prefix does not establish separation.
- [x] 2026-10-10 Asia/Shanghai: User approved Redis, successful-reset counting and exceptional undercount after a service interruption, with no SQL schema change.
- [x] 2026-10-10 Asia/Shanghai: User approved temporarily blocking reset when Redis cannot be reached; keep existing content and ordinary learning available.
- [x] 2026-10-10 Asia/Shanghai: Implemented the backend guard and availability contract. Real service tests with synthetic SQLite and FakeRedis verified first study, effective resets, cap preservation, retry receipts, scope, exemptions and rollback.
- [x] 2026-10-10 Asia/Shanghai: Implemented learner dialogs and update notices; frontend acceptance tests remain pending.
- [x] Implement configuration, course-specific exemption, transactional reset admission and exhausted UI.
- [x] Local verification: effective-reset boundaries, successful request retries, actual Redis concurrency/lease renewal, SQL rollback, authenticated HTTP identity and preview permission, exhausted/outage dialogs, updated-lesson review and analytics failure isolation. Deployed acceptance remains pending.
- [x] 2026-10-10 Asia/Shanghai: Repository gates passed and the focused implementation is committed. Dev02 build/deployment completed without touching old test-only tables or migration revisions; temporary CICD routing and diagnostic script were restored.
- [x] 2026-10-10 Asia/Shanghai: Deployed browser acceptance covers the authorized staff account at eleven resets and the approved guest identity at ten resets with the next attempt blocked, preserved content, Ask, reload and independent lessons. Authenticated nonstaff has local HTTP/service coverage only. Preserve #3065 as prior review history.

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

Backend and learner UI implementation are committed and deployed to dev02. Production is unchanged; there is no schema migration, and the production decision and PR review remain open. Local service tests use synthetic SQLite and isolated Redis; deployed browser evidence covers the approved guest identity and a course-authorized staff account. The experiment script and JSON results are in `/private/tmp/lesson-reset-redis-validation.py` and `/private/tmp/lesson-reset-redis-validation-result.json`; these temporary artifacts are not repository tests or release evidence. The simpler scope removes the need to track generation producers, refund failed generation or intercept normal teaching writes.

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

At the initial local checkpoint, the feature was implemented and locally tested but not deployed. The deployment section below records the later dev02 rollout and its remaining acceptance gaps. No test/production SQL tables or migration markers have been modified, and production remains unchanged.

## Deployment preparation (2026-10-10)

The user approved a separate two-line operations-test type fix and one temporary read-only Redis diagnostic, with CICD configuration restoration. The type-only fix is PR #3090 (`codex/fix-operations-test-types`, commit `e4faeb151`); it passed the whole web TypeScript check, user-detail hash/scroll regression and full lefthook gate. The reset feature branch does not contain those changes.

A separate integration branch `codex/lesson-reset-limit-dev02` combines the reset feature with that test-only fix. Dev02 alone now has `LESSON_RESET_LIMIT=10`. No SQL records, migration revisions or production configuration were modified. The CICD manual branch-build call returned HTTP 500 Not Found and created no build. The normal push path then created build 510 / Drone 5299, source `2e4134e5620dcc2333cf8877108c1321efb4fe57`, image tag `20261010-2e4134e`. Dev02 CICD branch routing is temporarily the integration branch; restore it to `dev02` after this acceptance deployment. Git `dev02` history remains unchanged.

The temporary API post-script issues only Redis PING, INFO and CONFIG GET commands using existing environment configuration; it reads no learner data and emits no credentials or literal masked prefix. It reports prefix scope classification, persistence and eviction settings. The original API post-script is empty and script timeout is zero; restore those after the one check, preserving any concurrent unrelated CICD edits. A classified prefix does not prove cross-environment isolation by itself.

Build 510 / Drone 5299 succeeded. API, web and worker run image `20261010-2e4134e`; initial auto-deploy records are 2426–2429. The first diagnostic failed in dotenv before issuing Redis commands. An explicit dotenv path corrected that launcher; API redeploy 2430 completed the one read-only Redis inspection. Redis PING succeeded, the runtime limit is 10, cluster mode is off and `maxmemory_policy` is `noeviction`. The cloud service did not expose persistence fields or CONFIG GET values, so durable recovery remains unverified. The prefix is the default scope; this does not prove separation from other environments. No Redis server configuration or learner data was changed by the diagnostic.

Fresh CICD readback confirmed branch `dev02`, empty API post-script and timeout zero restored after the check. The limit of 10 remains intentional dev02 feature configuration. API/web/worker have no observed restarts; celery beat continues a pre-existing restart problem and is outside this feature's scope. Old test tables remain untouched.

### Browser acceptance checkpoint

On the published dev02 test copy `c2cf49551ba94345b5a141c78d7b86e7`, lesson `49627b510d2d4147b691b77d8bb6fd13`, browser account “小0” completed eleven effective resets and reached regenerated teaching/interaction content each time. No count or remaining balance appeared. Visible UI inspection confirmed that this account can access the test course editor and publish controls; it has course permission and is expected to be exempt. These resets prove working regeneration and staff exemption, **not** ordinary-learner cap acceptance. No permissions were changed for the test.

The user explicitly approved temporary logout and guest acceptance, with user-owned relogin afterward. Under the existing browser guest identity, short lesson `aa5e4bbf085c4baf89c4ee569e83e75c` displayed its initial saved “测试重修” content, then completed ten effective resets. The eleventh attempt displayed the exhausted notice without the clear-content question; acknowledging it preserved “测试重修”, Ask and Next. Screenshot evidence is `/private/tmp/lesson-reset-dev02-exhausted.jpg`. The short lesson uses static teaching text, so this verifies the deployed SQL/Redis reset boundary without repeatedly spending generation credits; generated-content regeneration was separately verified on the longer lesson under the staff account.

Guest Ask returned an answer after exhaustion. Reloading preserved the saved text and question/answer and still displayed exhaustion on reset; this proves reload cannot bypass the same browser identity, not Redis crash recovery. After dismissing optional lesson feedback, Next opened lesson `49627b510d2d4147b691b77d8bb6fd13`, where a first guest reset succeeded and regenerated teaching content: the exhausted short lesson did not consume the other lesson's allowance. Additional screenshot evidence is `/private/tmp/lesson-reset-dev02-ask-after-exhaustion.jpg`. No learner permissions, Redis values or SQL records were injected for these checks; learning/reset itself used the normal UI.

Authenticated nonstaff, updated-lesson exhausted notice, Redis-outage and SQL-failure scenarios have local coverage only; this deployment performed no fault injection or course republishing. Do not present those as live acceptance or claim production durability from a local Redis experiment. The browser is intentionally left logged out after the user's approval; this guest short lesson is exhausted and the longer lesson has used one reset. For another ordinary-user acceptance run, use a nonstaff test account or another lesson; using the owner/collaborator account will remain unlimited.

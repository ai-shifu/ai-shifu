# Lesson retake limits: production review record

## Purpose / Big Picture

Prevent unusually frequent regeneration from driving course delivery costs. The current rule is ten successful extra teaching starts per learner identity and lesson in explicitly enabled deployments. Teachers do not configure a quota, and learners do not see remaining counts. This limits generation frequency, not total credits.

PR #3065 targets `main` from `codex/lesson-retake-production`. Review and fixes are authorized; merging and production deployment are not. Do not merge the test-environment integration branch wholesale: it includes unrelated features.

## Progress

- [x] 2026-10-03 Asia/Shanghai: Added ledger, producer ownership, durable-content counting, rollback snapshots and additive migrations.
- [x] 2026-10-08 Asia/Shanghai: Replaced teacher quotas with the fixed hidden ten-retake rule; reading-mode test delivery completed.
- [x] 2026-10-09 Asia/Shanghai: Verified real test-course speech settlement, cached replay, exhaustion and update guidance. Production configuration remains untouched.
- [x] 2026-10-09 Asia/Shanghai: Submitted PR #3065 without merging. Repaired two frontend module-loading failures; all 261 suites / 3,021 assertions passed before review follow-up.
- [x] 2026-10-09 Asia/Shanghai: User confirmed exemption for all active course collaborators, including read-only collaborators. Keep existing shared preview/progress storage; no isolation migration is authorized by this decision.
- [x] 2026-10-09 Asia/Shanghai: Added staff admission/revocation coverage, stable retry identities, current-request analytics, matching accessible labels, and locale-independent error-code assertions.
- [x] 2026-10-09 Asia/Shanghai: Existing reserved attempts settle after enforcement is disabled; another reset cannot erase a pending attempt. Other deployment namespaces remain excluded.
- [x] 2026-10-09 Asia/Shanghai: Existing ten-retake policies are read without repeated updates. The course-wide lock is still retained.
- [x] 2026-10-09 Asia/Shanghai: Added read-only operator diagnostics and explicit ordinary-run confirmed-stop recovery coverage; no automatic timeout takeover was added.
- [ ] 2026-10-09 Asia/Shanghai: Confirm scope for automatic ordinary-run recovery and replacing course-wide locks. Automatic approval rejected the global flush interceptor and lock-removal proposals; neither was applied.
- [x] 2026-10-09 Asia/Shanghai: Complete local regression, full pre-commit, repository harness and architecture checks for review fixes.
- [x] 2026-10-09 Asia/Shanghai: GitHub checks for `9574a9180` all passed; latest CodeRabbit review reported no new actionable findings. Recovery/concurrency scope confirmation remains pending.
- [x] 2026-10-09 Asia/Shanghai: Resolved three reset-entry conflicts with main `bdde9c54a`, retaining draft preview history, permissions, lesson ownership and retake idempotency. Adapted main preview tests without weakening admission.
- [x] 2026-10-09 Asia/Shanghai: Main-sync acceptance passed 1,361 backend/HTTP/preview/agent tests, 262 frontend suites / 3,028 tests, frontend lint and full pre-commit gates. Full TypeScript still reports only the two existing operations-user test errors.
- [ ] 2026-10-09 Asia/Shanghai: Push the synchronized PR branch, refresh its template checklist, and read back mergeability and new CI status. Latest review-follow-up runtime acceptance remains a release prerequisite.
- [ ] Future release: Review migration ordering, namespace, worker compatibility, incident ownership and rollback, then obtain explicit merge/release authorization.

## Surprises & Discoveries

Preview permission includes read-only collaborators. Legacy course preview and published learning share some progress records. Current main independently adds draft-script preview history; retain that implementation while preserving staff exemption. The user chose course-staff exemption instead of introducing preview isolation in this feature. Consequently, preview resets can still change the same staff member's own published progress; this is an explicit retained boundary, not proof of isolated storage.

Frontend integration tests mocked the store barrel but not the directly imported user store. This caused real stream dependencies or circular module loading during test startup. Direct imports and matching mocks resolved the original failure. Backend full CI exposed four assertions that matched internal error names rather than localized messages; stable error codes now own those assertions.

Retake reservation and content generation occur in different requests. Disabling a flag between them must not abandon the already accepted reservation. A stable namespace is required throughout rollback; changing or clearing it is not a supported rollback mechanism.

The original course-policy upsert wrote even for ordinary status checks. Existing fixed policies now take a read-only fast path. Removing the course-wide lock is a separate concurrency change requiring explicit scope confirmation and real MySQL verification.

## Decision Log

- Scope: each current learner identity and lesson, not a course-wide shared pool.
- Limit: ten additional successful starts. First study, continuation, saved-content review, saved-audio replay and Ask do not consume a retake.
- Counting: confirmed reset reserves; first nonempty durable teaching content charges once. Partial text counts even if later generation or TTS fails.
- Failure: empty failure restores prior learning and releases only after the producer has stopped. Timeout, disconnected browser or report alone is not proof of termination.
- Staff: current course owner and all active course collaborators are exempt in published learning as well as preview. Global teacher/operator/admin status and another course's collaboration do not grant exemption. Revocation preserves historical usage and rechecks permission on the next action.
- Preview: unlimited; retain main's draft-script preview handling and legacy shared progress. This retake feature adds no isolation schema or migration.
- Updates: same lesson identity preserves usage; no automatic replenishment. Exhausted update notice offers review guidance without an unusable reset link.
- Guests: temporary identities can study and retake under the same ledger. Changing browser/storage can create a fresh identity; preventing that is outside this phase. Guest-to-existing-account merge does not migrate the ledger.
- History: preserve recorded usage; do not reconstruct old uncounted resets or reset real counters for demonstrations.
- Rollout: default off, deployment-local namespace and allowlist/global flag. Disabled enforcement continues settling obligations in its existing namespace.
- Analytics: best-effort product signals never grant permission or determine billing. Contract v3 excludes all exempt course staff; fresh dialog checks cannot use stale prefetched responses.

## Outcomes & Retrospective

Recorded test acceptance before the review follow-up included 827 backend tests, 70 HTTP/connection probes, 12 isolated MySQL/recorder tests and 68 mocked audio/provider-failure tests. Review follow-up subsequently passed 1,323 backend/HTTP/agent tests (including the full offline engine gate) and 261 frontend suites / 3,026 assertions. The final focused ledger/execution suite passed 82 tests after the additional diagnosis and delivered/empty staff-revocation cases; these overlap the broader suite and must not be added to its total.

The test environment ran image `20261009-16fdeb8` across API, beat, worker and web. Real speech settled one 50.28-credit test charge; saved-audio replay, mode switching and refresh showed no additional settlement in the observed window. The test rate is not a production cost estimate. A synthetic recovery drill verified restoration, delivered-usage retention and idempotence, then removed its simulated records. It did not kill a live producer or inject a real provider failure.

The test API's gthread startup change recovered observed speech/connection failures on the same image. It is an operational test configuration, not part of this code PR; the precise original cause and production startup compatibility are not conclusively established. Pending unused temporary test-credit cleanup is separate housekeeping, not a code-review prerequisite. Retain detailed screenshots, private account references and workstation receipts outside version control.

## Context and Orientation

The reusable core lives in `src/api/flaskr/service/learn/retake_policy.py`, `retake_ledger.py`, `retake_execution.py`, `retake_run_guard.py`, `retake_service.py` and `retake_recovery.py`. Teaching writers bind at their durable database boundary. Existing learning engines are integration points; this is not a MarkdownFlow engine upgrade.

Frontend reset admission and retry identity live in `src/web/src/hooks/useRetakeAllowance.ts`, `src/web/src/api/lesson.ts` and `src/web/src/lib/retakeRequestIdentity.ts`. Both catalog and update-notice entry points use the same server decision. Translations live in shared i18n JSON. Canonical analytics contracts live in `docs/references/frontend-product-analytics.md`.

## Plan of Work

Fix review findings one at a time, test the affected contract, run the broader backend/frontend checks, and submit changes to the existing PR. Keep unapproved recovery/concurrency proposals separate from accepted changes. Existing test-environment deployments remain independent of a PR push.

## Concrete Steps

1. Verify ten successful starts and blocked eleventh for ordinary learners; verify staff and revoked permissions.
2. Verify pending reservation settlement when global/allowlist enforcement is removed, including empty failure and namespace exclusion.
3. Verify retry after lost transport, identity hydration including guests, and failure before a destructive request.
4. Verify fresh admission analytics, failed query exclusion, accessible labels and unchanged saved-content access.
5. Verify operator diagnostics and recovery do not release a live producer or erase charged usage.
6. Run focused tests, the offline agent gate, complete frontend tests and repository gates; update the PR description.
7. Before any later merge, review actual production startup, migrations and namespace independently.

## Validation and Acceptance

Successful delivery requires server-owned accounting and both UI entry points, not a frontend counter alone. Validate cross-tab repeated requests, producer ownership, empty and partial failure, account changes, exhausted updates and staff permission revocation. A green CI run is not a production deployment or proof of cost savings.

Observed production release pins remain `markdown-flow==0.3.4` and `markdown-flow-ui` `0.2.29`. The current independent lockfile install reports two existing operations-user test TypeScript errors. Earlier shared dependencies also produced two library locale errors; no clean repository-wide type-check is claimed. Do not change unrelated library pins or engine behavior to conceal baseline failures.

## Idempotence and Recovery

Reservations reuse stable request identities. Unknown transport outcomes retain the identity; success or a confirmed released-attempt outcome ends it. Database state and producer identity own settlement. Keep all timestamps UTC, serialized with `Z`.

For a blocked learner lesson, an operator can inspect state from the application shell using `inspect_lesson_run(app, namespace=..., shifu_bid=..., user_bid=..., outline_bid=...)`. It returns the current producer identity, UTC timestamps and pending attempt state without modifying records. Age is diagnostic only.

Recovery procedure:

1. Inspect the exact affected deployment and lesson, then confirm the identified producer has actually stopped by checking/replacing the relevant worker. Database age or an expired Redis lease alone is insufficient.
2. Call `repair_stopped_lesson_run` with the exact inspected producer identity, operator identity and `confirmed_stopped=True` in the matching deployment application shell.
3. Empty failed retakes restore previous progress; delivered retakes retain usage. Ordinary study recovery changes only its run slot and consumes/refunds no retake.
4. Inspect again and verify the learner can continue. Repeated repair is idempotent; an old identity cannot release a newer producer.
5. If there is a reservation with no run identity, do not invent a producer ID or delete the record. A resumed teaching request can claim it even after enforcement is disabled; investigate separately if that path cannot run.

Rollback disables new enforcement while preserving the namespace, ledger and schema. Existing pending attempts remain managed until they settle. Do not change namespaces, delete historical attempts or use timeout-based refunds as rollback.

## Interfaces and Dependencies

Migrations are additive: `0a3b9866d338`, `48efe7c245af`, `f5c8745b7e91`. Apply via the standard runner and verify schema before configuring a namespace or enabling a rollout. No review-follow-up migration is currently introduced.

Learner status exposes decisions (`available`, `allowed`, `in_progress`, `quota_exempt`), not remaining counts. Retired teacher configuration is unavailable/rejected. Staff exemption uses current course-specific permission records on the server.

Use `LESSON_RETAKE_NAMESPACE` as a stable deployment identity; `LESSON_RETAKE_SHIFU_BIDS` selects courses and `LESSON_RETAKE_GLOBAL_ENABLED` enables a deployment-wide rollout. Production CI/CD can deploy automatically after a main merge, so this task stops at PR review. Assign an incident responder before activation because process crashes can still require confirmed-stop repair.

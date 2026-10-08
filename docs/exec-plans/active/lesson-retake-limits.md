# Per-lesson retake limits: reusable test-environment core

## Purpose / Big Picture

Deliver a real, reusable per-learner, per-lesson retake capability, now enabled across dev02 courses only. The current approved rule is ten extra retakes per learner per lesson across enabled deployments, with no teacher control or learner balance display. The server owns enforcement. Earlier teacher-configurable decisions below are historical and superseded by the October 8 task list. No production deployment is authorized by this task.

## October 8 approved replacement task list

- [x] 2026-10-08 Asia/Shanghai: G1 Record fixed ten, hidden quota and rollout scope.
- [x] 2026-10-08 Asia/Shanghai: G2 Auto-initialize policy/lock for every dev02 course; ignore old teacher limits, preserve usage and failure recovery.
- [x] 2026-10-08 Asia/Shanghai: G3 Remove teacher control and all normal/last-attempt learner quota reminders; retain reset confirmation, blocked and retry guidance.
- [x] 2026-10-08 Asia/Shanghai: G4 Regression: ten accepted/eleventh blocked, lesson isolation, legacy settings/history, auto-init, preview, concurrency and analytics.
- [ ] 2026-10-08 Asia/Shanghai: G5 Commit/push dev02, verify build, deployment and environment activation separately.
- [ ] 2026-10-08 Asia/Shanghai: G6 Browser acceptance and user testing guide with actual starting usage disclosed.

Current contract: first study, continuation, review and Ask do not count. Confirmed reset reserves; first durable teaching charges, empty failure restores/releases. Successful text with later TTS failure still charges. No automatic expiry or course-update replenishment. Existing ledger counts are retained; historically uncounted resets are not backfilled. Old limits (including unlimited/zero/two) become ten. Teacher GET is deprecated/unavailable and PUT rejected, preventing old clients from changing the fixed rule. Learner status returns decisions only, no counts. Deployment-local namespace is mandatory; an explicit global flag activates every course only in dev02. No production/SIM authorization. No schema migration or history deletion. Rollback clears the global flag and restores the previous image and test-course allowlist; ledger remains intact.

Analytics v2 is defined in frontend-product-analytics.md. Billing reports and server ledger, not Umami, determine anomalous consumption. Test-course previous usage is two, leaving eight internally; do not reset real history for a demonstration.

## Progress

- [x] 2026-10-03 Asia/Shanghai: Re-read approved Obsidian scope and current learning code.
- [x] 2026-10-03 Asia/Shanghai: Fetched origin/dev02 and created isolated codex/lesson-retake-limits worktree from e74ddb30a; original dirty checkout preserved. No source .env files existed at the three standard locations.
- [x] 2026-10-03 Asia/Shanghai: T1 task breakdown and default-off rollout contract recorded; no historical debit is an explicit reviewable assumption.
- [x] 2026-10-03 Asia/Shanghai: T2a reusable rule/SQL ledger and deployment namespace isolation implemented; focused tests pass.
- [x] 2026-10-03 19:55 Asia/Shanghai: T2b-1: Bind actual producer iteration and both durable teaching writers to the ledger; add atomic reset snapshots and failure restoration. Focused offline database tests pass.
- [x] 2026-10-03 Asia/Shanghai: T2b-2 local integration: First-study/continuation producer guards, platform repair and reset admission implemented and tested.
- [x] 2026-10-03 20:55 Asia/Shanghai: T2b MySQL gate: Five concurrency cases passed on isolated local MySQL 8.4 using the three actual additive migrations. Deployed database identity and migration state remain part of T7.
- [x] 2026-10-03 20:19 Asia/Shanghai: T3: Permissioned policy/status/reset HTTP contracts, localized errors and all-entry request identities implemented; HTTP regression passes.
- [x] 2026-10-03 20:19 Asia/Shanghai: T4: Owner-only live setting in existing course settings; null/zero/positive limits, validation and save feedback implemented.
- [x] 2026-10-03 20:19 Asia/Shanghai: T5: Shared balance hook/message on catalog and course-update entry points; loading, failure, last-attempt, exhausted and busy states implemented.
- [x] 2026-10-07 Asia/Shanghai: T6: Focused regression tests, analytics contract, migrations and repository gates; live writer regressions included.
- [x] 2026-10-07 Asia/Shanghai: T7 core: dev02 deployment, test schema, teacher settings, two real charged retakes, exhaustion, lesson isolation and dynamic allowance verified.
- [ ] T7 extended: live TTS/failure-injection acceptance and separate diagnosis of the pre-existing Celery beat restart loop.

## Surprises & Discoveries

- Reset currently marks progress RESET and discards 2.0 sessions before the separate generation request. Charging at DELETE acceptance does not meet the successful-start contract.
- Generation runs in a producer thread. Client disconnect and producer completion differ: releasing from HTTP teardown alone could race a still-running producer.
- Engine routing documentation says simulation can share production data. Feature exposure must be deployment-local and default off; never rely solely on a shared course database flag.
- The original checkout contains unrelated custom-credit-validity changes. Do not stage, commit or overwrite them.

## Decision Log

- Approved: per-lesson quotas, course-wide teacher setting, identical new/existing learner policy, configurable limits, no shared pool or manual top-up workflow.
- Historical resets are proposed not to consume the new allowance; the first activation records the counting boundary. This is an explicit implementation assumption, still reviewable by the team.
- Proposed values: null means unlimited, zero disallows a new retake, positive integer gives extra attempts beyond first study. Updating a limit never clears usage.
- Bug reporting, per-lesson overrides, retrospective backfill, new dashboards and production rollout are out of scope.
- Use server-owned reserve -> commit/release transitions; retries share an operation identity. Pending reservations count against availability. No transaction spans model calls or generator yields.
- Test deployment must be explicitly allowlisted. The test course is requested from the user; no existing course is to be silently opted in.

## Outcomes & Retrospective

The reusable core is deployed and available for team trials on the explicitly allowlisted dev02 test course. Runtime tag 20261007-97418a6 includes both live-discovered writer compatibility fixes. Three additive migrations are installed in the verified test database. Teacher settings persist at 2; real browser acceptance proved 2 -> 1 -> 0, exhaustion, another lesson retaining 2, a temporary limit increase preserving usage, and continued learning through the next-lesson button after exhaustion. No production or source-course changes. Extended live TTS/failure-injection acceptance remains open; this test course has listen mode disabled. The pre-existing Celery beat restart loop remains separate from the demonstrated core flow. Prior full TypeScript checks still have four documented baseline errors, not a clean full pass.

## Context and Orientation

Product context: Obsidian 课程成本管理/01 课程成本管理：问题定义与方案选择.md and 02 重修次数管理：产品规则与分阶段实施.md. The server reset is learn_funcs.reset_learn_record; routes.py exposes DELETE records; runscript_v2.py owns producer execution; agent/session_store.py retains retired sessions. The learner reset button and LessonUpdateNotice share reset behavior. Teacher settings live in ShifuSetting.tsx.

## Plan of Work

T1/T2 precede public enforcement: first prove the ledger and exact producer lifecycle before wiring the UI. T3 supplies configuration and status contracts to T4/T5. T6 accompanies each implementation, followed by T7 only when verified. Preserve backward-compatible unlimited behavior for non-enabled courses.

## Concrete Steps

| Task | Deliverable | Acceptance before marking complete |
| --- | --- | --- |
| T1 | Versioned scope and task list | Per-lesson limits, exclusions, counting boundary and first-activation assumption explicit |
| T2a | Reusable rule and SQL ledger | Repeated requests, lesson isolation, limit changes, failed settlement, namespace and migration tests pass |
| T2b | Runtime lifecycle binding | Both supported runtimes prove real content commit and restoration without racing live producers |
| T3 | Permissioned policy and balance API | Only authorized course staff can configure; every reset entry checks server quota before generating cost |
| T4 | Teacher setting | Unlimited/zero/N with clear explanation; changes preserve spent opportunities |
| T5 | Learner experience | Remaining balance on confirmation, last opportunity warning, exhausted state and unaffected ongoing study |
| T6 | Regression and observability | MySQL concurrency, recovery, preview exclusion and fail-open analytics verified; repository gates pass |
| T7 | Test delivery | Correct dev02 runtime build verified and teacher/learner flows accepted on independent test course |

T2a is an implementation milestone, not a team-experience release. The first usable test delivery requires T2b–T7. Do not claim that completing the reusable foundation eliminates all rework: product wording and configuration can change, and runtime integration remains unproven. Do not ship a frontend-only counter as a shortcut.


1. Build and test the persistent policy/attempt ledger and deterministic transitions.
2. Select the exact successful-content boundary for both runtimes; restore prior progress/session on no-content failure and retain the same new round after partial success.
3. Add explicit permissioned policy mutation and learner status API, deployment allowlist and additive migration.
4. Integrate all reset paths, teacher settings and i18n; preserve existing stream semantics.
5. Define analytics before UI implementation: teacher configuration accepted, learner quota viewed/blocked, and retake terminal outcome. Payload allowlist: resource IDs, integer limits/counts, finite outcome enums. Exclude preview and user-authored content; tracking is best effort and never the quota authority. Keep existing reset events compatible.
6. Run regression and migration tests; verify actual deployed commit, page behavior and persisted rows separately.

## Validation and Acceptance

Test unlimited/zero/two, independent lessons and learners, new/existing learner rule, raises/lowers without clearing usage, repeated request, concurrent last slot, cancellation, provider failure, disconnect, delayed producer and current-round continuation. Validate reset from catalog and update notice, preview exclusion and both supported runtimes. Test TTS reuse and absence of new generation when quota is denied with a minimal live smoke, not load testing.

## Idempotence and Recovery

Use persistent unique request identities and database serialization. Preserve original worktree. Additive migrations only, no reset of existing learner rows. Deployment rollback disables exposure first, preserves ledger, and must not release a live worker's reservation blindly. Explicit deployment/course boundary is mandatory where databases may be shared.

## Interfaces and Dependencies

Policy and attempts belong to the learn service, not draft/published teaching content: changing a quota applies immediately without republishing. Define status as available, limit, used, reserved, remaining and allowed. The ledger is authoritative; Umami and browser state are not. Deployment follows established dev02/CICD, never build-latest.yml as a test deployment shortcut. User authorized a NEW test copy sourced from 048148e925a540d4af5e1efcdb2b03e1 (AI 业务操盘手的产品工程避坑课). Source was verified and exported to a temporary file without modification. Test-site device authorization completed. The new unpublished draft is c2cf49551ba94345b5a141c78d7b86e7, titled 重修功能测试｜AI 业务操盘手的产品工程避坑课. It contains six chapters and twelve lessons; exported readback matches the original Course Prompt and all eighteen outline-node contents. Course admin was opened and verified in the browser at https://cook02.dev.pillowai.cn/shifu/c2cf49551ba94345b5a141c78d7b86e7 . Source course was not modified. Local course directory is /private/tmp/retake-test-course and is temporary; re-pull the test BID if missing. Platform attributes use new-course defaults; enabling TTS, choosing runtime and learner access must be verified before acceptance. The draft is not yet published or on a retake allowlist. Live pipeline revalidation remains outstanding.


## Development Log

### 2026-10-03 19:55 Asia/Shanghai — producer ownership and atomic recovery

- Added `producer_finished_at` and `recovery_data` with a second model-generated, reviewed additive migration. Retired learning rows retain their content; snapshots store only original progress statuses and the non-preview session identity.
- `reserve_attempt(stage_reset=...)` commits quota reservation and record reset together. Repeating the same request never invokes reset again. A reset failure rolls back both.
- Bound `RunRecorder` and agent `record_turn_content` to the same accounting unit of work as their actual teaching writes. A failed transaction rolls back content and usage together. Feedback, student input and error blocks do not count.
- Wrapped the existing producer iterator. Closing the HTTP response alone cannot refund a live producer. A completed text write followed by TTS failure remains one retake; without saved teaching, producer closure restores the original progress/session and releases the opportunity.
- A committed attempt whose producer has not ended still blocks another reset. Preview, Ask and existing reload paths do not claim a pending retake. Empty first-study records cannot be reserved as a paid retake.
- Regression evidence: real SQLite progress/session/ledger tests, both writer paths, generator closure, delayed thread, duplicate producer, preserved preview session, terminal idempotency and rollback after simulated persistence failure. Existing stream-abort, session-store and agent-runtime tests are included in the focused suite.
- Local environment: reused the original checkout's installed Web tools through an ignored symlink only after confirming both package.json and package-lock.json match. No dependency pins changed.

- MySQL admission reads now use locking current reads for attempt state and balances. Merely locking the policy row cannot refresh an already-established REPEATABLE READ snapshot; the live MySQL race test remains required.

Validation command (from `src/api`, Python 3.12 with repository requirements):

```bash
python -m pytest tests/service/learn/test_retake_policy.py tests/service/learn/test_retake_ledger.py tests/service/learn/test_retake_rollout.py tests/service/learn/test_retake_execution.py tests/service/learn/test_retake_migration.py tests/service/learn/run/test_run_recorder.py tests/service/learn/agent/test_turn_storage_contracts.py tests/service/learn/agent/test_lesson_record.py tests/service/learn/agent/test_run_agent.py tests/service/learn/agent/test_session_store.py tests/service/learn/test_runscript_v2_lock.py tests/service/learn/test_runscript_v2_stream_abort_invalidate.py -q
```

Result: 254 passed. Tests invoke no paid model/TTS provider. Deprecation warnings from existing Swagger, pydub and Pydantic paths remain unchanged.

### 2026-10-03 19:57 Asia/Shanghai — checkpoint validation

- Final combined regression: 254 passed in 8.73 seconds, including both engines and existing stream/session regressions.
- Full repository pre-commit gate: passed in 40.10 seconds. An earlier run failed solely because the newly generated documentation indexes were not yet staged; staging both indexes resolved it. No lint rules or checks were weakened.
- Changes remain in the isolated `codex/lesson-retake-limits` worktree. This is a default-off backend checkpoint, not a completed teacher/learner feature. No dev02 push, schema installation or runtime deployment has been performed.

### Remaining release gates

1. Verify MySQL last-slot races before enabling a course. Current local tests use SQLite; no MySQL server or Docker runtime was available on this workstation.
2. First opt-in of an already-active course must drain all old producers before setting a policy. Producers started before the policy existed were not tracked. This test copy is unpublished, so initialize it before admitting learners. General old-course self-service rollout remains a later gate.
3. Verify deployment configuration, schema installation and browser/learner flows. No database connection or CICD mutation capability is available in the current tool set; a Git push alone is not runtime acceptance.
4. Crash repair is platform-only and relies on an operator externally confirming worker termination. It must not be invoked merely because a learner closed the browser or a timeout elapsed.

### Rollback boundary

Before exposure, keep deployment allowlist empty; the unbound hooks do not query or mutate the retake ledger. After exposure, stop new admissions and drain producers before disabling enforcement. Preserve attempt records and snapshots; reverting the new schema during live attempts would destroy recovery evidence.


### 2026-10-03 20:19 Asia/Shanghai — reusable teacher and learner workflow

- Added the third model-generated additive migration, `f5c8745b7e91`, for a per-learner/lesson producer guard. It excludes reset during first study and continuation as well as retakes. Pending retakes cannot be bypassed through reload. Preview and Ask remain outside retake accounting.
- Process-loss recovery is explicit and platform-only. Exact producer identity and an operator's confirmed stop are required; no timeout refunds. Recovery restores old records and releases the reservation atomically. Delivered content stays charged, and failed restoration leaves the guard and reservation intact.
- New owner GET/PUT `retake-policy` accepts exactly one `limit` field. GET `retake-status/<outline_bid>` returns only the authenticated learner's balance. Reset validates course/lesson membership and preview permission. Enabled courses require `X-Retake-Request-Id`.
- Both learner reset entry points use one shared allowance hook. They show remaining opportunities, a final-opportunity reminder, exhausted/busy states and a recoverable balance-load error. Confirm stays disabled until status loads; server enforcement remains authoritative when the displayed balance becomes stale.
- Browser request identities survive uncertain network responses and page refresh in session storage, scoped to learner/course/lesson/preview. They are cleared after acceptance or a confirmed released attempt. This is request deduplication, never the authoritative quota.
- Teacher settings save immediately and separately from draft publication; used attempts remain unchanged. No arbitrary initial default was added. Empty means unlimited, 0 means no additional retakes. Controls are hidden outside the rollout and for read-only viewers.
- Added translations for all eight existing locales. Defined three additive analytics events in the canonical analytics reference, with allowlisted fields, preview exclusions, per-open/per-submit deduplication and fail-open tracking.
- Validation so far: 319 backend tests (including 61 HTTP contracts), 97 frontend tests, Frontend lint passed; full TypeScript verification is qualified by the baseline errors recorded below. Extra repair and update-entry tests and the final repository gate are recorded below when complete.
- Live state remains unchanged: test copy is an unpublished draft; no source-course modifications, deployment-variable edits, live migrations or quota activation.

#### Platform repair procedure

1. Keep the affected lesson blocked. Identify its namespace/course/learner/lesson and `LessonRetakeRun.producer_id` from the deployment's database; preserve the attempt snapshot.
2. Stop or replace the owning worker and externally verify that the previous process cannot resume. Elapsed time, HTTP disconnect and a bug report are insufficient evidence.
3. In the corresponding deployment application shell call `repair_stopped_lesson_run(app, namespace=..., shifu_bid=..., user_bid=..., outline_bid=..., expected_producer_id=..., operator_bid=..., confirmed_stopped=True)`.
4. Read back the attempt, current progress/session, run completion and repair audit. No-content attempts become released with old progress restored; delivered attempts remain committed. A mismatched producer or missing original record must fail without a partial refund.
5. If the function rejects, investigate rather than deleting a guard or forcing a counter. No teacher or learner HTTP route exposes this operation.

#### Test deployment sequence

Keep `LESSON_RETAKE_SHIFU_BIDS` empty during the code rollout. Install all three additive migrations through the normal deployment process, then verify API/worker/Web commit identities and database scope. After the MySQL concurrency check, set `LESSON_RETAKE_NAMESPACE=dev02` and allowlist only `c2cf49551ba94345b5a141c78d7b86e7` in the dev02 environment group. Restart the matching workers/API as required by that deployment. Configure the still-unpublished course before opening learner access; confirm source course remains unavailable for this feature. Publish/open only the independent test copy for the authorized team trial, then exercise teacher changes and two-lesson learner balances with TTS. Never enable production or a wildcard allowlist.


### 2026-10-03 20:22 Asia/Shanghai — verification checkpoint

- Backend combined suite: 319 passed; two subsequent repair regressions also passed in the 28-test producer suite. Coverage now additionally proves delivered attempts are not refunded and missing originals roll back the entire repair.
- Frontend: 104 tests passed across seven focused suites, including both reset entry points, last/exhausted/busy messages, teacher settings, uncertain retries, identity separation and analytics failure isolation. Lint passed; the subsequent full TypeScript result is qualified below.
- The first full pre-commit run passed all semantic gates; the JSON formatter normalized key ordering and required a rerun. Formatting changes were reviewed and retained. Final gate result is recorded with the commit checkpoint.
- `origin/dev02` remains `e74ddb30a`; the feature can integrate as a fast-forward without unrelated merges. The deployment-config repository confirms dev02 uses its own CICD environment group, but does not expose a current database identity or this deployment's runtime state. No available CICD/SQL tool was found in the session.


### 2026-10-03 20:28 Asia/Shanghai — legacy regeneration boundary and baseline correction

- Inspection found that legacy inline refresh and answer resubmission still rewind learning and generate content, despite removal of the paragraph regeneration control. Configured courses now reject non-Ask reload parameters on the server before touching progress or invoking providers. The two legacy UI actions preflight the policy before truncating content or stopping an active stream, then explain how to use the lesson retake. Preview, Ask, ordinary continuation and unconfigured courses retain their behavior. This deliberately keeps one counted regeneration unit in the pilot: the whole lesson.
- UX limitation for team review: legacy inline failure retry on an enabled course also goes through the whole-lesson/recovery path. Do not claim a new free paragraph repair feature. Verify first-study empty-output retry and interrupted-stream continuation during live acceptance; if that path cannot resume safely, do not enable the course until it is repaired.
- Added a narrowly scoped analytics event for blocked legacy regeneration, with no content or errors. Tests cover preserving current content, keeping a running stream alive, exact payload, failed policy lookup, and tracking failure. Backend tests prove reload parameters cannot invoke the underlying generator or debit a retake.
- Corrected the earlier TypeScript status: `npm run type-check` reports four errors, two in the existing operations-user page tests and two in `markdown-flow-locale.ts` for installed-library locale types. Exporting untouched `e74ddb30a` into `/private/tmp/retake-baseline-types` and using the same installed dependencies reproduces exactly those four errors. No new retake type error was found. This is not a clean full TypeScript pass, and unrelated files/dependencies were not changed to hide it.
- Intermediate full repository gate passed after JSON ordering was normalized (39.12 seconds). Changes made after that checkpoint are covered by the final rerun below.


### 2026-10-03 20:30 Asia/Shanghai — final local acceptance

- Final backend combined run: 323 passed (9.00 seconds). Final frontend combined run: 180 passed across eight suites (9.97 seconds).
- Full `lefthook run pre-commit --all-files`: passed (39.75 seconds), including architecture, transaction boundaries, translations, analytics-producing frontend lint and repository harness. No rules or tests were disabled.
- Full TypeScript checking: four unchanged baseline errors, with no new retake errors. The baseline comparison is documented above; do not represent this as a clean full type check.
- The release remains default-off. The next checkpoint records the exact commit and dev02 push separately from runtime deployment/activation.


### 2026-10-03 20:32 Asia/Shanghai — dev02 push receipt

- Implementation commit: `c1cdd118f1441e607bb495346e600539989ed676` (`feat: let teachers manage retakes for each lesson`), following backend checkpoint `e46d3fd12`.
- `git push origin HEAD:dev02` succeeded as a fast-forward from `e74ddb30a`; independent `git ls-remote origin refs/heads/dev02` returned the exact implementation commit above.
- No forced push, main change, production release, rollout-variable update or course publication was performed. The original checkout's unrelated changes remain separate.
- Browser readback confirmed access to the independent test-course editor. That page access does not identify the deployed commit or validate the new retake workflow.
- Remaining delivery gates: MySQL last-slot/concurrent-first-study tests, actual CICD build and deployment identity, migration installation/database scope, explicit course-only enablement, first-study failure/continuation behavior, and teacher/learner browser acceptance with TTS. The current session has no callable CICD or SQL control tool; do not claim the feature is enabled or ready for the team to experience.


### 2026-10-03 20:56 Asia/Shanghai — MySQL and failed-study continuation evidence

- Installed MySQL 8.4.11 as a development dependency and started a temporary server bound only to 127.0.0.1:13307, using a separate temporary data directory. No production/test application database was accessed. No persistent service was enabled.
- Added opt-in `test_retake_mysql_concurrency.py`. It refuses non-loopback URLs and URLs naming an application database, creates a random test schema, applies all three actual migrations, then drops only that schema. Five cases passed under REPEATABLE READ: concurrent last-slot requests, identical request replay, a stale snapshot after the last slot is spent, concurrent first-study ownership, and policy reduction after an ORM snapshot.
- Reproduction: `RUN_LOCAL_MYSQL_RETAKE_TESTS=1 MYSQL_RETAKE_TEST_ADMIN_URI=mysql+pymysql://root@127.0.0.1:13307 python -m pytest tests/service/learn/test_retake_mysql_concurrency.py -q` from `src/api`, against the explicitly isolated temporary server. The URI is local-only test access, not application credentials.
- Clarified the earlier retry limitation: legacy inline refresh is regeneration; reopening a lesson loads durable history and starts normal continuation with no reload parameters. Added two frontend regressions for reopening failed first study with empty or saved history while the course has zero retakes. Both preserve this existing path; saved teaching remains visible. The complete hook suite passes 78 tests.
- Added a backend producer regression: a no-content first-study failure releases its producer guard; a later continuation succeeds with zero allowance and creates no retake attempt. The producer suite passes 31 tests. These checks prove orchestration/accounting, not a real model/TTS recovery in the deployed application. Live acceptance must still exercise that path. No new paragraph repair feature was introduced.
- The current session has no CICD, SSH or SQL deployment control capability. GitHub exposes no deployment receipt for the pushed commit; this is not evidence that independent CICD failed. Browser readback of the test-course settings still has no retake control. Requested the deployment console entry or CICD connection while finishing independent verification.
- Required dev02 configuration remains exactly `LESSON_RETAKE_NAMESPACE=dev02` and `LESSON_RETAKE_SHIFU_BIDS=c2cf49551ba94345b5a141c78d7b86e7`, merged into the existing environment group after schema/runtime checks. No wildcard, code hardcoded activation, or shared database switch is an acceptable substitute.
- Status: code previously pushed; local concurrency and continuation evidence complete; actual deployment identity, test-course activation/publication, and live teacher/learner/TTS acceptance remain unverified. Source course and production remain untouched.

- Follow-up release gate: `check_dev_tools.py` and full `lefthook run pre-commit --all-files` passed. The temporary MySQL schema count returned zero after fixture cleanup; the temporary server was shut down successfully.

### 2026-10-05 14:03 Asia/Shanghai — fix false allowance-query failures

- Reproduced the learner's disabled reset confirmation on the supplied dev02 test-course URL. Opened only the confirmation dialog; did not submit a reset or change learning records.
- Root cause in `src/web/src/api/retake.ts`: the shared request layer already unwraps `{code, data}`, but all three retake wrappers accessed `.data` again. Successful allowance/policy responses became `undefined`; the learner hook threw while reading `available` and displayed the query-failed state, while the teacher policy control stayed hidden. Missing rollout configuration alone does not explain this failure.
- Removed the second unwrap from policy read, policy save and allowance read. Actual HTTP/business failures still reject; no fail-open quota bypass or arbitrary unlimited fallback was added. Existing event names, eligibility and server enforcement remain unchanged.
- Added API regressions using the real shared request layer and mocked HTTP responses, rather than mocking the retake API itself. Before the fix: three success-path tests failed with `undefined`, one business-error test passed. After the fix: 26 tests passed across API envelopes, shared request, learner allowance and teacher settings. Enabled and unconfigured course responses are both covered.
- This corrects the earlier diagnosis boundary: the UI can show “query failed” even when the network request succeeds. Browser reproduction plus executable request-contract tests establish the client defect; deployment activation and database state are separate checks.
- Next: complete required checks, push the focused fix to dev02, and revisit the supplied URL after deployment. Do not claim runtime repair from local tests or a push alone.
- Verification: full pre-commit gate passed. TypeScript still reports exactly the four previously documented baseline errors in operations-user tests and markdown-flow locale typing; no retake error was added. No checks were disabled.


### 2026-10-05 — teacher-first configuration delivery plan

- Approved: the teacher saves a per-lesson allowance before enforcement/accounting starts; no historical debit. The independent test course will use 2 extra retakes per lesson for acceptance.
- [x] Clarify persisted teacher state separately from unsaved input: unconfigured, unlimited or saved numeric limit; expose policy-load failure rather than silently hiding it.
- [x] Add teacher policy-load analytics, define its safe contract before implementation, and test failure isolation and stale-response exclusion.
- [x] Verify no allowance before configuration, first save at 2, consumption, per-lesson independence and later increases/reductions preserving usage.
- [x] Run checks and push only this work to dev02 (55aeb1d3188e0df19a3302ce3846901c81ad0b09).
- [x] 2026-10-06: Obtain CICD access, verify runtime/schema, install the three additive test-database migrations and merge the exact dev02 namespace/course allowlist. Runtime activation and UI acceptance follow separately.
- [x] 2026-10-07: Saved 2 through teacher UI; verified real charges 2 -> 1 -> 0, exhausted admission, second-lesson isolation and adjustment preserving usage.

No new schema or counter reset is planned. Existing deployment isolation remains; environment configuration is a platform responsibility, never a teacher task. Keep source course and production untouched. Roll back UI-only additions by reverting this focused commit; preserve existing ledger and running producers.

- Local evidence for teacher-first follow-up: 19 frontend tests and 44 backend tests passed. TypeScript reports only the same four documented baseline errors. The JSON formatter normalized key order on the first complete gate; no rules were weakened. Runtime activation is still blocked on the deployment entry; the user approved 2 as the test allowance but has not supplied that entry.


### 2026-10-06 23:43 Asia/Shanghai — deployed schema and course-only configuration

- Native CICD MCP now works. Project 4 is ai-shifu/ai-shifu@dev02; all four services use build 318 / image tag 20261005-55aeb1d. This is actual runtime evidence, independent of the earlier Git push.
- Environment group dev02 is used only by this project's API, worker, beat and web. It originally had 195 entries / 63 secrets and no retake rollout variables.
- A temporary read-only API deployment preflight found database agi-sifu-test at revision fde432bceab4, with all three retake tables absent. Deployment record 1595 stopped at pre_script before replacing the existing service, as intended.
- Inspected the three additive migrations and the CICD pre-hook implementation. A guarded migration script asserted the actual application database name and host match the dev02 environment, and the exact prior revision. It ran Flask-Migrate upgrade to f5c8745b7e91 and verified the resulting revision and tables. Record 1596 succeeded. No existing learning tables or learner rows were reset.
- Restored the API pre_script to its original empty value immediately after migration. No permanent operational hook was added.
- Merged only LESSON_RETAKE_NAMESPACE=dev02 and LESSON_RETAKE_SHIFU_BIDS=c2cf49551ba94345b5a141c78d7b86e7. Readback: 197 entries / 63 secrets, all 195 original entries unchanged. No production, SIM, source-course or wildcard activation.
- Requested redeployment of the same image for project 4 so all four services receive the merged environment. Completion, teacher save at 2, learner balance, charged retakes and exhaustion are not yet verified at this checkpoint.
- Pre-existing issue observed before changes: dev02 Celery beat had 3069 restarts. Filtered logs showed repeated initialization but no explicit exception; do not attribute this to retake changes without further evidence.


### 2026-10-06 23:49 Asia/Shanghai — activation and live compatibility defect

- Deployment queue 319 completed successfully: API 1597, beat 1598, worker 1599, web 1600. Teacher settings now show the retake control. Saved 2 through the real owner UI; readback says the setting is effective. Learner confirmation shows 2 remaining.
- The first real reset was rejected with retakeNotStarted despite visible persisted teaching. No quota was consumed. This is a newly observed acceptance defect, not a completed end-to-end delivery.
- Reproduced the contract gap with the real MarkdownFlow 2.0 stage_turn_block writer: it leaves role=0, while the new retake recovery predicate required ROLE_TEACHER=1. Two new regression cases failed before the fix. The writer now sets ROLE_TEACHER explicitly; the reader also admits historical role=0 content turns with an empty source block ID, while retaining type, nonempty content, active status, progress and learner/course filters. Student, error, empty and source-backed unknown-role blocks remain excluded. No bulk data rewrite or additional schema change.
- 74 focused tests pass, including the actual writer, historical compatibility, negative eligibility, accounting, restoration and legacy recorder. Runtime deployment of this compatibility fix and charged/exhausted acceptance remain pending.


### 2026-10-06 23:57 Asia/Shanghai — real legacy writer accounting correction

- Commit 00832ea759c491018b8da40d2571a434ed5e9217 built as CICD build 321 / tag 20261006-00832ea; automatic deployment records 1601-1604 completed. A real retake generated new teaching, but balance incorrectly stayed at 2.
- A read-only aggregate diagnostic for this test course (record 1605) proved one released attempt, no active producer, and persisted role=0/type=311 teaching rows. It did not print learning content or learner identifiers. The temporary worker pre_script was restored to empty afterward.
- Corrected the earlier engine-only diagnosis: the legacy MDF init_generated_block factory also leaves teaching role unset. RunRecorder therefore skipped settlement and the producer treated the delivered turn as empty. The recorder now normalizes only type=311, empty-source-block, unset-role teaching before committing it and its retake charge in the same transaction. Student/error rows remain excluded. The historical reader compatibility covers both generation paths.
- Added two real legacy-factory regressions (staged/unflushed and preflushed); both failed before the fix. No learner counters were manually rewritten. The incorrectly released trial remains evidence of the bug; the next two successful retakes must charge normally before declaring acceptance.


### 2026-10-07 00:07 Asia/Shanghai — core experience acceptance

- Commit 97418a6a88f2d754f81a996c1973a69c8e9d3df3 was pushed and remotely verified on dev02. The automatic push did not initially create a build receipt; manually triggered Drone 5113 for the verified branch. CICD build 322 / image tag 20261007-97418a6 succeeded. All deployment records 1606-1609 succeeded and all four services report that image.
- 127 focused tests and the complete repository pre-commit gate passed for the final accounting correction. Both transient diagnostic/migration pre_scripts were restored to their original empty values.
- Real owner UI saved 2 and retained it after reload. Changed 2 -> 3 -> 2 once before consumption to verify settings propagate.
- Real learner account on this test course performed two successful new retakes of lesson 49627b510d2d4147b691b77d8bb6fd13. Balance moved 2 -> 1 -> 0; the last-attempt message appeared; the exhausted confirmation disabled its submit button. Lesson 1ed48134e959487986ab5d012ecb85a1 still showed 2.
- After two charges, changing the teacher limit to 3 exposed exactly 1 remaining opportunity on the first lesson. Restored the teacher limit to 2; historical usage was retained.
- With no retakes left, selected the existing learning interaction, received further teaching, and reached the next-lesson button. Reopening reset still showed exhaustion. Thus the limit did not block completion of the current learning round.
- Test state intentionally retained: this browser learner's first lesson has used 2; the second lesson has 2 remaining. No manual counter reset was used. Screenshots: /private/tmp/retake-teacher-enabled.png, /private/tmp/retake-last-chance.png, /private/tmp/retake-exhausted.png. Teacher and learner browser tabs are retained as deliverables.
- Limits of evidence: live acceptance used reading mode; listen mode was disabled in the test course, so TTS and real provider-failure recovery are not claimed verified. Celery beat continues restarting (3 restarts observed after the final image), while API, worker and web reported zero restarts. Handle that infrastructure issue separately rather than masking it in retake changes.

### October 8 verification before deployment

- Fixed-ten backend regression: 121 passed. Frontend regression: 183 passed (including both reset entrances, learning logic and teacher settings).
- Real loopback MySQL: six concurrency tests passed, including two learners activating an unconfigured course at once. Combined MySQL/ledger/recovery run: 64 passed. Applied only the existing migrations to disposable random schemas; no business DB writes.
- First activation now uses MySQL INSERT ON DUPLICATE KEY UPDATE before any missing-row lock, avoiding concurrent gap-lock insert deadlocks. Existing policy row serializes later admission; counters are not cleared.
- Full TypeScript check reproduced only the same four baseline errors in operations-users tests and markdown-flow-locale; no new errors. Complete repository gate passed before final MySQL amendment and is rerun before commit.
- Added only LESSON_RETAKE_GLOBAL_ENABLED=true to the dev02 environment group using merge. Original values and secrets remain; actual activation requires new containers. Production/SIM untouched.

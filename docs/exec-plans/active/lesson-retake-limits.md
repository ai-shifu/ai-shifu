# Per-lesson retake limits: reusable test-environment core

## Purpose / Big Picture

Deliver a real, reusable per-learner, per-lesson retake capability, initially enabled only for explicitly selected test courses. Teachers configure one limit for every lesson, learners see remaining opportunities, and the server owns enforcement. No production deployment is authorized by this task.

## Progress

- [x] 2026-10-03 Asia/Shanghai: Re-read approved Obsidian scope and current learning code.
- [x] 2026-10-03 Asia/Shanghai: Fetched origin/dev02 and created isolated codex/lesson-retake-limits worktree from e74ddb30a; original dirty checkout preserved. No source .env files existed at the three standard locations.
- [x] 2026-10-03 Asia/Shanghai: T1 task breakdown and default-off rollout contract recorded; no historical debit is an explicit reviewable assumption.
- [x] 2026-10-03 Asia/Shanghai: T2a reusable rule/SQL ledger and deployment namespace isolation implemented; focused tests pass.
- [x] 2026-10-03 19:55 Asia/Shanghai: T2b-1: Bind actual producer iteration and both durable teaching writers to the ledger; add atomic reset snapshots and failure restoration. Focused offline database tests pass.
- [ ] 2026-10-03 19:55 Asia/Shanghai: T2b-2: Finish admission/reset integration and MySQL concurrency validation, including an already-running first-study producer and process-loss recovery. Do not enable the test course before these release gates pass.
- [ ] 2026-10-03 Asia/Shanghai: T3: Implement policy persistence, migration, permissioned API and all-entry enforcement.
- [ ] 2026-10-03 Asia/Shanghai: T4: Add teacher configuration to existing course settings.
- [ ] 2026-10-03 Asia/Shanghai: T5: Add learner balance, last-attempt and exhausted states to all reset entry points.
- [ ] 2026-10-03 Asia/Shanghai: T6: Focused regression tests, analytics contract, migrations and repository gates.
- [ ] 2026-10-03 Asia/Shanghai: T7: Integrate dev02, verify independent deployment and perform browser plus database acceptance on selected test course.

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

In progress. The producer and actual legacy/2.0 content writers now have default-off hooks, with durable recovery snapshots. The HTTP reset endpoint, permissioned configuration API and teacher/learner UI remain unchanged; no live retake attempts can be created through the product yet. The final focused persistence/runtime suite passed 254 tests, including 22 execution/recovery cases. Ruff checks passed. The full `lefthook run pre-commit --all-files` gate passed after staging the generated document indexes. Existing unrelated frontend/deprecation warnings remain. SQLite migration round trips passed; MySQL concurrency and live migration remain unverified. No runtime deployment or existing learner data mutation. The independent test-course draft from the previous milestone is unchanged.

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

1. The current reset API has not been changed. Wire it only after atomically excluding a still-running first-study/continuation producer; a Redis response-status flag alone is insufficient because HTTP teardown can precede producer exit.
2. Process death can leave a pending attempt. Never auto-refund merely on elapsed time. Implement a fenced recovery or explicit platform repair path with proof that the producer has stopped before enabling live use.
3. Map rule outcomes to localized API errors and implement authorization, stable request identity, learner balances and teacher settings together. No generic server error should become the normal exhausted-state experience.
4. Verify MySQL last-slot races, test deployment configuration, schema installation and learner flows. Passing SQLite tests is not evidence of test-environment deployment.

### Rollback boundary

Before exposure, keep deployment allowlist empty; the unbound hooks do not query or mutate the retake ledger. After exposure, stop new admissions and drain producers before disabling enforcement. Preserve attempt records and snapshots; reverting the new schema during live attempts would destroy recovery evidence.

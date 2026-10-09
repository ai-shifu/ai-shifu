# Keep native usage classification inside an application scope

## Purpose / Big Picture

A completed MarkdownFlow 2.0 model response must not turn into an unknown error
when its native producer records usage for a course absent from the demo cache.
Preserve ordinary-course billing and built-in demo exemptions for both LLM and
TTS recording without changing request-owned transactions.

## Progress

- [x] 2026-10-09T04:05:00Z: Reproduce the production failure in cold demo
  classification. Both production regions have been rolled back to 1.0;
  deploy-config #37 was merged with both engine flags explicitly false.
- [x] 2026-10-09T04:15:00Z: Add seven regressions. Before the fix, all six
  native LLM/TTS course cases fail; the caller-transaction regression passes.
  After the fix, metering, billing and demo suites pass 1,681 tests with ten skips.
- [x] 2026-10-09T04:23:00Z: Learning/profile/user/shared LLM tests pass
  4,243 tests with one skip and four subtests; repository gates pass. Sim build
  444 / Drone 5235, deployments 2120/2121, both API replicas match 38 hashes.
  Fresh demo start/answer complete without errors; one 2.0 session has two turns
  and two real exempt usage records.
- [x] 2026-10-09T04:24:00Z: CI identifies a new test's model-registration
  dependency on other collected modules. Isolated execution reproduces it;
  register the course model before fixture schema creation.
- [ ] Re-run isolated recording tests and final CI after the test-only correction.
- [ ] Open the source PR, inspect CI and respond to every AI review opinion.
  A human merges the PR before production image rollout and re-enablement.

## Surprises & Discoveries

The model response succeeds before its usage recorder raises. Classification
precedes autonomous usage persistence, so that persistence scope cannot protect
the earlier cold configuration and course queries. A warm metadata cache masks
the failure. CI also exposed that test-local model imports occurred after fixture
schema creation; collecting demo tests first masked that setup defect locally. Production read-only reproduction fails without a context and
returns the expected demo exemption inside the existing app-context helper.

## Decision Log

- Bound only the classification read with `app_context_scope(app)`. Reuse an
  existing caller session; end a temporary native scope before autonomous writes.
- Keep the fix in the shared recorder so both LLM and TTS callers benefit.
- Preserve billing defaults, settlement enqueue rules, schemas and dependencies.
- Keep both production flags false until the corrected image is verified.

## Outcomes & Retrospective

The focused regression establishes that cold native classification and real usage
persistence work for ordinary, title-recognized demo and configured demo courses.
Production activation remains pending; passing health probes alone did not catch
this error, so fresh-learner streaming acceptance is required for reactivation.

## Context and Orientation

`src/api/flaskr/service/metering/recorder.py` owns usage classification and
autonomous persistence. `service/shifu/demo_courses.py` reads configuration and
course rows on cache misses. The engine's model bridge runs on a native thread
without a Flask request context. `flaskr/dao/uow.py` owns the reusable scope helper.

## Plan of Work

Wrap the shared classification lookup with the existing helper, add real SQLite
native-thread recording and caller-rollback regressions, and verify the deployed
sim tree before preparing production rollout. This work does not change the
separate teaching-attempt attribution follow-up.

## Concrete Steps

1. Run the metering, billing and demo tests from `src/api` in conda `ai-shifu`.
2. Run learning, profile, user and shared provider regressions and repository gates.
3. Push a focused source PR and its exact tree to sim; inspect the deployed image,
   recorder hash and fresh learner's normal streaming response and usage rows.
4. Audit reviews, inline comments and issue comments; reply in original threads.
5. After human merge, verify the production image before a separate versioned
   flag-only configuration update and actual regional streaming acceptance.

## Validation and Acceptance

Cold native LLM/TTS calls persist billable ordinary usage and exempt demo usage,
enqueue settlement only for billable rows and leave no thread context behind.
Classification must not commit or replace a caller session or fire its callbacks
after caller rollback. Sim must complete fresh built-in demo start and answer
without SSE errors, with real 2.0 session and exempt usage records.

## Idempotence and Recovery

No database migration or data repair is required. Tests use isolated SQLite data.
Production rollback is the versioned `FLOW_ENGINE_V2_ENABLED=false` setting in
both regions; preserve unrelated live configuration drift when applying flags.
Never reset learners or fabricate engine checkpoints during rollout.

## Interfaces and Dependencies

Reuse `app_context_scope`, `UsageContext`, the shared recorders and existing demo
classification. No new dependencies, environment variables, public APIs, billing
semantics or memory-scope contracts are introduced.

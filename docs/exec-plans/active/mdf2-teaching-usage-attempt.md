# Attribute teaching usage to the actual learning attempt

## Purpose / Big Picture

MarkdownFlow 2.0 teaching, teaching-summary and memory-admission usage must
identify the same learning attempt and generated block as the streamed turn.
Fresh sim acceptance previously found seven teaching records with course and
lesson IDs but no attempt ID, while follow-up usage was already complete.

## Progress

- [x] 2026-10-09T04:47:00Z: Trace the missing IDs to models constructed before
  `run_agent_lesson` opens the active progress record and generated block.
- [x] 2026-10-09T04:50:00Z: Six attribution variants fail with empty attempt
  and block IDs before the fix. Bind all three models after opening each turn
  and before starting its native producer; 208 focused tests pass, including
  first/resumed turns, previews, independent learners and failure cleanup.
- [x] 2026-10-09T06:21:00Z: Related learning, profile, user, shared API,
  metering, billing and demo suites pass 5,498 tests with 11 skips and four
  subtests. Full repository pre-commit gates pass.
- [ ] Open a focused PR, deploy its exact tree to sim and verify fresh learner
  usage against actual progress and generated-block records. Reply to AI reviews.

## Surprises & Discoveries

`UsageContext` is immutable. Models are request-local but reused across the
host's automatic continuation turns. A one-time lookup at lesson entry cannot
identify the new attempt reliably and would miss each turn's block identity.

Before deployment, fresh sim learners reproduce the gap in both billing
categories: two exempt demo teaching records and one ordinary billable teaching
record have no attempt/block IDs, despite real progress and generated rows.

The first broad run found four lifecycle tests whose offline `FunctionModel`
replacement lacked the new gateway setter. Extend that fixture to record usage
binding and assert it against actual SQLite blocks after regeneration, changed
answers and resets; all 208 focused cases then pass.

## Decision Log

- Use the real IDs opened by the host rather than create a second progress row.
- Bind each request-local gateway before the producer starts. Snapshot the
  immutable context per turn so earlier requests retain their attribution.
- Preserve preview's unwritten progress ID, scene and learning mode. Finished
  lessons must still open no turn and perform no model call.
- No schema, billing-policy, production-configuration or memory-scope changes.

## Outcomes & Retrospective

Implementation and focused regressions are complete. Fresh sim baseline
reproduces the missing attribution; corrected-image acceptance is pending.
Production remains on its previously verified 2.0 image.

## Context and Orientation

`agent/lesson_entry.py` constructs the three gateway models and repeats host
turns. `agent/run_agent.py` opens progress and the block before invoking the
native bridge. `agent/gateway_model.py` forwards immutable usage contexts to
the shared gateway; metering persists them independently of streamed elements.

## Plan of Work

Expose a turn-opened callback on the host and a context setter on the gateway.
The entry point updates all three models from the original course/lesson/scene
context using the opened IDs. Cover lifecycle ordering and gateway-visible
contexts across turns, including previews and separate learner requests.

## Concrete Steps

1. Run focused regressions from `src/api` in conda `ai-shifu` before and after
   the fix, then run broader learning, provider, profile and metering suites.
2. Stage the plan, regenerate the knowledge index and run repository gates.
3. Push the feature branch to GitHub, create its PR, then merge its exact tree
   into the sim branch and allow the normal deployment webhook to run.
4. Verify both sim replicas and exercise a new dedicated learner through HTTP;
   read only that learner's usage/progress/block rows to confirm attribution.

## Validation and Acceptance

Every model request, including the first teaching request, carries the opened
attempt and block IDs without losing user/course/lesson/scene/mode fields.
Rebinding later turns does not change earlier contexts. Preview remains separate
from learner history; finished sessions perform no binding. Sim usage joins the
new learner's real active progress record and generated block.

## Idempotence and Recovery

No migration or historical backfill is necessary. Tests use local SQLite and
mocked providers. Sim acceptance uses a new dedicated learner through normal
endpoints. A human controls main-branch merging; existing production is untouched.

## Interfaces and Dependencies

The optional host callback receives `(progress_record_bid, generated_block_bid)`
before engine session creation or producer execution. The gateway setter accepts
the existing immutable `UsageContext`. No new external dependency is required.

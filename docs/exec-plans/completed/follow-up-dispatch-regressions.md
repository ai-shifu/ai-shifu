---
title: Verify follow-up dispatch through the lesson caller
status: completed
owner_surface: learner
last_reviewed: 2026-10-08
---

# Verify follow-up dispatch through the lesson caller

## Purpose / Big Picture

Close the caller-level Ask routing gap deferred from CodeRabbit review 5442852102
on PR 3031. A follow-up must keep its inserted sidecar even when the deployment
teaches with 2.0. Protect the request boundary with tests; no runtime behavior,
provider, database, environment or frontend changes are needed. The durable
contract is [MarkdownFlow Runtime Selection](../../references/markdownflow-runtime-selection.md).

## Progress

- [x] 2026-10-08 01:41 UTC: Verify PR 3037 merged, final technical CI passed,
  and both production regions match the accepted sim runtime. Archive its plan.
- [x] 2026-10-08 01:43 UTC: Inspect the real caller and add 16 permutations of
  deployment flag, delivery mode, preview and anchor presence. Guard the agent
  entry, sidecar request arguments, event forwarding and context ownership.
- [x] 2026-10-08 01:43 UTC: Focused routing/history/provider/Live regression
  passes 374 tests. The caller-bypass mutation fails all eight enabled Ask cases
  while disabled cases pass; restore the exact runtime bytes.
- [x] 2026-10-08 01:46 UTC: Gates passed; publish PR 3038 at df5f5a79e and
  synchronize initial sim 512fc4aee. Reply on PR 3031 with the implemented
  deferred coverage and pushed commit.
- [x] 2026-10-08 01:51 UTC: Accept Devin producer-normalization finding. Add
  eight real run_script/background-producer cases with actual caller/config,
  sidecar anchor/adapter, semaphore isolation, app context and terminal SSE.
  Focused regression including lock/disconnect contracts passes 415 tests;
  removing listen normalization fails four listening cases. Preserve runtime bytes.
- [x] 2026-10-08 02:07 UTC: Revised gates passed, final 0da03d393 pushed and original
  Devin thread replied with commit/tests. Final sim 100d9f6ae passed dual-pod probes;
  technical CI passed and CodeRabbit reviewed final head with no code changes.
  Every independent opinion was replied to. PR 3038 merged at 02:02:08 UTC;
  main acd8ae4cd matches accepted sim. Build 381 and deployments 1864-1871 succeeded,
  both regions passed 57 isolated checks/18 hashes and retained engine 1.0.

## Surprises & Discoveries

The earlier test proves only the predicate excludes Ask. It cannot detect a
caller that ignores the predicate, which is the deferred review's specific risk.
Existing general argument forwarding tests stub the runtime configuration and
use normal teaching inputs, rather than actual Ask under the environment flag.
Devin also identified that direct listen=True caller cases bypass the public
producer, which always normalizes Ask to listen=False. Retain those as defensive
function-boundary tests and add real public-entry/background-producer coverage.

## Decision Log

- 2026-10-08: Use the real configuration and caller. Stub only downstream
  engine entries; fail immediately if Ask enters the teaching agent.
- 2026-10-08: Check anchored and unanchored requests in both delivery modes and
  preview states. Do not change the production runtime to satisfy a test.

## Outcomes & Retrospective

Implementation is test-only. Revised focused regression passes 415 tests. The
caller-bypass mutation fails eight enabled direct cases; removing producer
normalization fails four real listening cases. Runtime bytes are unchanged.
Final publication, sim/CI, review replies and merged production verification
are complete. Source trees match; no runtime behavior changed.
Full follow-up quality, shared memory writes, recall/compression and independent
human acceptance remain separate work in the workspace milestone plan.

## Context and Orientation

`runscript_v2._teaches_with_agent` reads the deployment flag and excludes Ask.
`_lesson_events` dispatches to the agent or `run_script_inner`, the existing
inserted follow-up path. `test_lesson_routing.py` already covers normal teaching,
regeneration and fallback. This increment exercises the missing Ask caller.

## Plan of Work

Add focused caller tests, demonstrate failure if the caller bypasses the Ask
exclusion, restore source, run provider/history/Live regressions and all gates.
Publish a focused PR and synchronize sim. Record any review in its original
thread with pushed fixes and tests; keep merging main under user control.

## Concrete Steps

1. Run the routing, history, provider and Live-entry test modules from `src/api`.
2. Temporarily bypass the predicate at the caller, run the new cases and restore
   the exact runtime bytes in a `finally` block.
3. Run the developer-tool check and all pre-commit gates, then commit and push.
4. Verify sim code identity and isolated probes; inspect final CI and reviews.

## Validation and Acceptance

All 16 direct Ask combinations select only the sidecar and preserve exact
arguments and ordered events. Eight real public-entry producer cases normalize
listen=False while preserving learning mode, anchor and adapter. They retain
Ask semaphore isolation and terminal SSE without changing active lesson status. A caller that routes enabled Ask directly to the agent must
fail the enabled combinations. Existing adjacent regressions and repository
gates pass. The deployed sim runtime matches the already accepted PR 3037 code;
production stays on 1.0. Every independent AI opinion receives a reply.

## Idempotence and Recovery

Tests use no database or provider. The mutation restores original bytes even
on failure. Runtime files must have no committed diff. The PR is independently
revertible; deploying or reverting it does not modify learner data or routing.

## Interfaces and Dependencies

Use the existing config, `_lesson_events`, `run_script_inner`, agent entry and
pytest monkeypatch fixture. Add no dependency, schema, API or environment key.

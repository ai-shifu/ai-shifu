---
title: Verify follow-up dispatch through the lesson caller
status: active
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
- [ ] 2026-10-08 01:43 UTC: Pass repository gates, publish one PR, synchronize
  sim, verify its unchanged runtime and final CI, and reply to all AI opinions.

## Surprises & Discoveries

The earlier test proves only the predicate excludes Ask. It cannot detect a
caller that ignores the predicate, which is the deferred review's specific risk.
Existing general argument forwarding tests stub the runtime configuration and
use normal teaching inputs, rather than actual Ask under the environment flag.

## Decision Log

- 2026-10-08: Use the real configuration and caller. Stub only downstream
  engine entries; fail immediately if Ask enters the teaching agent.
- 2026-10-08: Check anchored and unanchored requests in both delivery modes and
  preview states. Do not change the production runtime to satisfy a test.

## Outcomes & Retrospective

Implementation is test-only. All 374 focused tests pass; bypassing the caller
exclusion fails eight enabled cases. Runtime bytes are unchanged. Repository
gates, publication, review and sim rollout are pending.
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

All 16 Ask combinations select only the sidecar and preserve exact arguments
and ordered events. A caller that routes enabled Ask directly to the agent must
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

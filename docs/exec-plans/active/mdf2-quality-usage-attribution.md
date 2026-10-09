# Attribute synthetic quality evaluation usage to its selected course

## Purpose / Big Picture

The opt-in memory-quality CLI validates a published lesson and temporary learner,
but its gateway factory omitted their course and lesson UsageContext. Actual
successful evaluation rows therefore had empty course/lesson IDs, preventing
course-owner settlement and hiding evaluation costs from scoped queries. Bind
all five gateway generation families to the already validated selection without
creating classroom progress or changing shared billing policy.

## Progress

- [x] 2026-10-09T11:58:00Z: Confirmed the live gap and added a CLI regression that
  fails on the missing context. Added real gateway/SQLite persistence coverage.
- [x] 2026-10-09T11:59:00Z: Bound one immutable context in the gateway factory.
  Ordinary and built-in-demo persistence tests pass for all five families.
  Removing the binding makes both integration cases fail on empty course IDs.
- [x] 2026-10-09T12:01:00Z: Related evaluator/shared gateway/metering tests pass
  (371). Isolated sim acceptance passes four selected cases, with all eleven
  actual requests scoped and settled to the correct owner (5.26 credits).
- [ ] 2026-10-09T12:01:00Z: Complete repository gates and publish a focused main PR.
- [ ] 2026-10-09T11:59:00Z: Reply to every independent AI opinion and record final
  CI, scope review and publication evidence before archiving this plan.

## Surprises & Discoveries

Thirty successful requests from the preceding exercise evaluation had no course
or lesson scope. The learner ID and generation name were present; those alone
cannot resolve the course owner. The natural classroom's separate 82-row ledger
was correctly scoped. These are different populations, not contradictory results.
The first new integration run had an invalid test settings fixture (missing
required temperature); it is not counted as a regression baseline. After fixing
that fixture, removing the production binding produced two actual regressions.

## Decision Log

- Reuse metering.api.UsageContext and the existing gateway factory; no new billing
  path, pricing, scene, billable override or administrative endpoint.
- Bind only the validated learner, course and lesson. Leave progress/block IDs
  and learning mode empty: synthetic evaluation is not a classroom attempt.
- Retain generation names to distinguish synthetic costs from natural teaching.
- Preserve built-in-demo exemption through the shared course-aware classifier.
- Do not fabricate or repair historical rows. Keep the original unscoped evidence.
- Run only isolated temporary scripts on sim, without overwriting application
  files, changing the deployment, or modifying learner/course/session state.

## Outcomes & Retrospective

Local evaluator/shared gateway/metering verification passes 371 tests. The
isolated sim run passes four selected cases, not the full catalog. Eleven actual
requests cover all five generation names, all have the real course/lesson IDs,
no fabricated classroom IDs, zero failed usage, correct settled owner and no
unsettled successful billable requests; the separate synthetic cost is 5.26
credits. The earlier 30 unscoped rows remain unchanged. A private ledger-summary
reader initially treated SQL JSON text as a dictionary; fixing that reader used
the already saved report/ledger, without another billed evaluation. The first
expanded pytest command used the repository root, where app startup cannot find
flaskr/service; rerunning from src/api passed. Repository gates/publication remain
in progress. This repairs
new evaluator usage attribution, not the unresolved natural-course exercise
statistics failure. That failure remains in the workspace MDF status and natural
acceptance record. Engine 1.0 retirement remains inventory only.

## Context and Orientation

The factory lives inside main() in src/api/scripts/evaluate_mdf2_memory.py.
GatewayModel forwards UsageContext unchanged into shared chat_llm normalization;
metering owns raw usage persistence and asynchronous settlement. CLI wiring is
covered by tests/scripts/test_evaluate_mdf2_memory.py. Real gateway/SQLite and
course-owner resolution coverage lives beside the existing entry integration in
tests/test_llm.py. The canonical evaluator contract is
[the quality reference](../../references/markdownflow-memory-quality.md).

## Plan of Work

Bind context after the existing access/model resolution, test each generation
family through the real gateway and recorder, and verify normal versus demo
billability. Compare isolated sim requests against a read-only ledger baseline,
keeping evaluation outputs and original failures private. Publish one focused PR.

## Concrete Steps

1. Add a failing CLI context assertion and real SQLite persistence regressions.
2. Add course and lesson context to the common gateway factory.
3. Run the evaluator and shared-gateway/metering tests; demonstrate that removing
   the binding breaks attribution checks, then restore the implementation.
4. Run selected synthetic cases on sim with a dedicated temporary learner;
   verify all five generation names, IDs, actual owner and settlement separately
   from semantic quality scores.
5. Regenerate knowledge indexes, run developer-tool and full pre-commit gates,
   commit with repository defaults and open a GitHub main PR without merging.

## Validation and Acceptance

All five families must persist the selected learner/course/lesson and preserve
actual request IDs and token/cache counters. Ordinary rows remain billable and
resolve the course owner; configured built-in-demo rows remain exempt. No fake
progress/block or learning-mode identity is introduced. The report still contains
no learner/course/lesson IDs or raw model output. Existing list-only and engine
1.0 refusal behavior remain intact. Live semantic results are reported separately
from usage attribution: a semantic failure must never be hidden by valid billing.

## Idempotence and Recovery

List-only invocation remains read-only and free. Every live invocation makes new
potentially billed requests; retain distinct reports rather than replacing failed
runs. Do not backfill the earlier rows. Revert the CLI change if necessary;
there is no schema/config migration or application rollout. Temporary sim scripts
can be removed without affecting the application or pending classroom state.

## Interfaces and Dependencies

Reuse the existing CLI arguments, validated published lesson lookup, immutable
UsageContext, GatewayModel, shared chat gateway and metering/settlement contracts.
No dependencies, frontend interfaces, engine prompts, memory authorization or
engine switches change.

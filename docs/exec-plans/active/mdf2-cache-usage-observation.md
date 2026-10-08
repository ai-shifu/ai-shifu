# Provider cache usage in memory quality reports

## Purpose / Big Picture

Preserve reported provider prefix-cache token usage through the shared gateway,
the engine's diagnostic counters and serialized session reloads. Record real
summary request usage separately in the repeatable quality evaluator. These
observations prepare complete-course cache/cost testing after merged PR #3053;
they do not calculate prices or replace the shared billing ledger.

## Progress

- [x] Inspected the shared usage extractor, streamed gateway, engine counters
  and summary evaluator. The adapter drops cache counts, the engine retains
  only three totals, and summary request usage is absent from the report.
- [x] Focused pre-fix regressions: seven failures / six passes in gateway and
  reload cases, plus two expected summary-report failures. Logs retained privately.
- [x] Implemented valid cache accounting and observed-subset input/read totals;
  missing, malformed and explicit-zero metadata remain distinguishable.
- [x] Summary responses are observed separately through the actual nonstreamed
  factory path. Cache reload keeps one request; injected failure records no
  provider usage. Admission responses share the same numeric accumulator.
- [x] Local learning/profile/operator regressions: 2,892 passed, one expected
  skip and four subtests passed. Developer-tool checks and all repository
  pre-commit gates passed.
- [ ] Open one focused PR and verify deployed sim reports.
- [ ] Reply to independent AI opinions in their original discussions.
- [ ] Await manual main merge and verify release selection.

## Surprises & Discoveries

Provider prefix-cache hits and the engine's semantic-summary cache are different
mechanisms. A provider that omits cache usage cannot be treated as reporting zero
hits. Teaching counters exclude the separately billed summary model, so they
cannot establish a complete lesson cost by themselves.
A native SDK cache count can exist without complete gateway coverage, so the
reported-subset numerator is retained independently from all SDK cache reads.
The local teaching model double now terminates after finish instead of reaching
the request-limit fallback; this exposes completed teaching usage in its tests
without changing production finish behavior.

## Decision Log

- Reuse the shared gateway's cache extraction conventions and actual provider
  responses. Preserve core input/output counters and existing billing/tracing.
- Retain provider-reported coverage counts and its input-token denominator;
  never invent a hit rate from unsupported or malformed metadata.
- Keep legacy sessions and unreported-cache providers compatible. Store only
  numeric diagnostic counters, never prompts, learner facts or model responses.
- Observe summary usage in the opt-in operator, including one actual request
  followed by a cache round trip. Explicit failure injection makes no model call.
- Keep system-global/course-local scope and production 1.0 routing.

## Outcomes & Retrospective

Acceptance is pending. This technical observation surface does not complete
long-term fees, natural teaching quality or human trials.

## Context and Orientation

The adapter is `src/api/flaskr/service/learn/agent/gateway_model.py`; the engine
currently sums requests/input/output in `engine/engine.py`. Session usage is a
JSON dictionary. The evaluator is `src/api/scripts/evaluate_mdf2_memory.py` and
already exercises real summaries and cache reloads in four long-history cases.

## Plan of Work

Add optional provider cache accounting without changing teaching or authorization.
Propagate observed usage through real engine reloads, expose summary request totals
separately, document interpretation and run the fixed catalog on deployed sim.

## Concrete Steps

1. Add focused gateway/session/operator regressions and retain pre-fix failures.
2. Implement bounded numeric accounting and separate summary observations.
3. Run engine, learning/profile/operator and repository-wide gates.
4. Open the PR, synchronize sim and inspect runtime fingerprints/model reports.
5. Audit all review surfaces and reply to every independent opinion.

## Validation and Acceptance

Supported object/dictionary metadata, explicit zero, unknown/invalid counts,
cumulative stream updates and mixed supported/unsupported requests must retain
accurate totals. Reload must preserve earlier counters. Summary observations must
show one real request and no second request after reload; injected failure must
not claim provider usage. Keep all existing quality assertions intact.

## Idempotence and Recovery

Use synthetic sessions and dedicated internal sim learners. Reports remain private
and uncommitted. Do not alter prices, usage rows, production switches or real
learner memory. Restore counters with existing session/checkpoint behavior.

## Interfaces and Dependencies

Reuse Pydantic AI usage objects and the shared LLM extraction conventions. No
database migration, dependency, environment or frontend change is planned.

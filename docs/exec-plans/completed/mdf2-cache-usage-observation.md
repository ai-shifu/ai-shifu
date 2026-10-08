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
- [x] Local learning/profile/operator regressions: 2,893 passed, one expected
  skip and four subtests passed. Developer-tool checks and all repository
  pre-commit gates passed.
- [x] Opened PR #3054. Adopted the shared stream-normalization review:
  four failing / six passing real-gateway regressions reproduced dropped cache
  metadata before the fix.
- [x] Final shared gateway / learning / profile / operator regressions:
  3,223 passed, one expected skip and four subtests passed; provider-boundary
  tests separately 116 passed, onboarding/operator compatibility 144 passed.
  All repository gates passed.
- [x] Runtime `f4d6b003e` / sim `cd5f1b392` trees match. Build 424 / Drone
  5215 and deployments 2044/2045 succeeded; both API replicas match 25 runtime
  fingerprints and route to 2.0, web is ready.
- [x] Deployed full catalog: 24 cases repeated three times, 72/72 passed with
  zero request errors and no candidate overrides. Read/listen completion and
  audio backfill (2.05 seconds) passed.
- [x] Adopted the posted Devin issue and replied in its original thread with
  pushed fix `f4d6b003e`, red/green regressions and billing assertions. Continue
  auditing new independent opinions and live CI/review status in PR #3054.
- [x] 2026-10-08 23:33 CST: User merged PR #3054 as `3656530e0`. The initial main webhook failed with 502; one verified redelivery started build 426 / Drone 5217. All eight deployments 2048-2055 succeeded. Both production regions match all 25 runtime hashes across eight API replicas and select engine 1.0. Complete-course attribution follow-up is tracked in `mdf2-course-usage-attribution.md`.

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
A dictionary containing an object-shaped nested usage field is unsupported by the
shared extractor; a regression keeps it unknown instead of recording mismatched
cached-token numerator and coverage metadata.

The initial adapter-only tests missed that `chat_llm` normalizes usage into a
three-field DTO. The shared stream now carries optional raw cache metadata through
that DTO, preserving explicit zero and missing/invalid values. The billing numeric
conversion is unchanged. Tests invoke the actual chat gateway and adapter while
stubbing only the provider, and verify both diagnostic counts and billed totals.

A combined custom test order loaded the existing LiteLLM stub before provider
boundary tests and caused two missing-`token_counter` fixture errors. Those
boundary tests passed in their separate process; the remaining combined suite
passed. No unrelated stub behavior was changed.

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

Deployed runtime acceptance passed. The real report contains 162 admission /
recall / teaching requests plus nine separately observed summary requests, all
with cache metadata. The nine summaries consume 9,684 input / 446 output tokens;
summary cache reload creates no second request. Three injected failures contain
no summary provider usage. The warmed synthetic catalog is not a fresh-cache
baseline or complete-course cost measurement.

The production-image/browser runtime CI run 37796516528 passed for the runtime
commit. Live final checks and subsequent AI replies are tracked in PR #3054;
the user manually merged main as `3656530e0`, and production routing remains 1.0 after runtime verification. Final documentation synchronization
preserves the tested runtime files and can reuse this model/HTTP evidence after
verifying image fingerprints. This technical observation surface does not complete
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

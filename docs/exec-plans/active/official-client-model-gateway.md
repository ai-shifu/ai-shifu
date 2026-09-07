---
title: Official Client Model Gateway
---

## Purpose / Big Picture

Provide official clients with account-backed model access through the existing
AI-Shifu device authorization, LLM wrappers, usage recorder, and asynchronous
credit settlement. Keep course learning and client calls on the same billing
lifecycle. Client-side applications remain outside this repository.

## Progress

- [x] 2026-09-01: Added account, model-list, and OpenAI-compatible chat endpoints,
      tests, and the external CLI integration guide.
- [x] 2026-09-05: Added client allowlisting and review fixes for request bounds,
      stream typing, token estimates, localization, and persistence-safe IDs.
- [x] 2026-09-05: Superseded the gateway-specific reservation design at the
      user's request. Restore the legacy reservation service and usage recorder
      to the PR base; reuse course admission and asynchronous settlement.
- [x] 2026-09-05: Resolve server-marked, course-less gateway usage to the
      authenticated account without changing course/debug ownership.
- [x] 2026-09-05: Verify gateway-to-recorder-to-worker behavior, no hold/release
      entries, duplicate requests, legacy compatibility, and full regression.
- [x] 2026-09-05: Full backend run passed 3789 tests with 16 skips and 46
      passing subtests; the final 48 gateway route/integration checks also pass.

## Surprises & Discoveries

- Existing production settlement normally resolves a course owner through
  shifu_bid; a gateway record needs a narrowly scoped server-generated source
  marker so the same worker can resolve the signed-in user's wallet.
- Existing usage rows already index request_id, so completed-request
  deduplication needs no schema change.
- A shared cache claim provides bounded in-flight deduplication independently
  of financial ledger state.
- The existing recorder intentionally uses best-effort persistence and
  asynchronous enqueue; gateway-specific suppression and capture were
  unnecessary once the lifecycle was aligned with course learning.

## Decision Log

- Reuse existing device authorization and session tokens; no client registry,
  scopes, wallet-owner abstraction, or schema changes.
- Reuse admit_creator_usage, record_llm_usage, billing.settle_usage, and existing
  rate calculation. Do not reserve a worst-case request amount.
- Stamp production LLM usage with extra.billing_source = model_gateway on the
  server. Only course-less gateway records use user_bid for settlement.
- Preserve complete model-rate eligibility, JSON/SSE/tool output, request bounds,
  and the client ID allowlist.
- Retain a 90-character caller key, derive a stable internal request ID, and
  reject duplicates via existing usage plus a 24-hour atomic shared-cache claim.
- Failed/interrupted calls follow the existing non-billable/failed-usage path;
  do not preserve a separate gateway partial-failure charging rule.
- Design reservations and recovery for course learning and gateway access
  together in a future change. Earlier reservation/capture decisions in this
  branch are superseded, not deployment requirements.

## Outcomes & Retrospective

The intended final change exposes gateway APIs and reuses shared admission and
asynchronous billing. It removes this PR's changes to operation_credits.py and
the shared recorder. The remaining ownership extension is gated to trusted
gateway-source production LLM usage without a course ID.

## Context and Orientation

Gateway HTTP behavior lives in flaskr/route/model_gateway.py; request admission
and deduplication live in model_gateway_runtime.py. LLM wrappers record usage
through flaskr/service/metering/recorder.py. Existing billing/admission.py,
ownership.py, charges.py, and settlement.py own the shared billing rules.

## Plan of Work

1. Remove gateway holds/capture/release and restore their shared-service changes.
2. Use existing admission, source-marked usage, and normal settlement enqueue.
3. Keep duplicate-request protection independent of wallet mutations.
4. Replace reservation-specific tests with async integration and compatibility
   coverage, and update design/client documentation.

## Concrete Steps

Run focused gateway, ownership, admission, settlement, metering, and LLM tests.
Verify operation_credits.py and recorder.py match the PR base. Regenerate
documentation indexes and translation types, then run repository hooks and
the full backend suite.

## Validation and Acceptance

- An admitted model request changes neither available nor reserved credits.
- A successful response records one usage and queues the existing settlement.
- Running that settlement charges the signed-in account once, with no hold or
  release entries; course and debug ownership tests remain unchanged.
- Admission rejects unavailable credits according to course policy.
- Duplicate keys reject concurrent or recorded requests without wallet writes.
- Ordinary failures and interrupted streams do not enqueue failed usage.
- Existing voice-clone reservation code and the common recorder match main.
- No tables, columns, indexes, migrations, or application CLI are introduced.

## Idempotence and Recovery

The shared worker owns settlement idempotency and replay/backfill. Cache guards
expire after 24 hours; persisted usage request IDs continue blocking reuse while
retained. Cache loss during an unrecorded request and best-effort usage/enqueue
failures remain operational limitations. No credit holds need gateway recovery.
Concurrent admissions can exceed the later available balance, as with courses.

## Interfaces and Dependencies

The five device/account/model endpoints, Bearer header, client ID header, and
Idempotency-Key contract remain. Dependencies are existing Flask, LiteLLM,
SQLAlchemy, shared Redis, usage recording, and the billing worker. Balance
refresh is eventually consistent with asynchronous settlement.

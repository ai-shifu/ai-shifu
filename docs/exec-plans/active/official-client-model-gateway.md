---
title: Official Client Model Gateway
---

## Purpose / Big Picture

Expose AI-Shifu's existing account, model routing, and credit wallet to official
clients through one OpenAI-compatible gateway. Reuse the Course CLI browser
device authorization flow and preserve the current database schema. The main
repository owns server implementation and tests; a production application CLI
belongs in a separate project and follows the checked-in integration guide.

## Progress

- [x] 2026-09-05: Fix PR review findings on persistence-safe idempotency,
      concurrent reservations, output-token estimation, failed-call billing,
      settlement cleanup, request bounds, localization, and the plan index.
- [x] 2026-09-05: Verify 1025 billing, metering, LLM, gateway, configuration,
      and device-authorization regression tests (10 skipped); full backend
      validation is also run after aligning the local markdown-flow dependency.

- [x] 2026-09-01 15:00 CST: Revalidated current device authorization, user
      sessions, LiteLLM routing, operation reservations, usage records, and the
      earlier Desktop experiment against the latest remote main branch.
- [x] 2026-09-01 15:20 CST: Added strict LLM estimation, partial capture with
      unused-credit release, and focused billing tests without schema changes.
- [x] 2026-09-01 15:35 CST: Added Bearer-authenticated account, models, and Chat
      Completions routes with JSON, SSE, and tool-call coverage.
- [x] 2026-09-01 15:45 CST: Added the architecture decision and external CLI
      integration guide without adding an application CLI to this repository.
- [x] 2026-09-01 15:48 CST: Completed 114 focused and regression tests, Ruff
      0.16.5, architecture, repository harness, route registration, whitespace,
      and no-migration checks; live provider/account E2E remains deployment work.

## Surprises & Discoveries

- The current device flow already has browser approval, one-time collection,
  request expiry, rate limiting, host binding in the Course CLI, and revocable
  user sessions. Replacing it with OAuth/OIDC would not improve the official-only
  first version enough to justify new tables and client migration.
- The global Flask token extractor does not accept the standard Authorization
  header. Gateway routes must bypass that extractor and validate Bearer tokens
  explicitly while still calling the shared `validate_user` service.
- Existing operation credits reserve and capture complete holds. Exact LLM
  settlement only needs an additive optional capture amount and same-transaction
  release; it does not need a new wallet, request table, or migration.
- The local backend virtual environment had stale Langfuse and LiteLLM packages.
  Synchronizing them to `requirements.txt` restored current test collection
  without modifying dependency pins.

## Decision Log

- PR review: derive a deterministic 36-character internal request ID from the
  account and caller key; retain the original key in hold metadata. Do not
  change persistence schemas or shorten the documented 90-character limit.
- PR review: retry metered settlement once on failure, then attempt release
  with explicit failure logging. Database failures must not trigger maximum
  reservation capture or escape stream finalization.
- PR review: limit gateway chat bodies to 1 MiB, message arrays to 256, and tool
  arrays to 128 before tokenization; require a JSON boolean for stream.
- PR review: TLS enforcement belongs to the trusted deployment edge, where TLS
  terminates; do not trust arbitrary forwarded headers in Flask as proof of TLS.
- PR review: a stale-hold sweeper needs an active-request lease and a bounded
  provider lifecycle first. Do not release possibly active paid calls solely
  based on hold age. Hard process termination and persistent DB failures still
  require operational reconciliation.

- Decision: reuse `/api/user/device/*` and the current AI-Shifu session token.
  - Why: the first audience is official clients, and Course CLI compatibility
    is more valuable than premature standard-client infrastructure.
- Decision: keep `creator_bid` throughout wallet code and compare it directly
  with the authenticated `user_id`.
  - Why: a wallet-owner abstraction or schema rename adds no first-version
    behavior.
- Decision: require complete input, cache, and output rates before advertising
  or invoking a model.
  - Why: preauthorization and exact capture cannot be guaranteed for a partly
    rated model.
- Decision: require `Idempotency-Key` and reuse ledger uniqueness.
  - Why: this prevents duplicate reservation and charge without a gateway
    request table.
- Decision: keep the production CLI outside this repository.
  - Why: the server repository should own protocol contracts and tests, not a
    second end-user application lifecycle.

## Outcomes & Retrospective

PR review fixes cover nine actionable inline findings. Provider-rate identity
consistency is verified by regression tests without changing the shared resolver:
both admission and persisted usage use the application provider mapping, and
unmapped models cannot invoke a provider. TLS enforcement remains at the trusted
public edge. Model-list caching and age-based hold sweeping are deferred rather
than introducing stale-rate or active-request-release risks in this PR.

The implementation is intentionally additive: three gateway endpoints, shared
LLM wrapper extensions, partial credit capture, tests, and documentation. No
database model or migration is added. Seventy-three LLM tests, twenty-six
gateway/billing/metering/Swagger tests, and fifteen existing device authorization
tests pass. Ruff 0.16.5, formatting, architecture boundaries, repository harness,
route registration, and whitespace checks pass. A live billable provider call
was not made because it requires a designated account, wallet, rates, and real
provider credentials in a deployment environment.

## Context and Orientation

Device authorization lives in `flaskr/service/user/device_auth.py`. Model
providers and token metering live in `flaskr/api/llm/__init__.py`. Credit holds,
wallet buckets, and ledger capture live in
`flaskr/service/billing/operation_credits.py`. The gateway route layer owns the
cross-domain orchestration so lower services remain independent.

## Plan of Work

1. Extend operation reservations to estimate complete LLM rates and capture an
   actual amount while releasing the unused remainder atomically.
2. Let gateway calls assign a usage BID and suppress the normal asynchronous
   settlement enqueue so one usage record cannot be charged twice.
3. Add OpenAI-compatible LLM wrappers for raw non-streaming and streaming
   payloads, including tool-call chunks and provider usage.
4. Register account, models, and Chat Completions routes with explicit Bearer
   validation and OpenAI-shaped HTTP errors.
5. Document the protocol for a separately maintained official application CLI.

## Concrete Steps

1. Add focused billing tests for complete rates, partial capture, release
   breakdown, and metered usage capture.
2. Add focused LLM tests for input counting, output limits, raw JSON/SSE, usage
   persistence, and tool-call preservation.
3. Add route and runtime tests for authentication, account/model shapes,
   idempotency, credit errors, provider failure, and SSE completion.
4. Register the gateway under `/api/gateway` and keep device routes unchanged.
5. Generate repository knowledge indexes and run formatting, Ruff, architecture,
   migration-head, and focused pytest checks.

## Validation and Acceptance

- Existing device authorization tests pass without Course CLI changes.
- Missing, invalid, expired, and revoked Bearer tokens cannot enter gateway
  business logic.
- A non-teacher user with a matching wallet can call a rated model; a missing
  or insufficient wallet stops before provider work.
- Model listing includes only available allowlisted models with complete rates.
- JSON, SSE text, and SSE tool-call payloads retain OpenAI-compatible shapes.
- One request creates one hold, one usage record, one consume entry, and at most
  one unused-reservation release entry.
- Repeated idempotency keys do not call the provider or change the wallet twice.
- No Alembic revision, table, column, or index is added.
- The CLI guide is sufficient to implement login, credential storage, account,
  model listing, JSON chat, SSE chat, tool calls, and error handling externally.

## Idempotence and Recovery

Authorization codes remain one-shot under the existing device flow. Model
request idempotency uses the existing operation ledger key. Capture and release
helpers return the existing terminal result on repeated settlement attempts.
Provider failures before output release the hold; completed or partially visible
responses settle from the persisted usage record, with conservative fallback
when exact provider usage is unavailable.

## Interfaces and Dependencies

- Existing auth: `/api/user/device/authorize`, `/api/user/device/token`, and the
  `/login/device` browser page.
- New account: `GET /api/gateway/account`.
- New model list: `GET /api/gateway/v1/models`.
- New inference: `POST /api/gateway/v1/chat/completions`.
- Authentication: `Authorization: Bearer <AI-Shifu session token>`.
- Idempotency: required `Idempotency-Key` on Chat Completions.
- Existing dependencies: Flask, LiteLLM, Langfuse, SQLAlchemy, wallet buckets,
  usage records, and credit ledger entries.

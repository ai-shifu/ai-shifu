---
title: Route OpenAI text generation through the Responses API
status: active
owner_surface: backend
last_reviewed: 2026-11-13
---

# Route OpenAI text generation through the Responses API

## Purpose / Big Picture

Use Responses for supported OpenAI text generation across AI-Shifu. GPT-6.1
Sol requires that endpoint for course tools. Learning, authoring, background
jobs and the model gateway share one transport policy. The gateway keeps its
[Chat Completions contract](../../references/model-gateway-cli-integration.md)
for desktop and CLI clients.

## Progress

- [x] 2026-11-13 07:24 UTC: Audit outgoing OpenAI calls, proxy paths, model
  limits, unsupported request options and the runtime harness.
- [x] 2026-11-13 07:24 UTC: Exercise the local Responses sidecar with pinned
  LiteLLM 1.109.1. Streamed text, tool arguments, terminal usage and the full
  interaction and finish replay work.
- [ ] 2026-11-13 07:24 UTC: Finish shared routing, focused tests and PR
  [#3407](https://github.com/ai-shifu/ai-shifu/pull/3407) verification.
- [ ] 2026-11-13 07:24 UTC: Verify deployed app behavior and provider
  credentials per region. Then enable GPT-6.1 Sol for US Quality and verify
  the course, gateway and billing behavior.

## Surprises & Discoveries

- US and US-dev share a transparent OpenAI proxy that forwards
  `POST /v1/responses`. Live US credentials completed a Responses request.
  The CN proxy forwarded the request and returned an upstream 401 without credentials. This establishes CN path forwarding, with authenticated
  generation still pending.
- The pinned bridge does not preserve `stop`, `seed`,
  `frequency_penalty`, or `presence_penalty` on Responses. Its OpenAI
  adapter would raise a requested output limit below 16 to 16 without explicit routing.
- A Responses tool result may carry an array of text parts. The runtime
  harness must replay both that shape and plain text to advance a lesson.
- The US production database has exact GPT-6 Sol rates of 0.0006666700
  credits/token for input, cache and output. GPT-6.1 Sol currently resolves to
  wildcard rates of 0.0002000000. An available model can still match wildcard
  rates.

## Decision Log

- Route by AI-Shifu's resolved provider key. Other providers can use LiteLLM's
  OpenAI adapter and retain their existing transport.
- Keep Responses as the default for supported OpenAI text and image input.
  Use Chat Completions for models that only support that endpoint and for
  incompatible options when the model supports Chat with the requested
  features. Return an explicit error when neither endpoint can preserve the
  request. Select the endpoint before sending the request.
- Request `store=false` and preserve existing tool strictness, history,
  physical model IDs and metering. Keep model discovery on `GET /v1/models`.
  Embeddings, moderation, dedicated image generation, TTS, transcription and
  Realtime are outside the shared text transport.
- Keep the US Quality slot numbered 3. Preserve its existing credit policy by
  adding exact new-model rates before switching the slot. Retain the old rates
  for rollback and historical settlement.

## Outcomes & Retrospective

Local wire and replay verification passed for the deterministic sidecar.
Application PR validation and US production acceptance are tracked separately.
The deployed US Quality slot still uses GPT-6 Sol.

## Context and Orientation

`src/api/flaskr/api/llm/__init__.py` owns stream and nonstream provider
invocation and usage accounting. Gateway routes use that module while
serving Chat Completions JSON and SSE. `scripts/harness/interaction_model_stub.py`
simulates the model provider through `OPENAI_BASE_URL`. The US runtime
ConfigMap and rollout live in [deploy-config](https://github.com/ai-shifu/deploy-config).

## Plan of Work

Use the shared LiteLLM bridge for capable models. Cover generation, tool
argument deltas and returned tool results, structured output, and usage
without changing consumers. Then verify the candidate image through the
configured proxies before promoting the US Quality model.

## Concrete Steps

1. Run the focused LLM, gateway, learning interaction and harness tests.
   Check the actual LiteLLM request path and the Chat-compatible result.
2. Run repository checks and update PR #3407 for maintainer review and merge.
3. Verify the candidate image with an authenticated request through each
   OpenAI proxy in use. Run a US tool round trip with the running app and
   check stream completion and metering.
4. Confirm the three exact US production rates using the application's rate
   selector. Update the US slot and its token limit maps. Roll the API, Celery
   worker and beat, then read back the effective model and public Quality
   multiplier.

## Validation and Acceptance

For a capable OpenAI model, confirm `POST /v1/responses` for streamed and
nonstreamed text generation, with function-call history, stable call IDs,
tool arguments, finish reasons, structured output and final token usage.
Confirm the explicit Chat or error behavior for incompatible requests and
check a non-OpenAI provider. Verify gateway response and usage contracts.
US production acceptance requires ready replicas using `gpt-6.1-sol`,
a successful interaction and a Quality multiplier of 10x. Record authenticated
CN acceptance once working credentials are available.

## Idempotence and Recovery

Add only missing, verified US rate rows. If the Quality switch fails, restore
the prior model ID and token limit maps, and roll the same workloads. Keep
both sets of rates for usage already recorded. If the shared transport fails
independently of the model switch, restore the prior application release.

## Interfaces and Dependencies

The application uses pinned LiteLLM 1.109.1. The configured OpenAI base URL
must forward `/models`, `/responses`, and `/chat/completions` under its API version prefix.
Reference the [OpenAI migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[function calling guide](https://developers.openai.com/api/docs/guides/function-calling)
and [GPT-6.1 Sol model contract](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

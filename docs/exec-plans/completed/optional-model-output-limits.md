---
title: Optional model output limits
status: completed
owner_surface: backend
last_reviewed: 2026-09-27
canonical: false
---

## Purpose / Big Picture

Allow an eligible gateway model to run without explicit output-limit configuration
or a complete LiteLLM catalogue entry. Preserve authentication, routing, rates,
credit admission and shared asynchronous usage settlement. Deployment configuration
is outside this task. The durable parameter contract lives in
[Model Gateway CLI Integration](../../references/model-gateway-cli-integration.md).

## Progress

- [x] 2026-09-27 UTC: Read repository/backend instructions and synchronize main.
- [x] 2026-09-27 UTC: Inspect preparation, registration and both completion paths.
- [x] 2026-09-27 UTC: Implement shared optional-ceiling lookup and gateway fallback.
- [x] 2026-09-27 UTC: Add regression coverage; 471 relevant backend tests pass.
- [x] 2026-09-27 UTC: Complete repository gates and review the final diff.
- [x] 2026-09-27 UTC: Follow-up: preserve provider defaults for omitted/null tokens
  and verify both modes, known/unknown ceilings and streaming retries.
- [x] 2026-09-27 UTC: Unify gateway and learning output-token resolution,
  remove gateway-specific defaults flags and validate 752 relevant tests.

## Surprises & Discoveries

The gateway rejected absent metadata before invoking the provider. Shared streaming
already tolerated lookup exceptions, but trusted zero, negative and malformed
metadata. Non-streaming forwards the prepared gateway value directly. Registration
already tolerates empty configuration and registration failures; GPT capability
registration must stay independent of output limits.

## Decision Log

- 2026-09-27 UTC: Initially retained the historical 4096 gateway default. User
  clarification supersedes this: omitted/null values must use provider defaults.
  Reject explicit values above a known positive integer ceiling.
- 2026-09-27 UTC: Unknown ceilings accept positive integer caller values without
  imposing an invented model maximum. Provider constraints still apply.
- 2026-09-27 UTC: Preserve course streaming behavior: apply a known ceiling and
  omit the option when neither a ceiling nor a caller value exists.
- 2026-09-27 UTC: Reuse current HTTP validation/error and billing contracts.
- 2026-09-27 UTC: Unification follow-up: both surfaces should use the same
  output-token resolver. The user chose the learning default policy: known
  ceilings are defaults and unknown ceilings leave the option omitted. This
  supersedes the prior gateway-only provider-default policy. Explicit invalid
  or excessive values are rejected by the shared resolver in both surfaces.
  Learning calls previously clamped excessive values or replaced invalid values
  when a ceiling existed; these now fail before provider invocation. Normal
  learning calls omit this option and retain their default behavior.

## Outcomes & Retrospective

Implemented optional ceilings without changing the gateway billing contract.
The first combined run passed 471 tests covering LLM
wrappers, provider boundaries, gateway routes/runtime, actual asynchronous billing,
metering, admission/ownership, and course model selection. Native LiteLLM 1.102.0
uses mocked HTTP for both completion modes without output metadata, including real
token counting and usage normalization. All-file lefthook checks, developer-tool
validation, architecture boundaries and repository harness pass. Existing audioop
and Pydantic deprecation warnings remain. Local LiteLLM and MarkdownFlow had to be
aligned to their existing requirements pins before the full selection could pass.
No production call or deployment was performed or required for acceptance.
The intermediate provider-default follow-up passed 502 tests. The final shared
policy supersedes that default and passes 752 tests: both learning entry points
and both gateway modes use known ceilings by default and omit unknown limits.
Streaming retries retain the resolved default. All four completion entry points
reject invalid/excessive explicit values before provider invocation. Native
mocked HTTP confirms no max_tokens/max_completion_tokens field is sent for null
gateway values when metadata is unknown, for OpenAI and DashScope. Additional
learning context, ask-provider and agent-adapter regressions pass. Existing
course defaults remain intact; no gateway-specific output policy flag remains.

## Context and Orientation

`src/api/flaskr/api/llm/__init__.py` owns provider routing, optional output metadata,
streaming, non-streaming and usage recording. `model_gateway_runtime.py` prepares
requests and performs admission. Gateway routes own authenticated catalog eligibility
and resolve `ai-shifu-default` before request preparation.

## Plan of Work

Share optional ceiling lookup between gateway validation and streaming. Verify
configured routed IDs take precedence over stripped provider model metadata. Add
known/unknown limits, explicit/default values and failure boundaries to tests, and
exercise the actual preparation-to-completion chain with usage recording.

## Concrete Steps

1. Modify the LLM wrapper and update the canonical gateway contract.
2. Run targeted provider, LLM and gateway tests using the local virtual environment.
3. Run development-tool validation, repository harness and lefthook gates.
4. Review scope and move the verified plan to completed.

## Validation and Acceptance

Both completion paths reach a mocked provider for missing metadata, preserve
valid caller/default values and record actual usage. Known limits remain enforced;
invalid values, unavailable models, missing rates, credit failure and provider
failure retain their existing boundaries. Existing gateway/auth/billing regressions
and repository checks pass.

## Idempotence and Recovery

Tests use isolated state and mocked provider responses. No schema, credentials,
environment files or deploy-config changes are needed. Revert the scoped commit
to restore the earlier metadata requirement.

## Interfaces and Dependencies

`resolve_llm_max_output_tokens(model, requested)` uses a shared resolver that
returns a valid explicit value, a known ceiling for omitted/null input, or None
when neither is available. The same resolver prepares learning streams, gateway
streams, gateway preparation and non-streaming completions, with no policy flag.
Its metadata lookup is optional. No new package or environment
variable is introduced. Existing LiteLLM registration and billing APIs stay intact.

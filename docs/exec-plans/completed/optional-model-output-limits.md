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
Follow-up validation passes 502 tests. Omitted/null gateway values stay absent
for known and unknown ceilings in both modes and across pre-content stream retries.
Native mocked HTTP confirms no max_tokens/max_completion_tokens field is sent for
null gateway values by OpenAI and DashScope. Existing course defaults remain intact.

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

`resolve_llm_max_output_tokens(model, requested)` returns a positive integer for
an explicit valid request and `None` for omitted/null values. Preparation omits
the option in the latter case, and gateway streaming disables implicit ceiling
defaults across retries. Its metadata lookup is optional. No new package or environment
variable is introduced. Existing LiteLLM registration and billing APIs stay intact.

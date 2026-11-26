---
title: Upgrade LiteLLM to 1.109.1 and retire covered compatibility code
---

## Purpose / Big Picture

Upgrade the shared backend SDK to the latest stable release. Use native LiteLLM
behavior where it preserves the existing provider requests and responses.

## Progress

- [x] 2026-11-13 11:53 CST: Verified the latest release in PyPI and GitHub and
  started from the current `origin/main` revision.
- [x] 2026-11-13 12:01 CST: Installed the full CI requirements in a clean
  Python 3.11 environment without MCP, and cross-resolved Linux requirements.
- [x] 2026-11-13 12:02 CST: Compared all 31 previous overrides in 462 cases
  and the eight Z.AI removals together in 540 cases.
- [x] 2026-11-13 12:04 CST: Removed the MCP extra, eight Z.AI overrides,
  and the global asyncio runner patch. Verified the native Responses bridge
  and streaming log execution in the clean environment.
- [x] 2026-11-13 12:05 CST: Confirmed that affected Gemini Flash requests
  omit unsupported sampling fields and that other Gemini models keep them.
  All 404 focused backend tests passed on the final SDK.
- [x] 2026-11-13 12:09 CST: Passed the full backend suite on the final code
  with real Redis for Gemini Live admission. Verified the dependency,
  architecture, Ruff, and repository harness checks.

## Surprises & Discoveries

- Upstream [#45961](https://github.com/BerriAI/litellm/pull/45961) defers the MCP
  gateway import for ordinary tools. The MCP extra was added solely to work
  around that import in the previous SDK.
- The [Z.AI adapter](https://github.com/BerriAI/litellm/blob/v1.109.1/litellm/llms/zai/chat/transformation.py)
  now declares `response_format`. The
  [OpenAI transport](https://github.com/BerriAI/litellm/blob/v1.109.1/litellm/llms/openai/openai.py)
  now sends provider request bodies without forcing vendor extensions through
  the OpenAI SDK's parameter signature.
- The macOS arm64 wheel matched the SHA-256 published by PyPI. Linux x86_64
  CI and Linux arm64 runtime requirements resolve with published wheels.
- [LiteLLM's Gemini adapter](https://github.com/BerriAI/litellm/pull/47645)
  now rejects sampling parameters for models that Google ignores them on.
  Course settings can supply temperature on every request.
- Removing the MCP extra reduced the resolved CI environment from 170 to 164
  packages. Pydantic AI still uses `httpx2` and its `httpcore2` dependency.
- The old/new comparison covered 228 request cases across five providers.
  Course `json_object` behavior stayed intact. For Z.AI models without
  native schema support, the SDK now translates a gateway `json_schema`
  request to `json_object` plus a schema prompt. This fallback does not
  enforce the schema at the provider. Z.AI GLM-5.3 requests that previously
  failed on the vendor thinking argument now reach HTTP.

## Decision Log

- Pin [1.109.1 on PyPI](https://pypi.org/project/litellm/1.109.1/) exactly.
  Use the [release notes](https://github.com/BerriAI/litellm/releases/tag/v1.109.0)
  and the installed SDK to identify candidates. Remove a provider override only
  after the real SDK preserves the request contract without it.
- Use native Z.AI structured output and disabled thinking for GLM 4.6,
  4.7, 4.7 Flash, 5, 5.1, 5 Code, and 5.2. Keep the six GLM 4.5 exceptions:
  the SDK does not advertise thinking controls for these model IDs.
- Keep the remaining model and provider overrides because deleting them
  changes wire behavior. The async Router's continuation feature does not
  replace the application's pre-output retry and cancellation rules.
- Remove the process-wide `asyncio.run` replacement added for gevent. The
  API uses Gunicorn gthread and LiteLLM runs synchronous streaming log work on
  its own thread. Verify that logging runs while the consumer owns an active
  event loop without replacing Python's runner.
- Omit sampling kwargs only when the Gemini adapter declares them
  unsupported. Preserve configured sampling for other models and leave
  validation of unrelated parameters with the SDK.

## Outcomes & Retrospective

The SDK is pinned to 1.109.1. The upgrade removes the MCP extra, eight
provider overrides, and the process-wide asyncio workaround. Gemini requests
remain compatible with saved course settings. The backend suite finished with
16,313 passing and 20 skipped, with real Redis enabled. Provider contract
tests used mock transports. No provider traffic or deployment was needed.

## Context and Orientation

`src/api/requirements.txt` is shared by backend CI and the Docker build.
`src/api/flaskr/api/llm/__init__.py` owns routing, request preparation,
streaming, and usage. See the
[1.106.2 audit](../completed/litellm-1-106-upgrade.md) for why the existing
workarounds were retained.

## Plan of Work

Resolve the pinned requirements on Python 3.11. Compare request preparation
with and without each candidate override, including caller-supplied controls
that could conflict with the product minimum. Preserve application-specific
routing, retries, cancellation, usage, and tracing.

## Concrete Steps

Install `src/api/requirements-ci.txt` into an isolated Python 3.11 environment.
From `src/api`, run the LLM provider-boundary and real SDK contract tests first,
then the complete backend suite. Use the repository checks before committing.

## Validation and Acceptance

- Normal Responses requests with function tools work with MCP unavailable,
  both with and without streaming.
- Retired patches preserve provider wire fields, output, and usage under
  mocked HTTP transports.
- Dependency resolution and the backend suite pass on Python 3.11.

## Idempotence and Recovery

The tests use mock HTTP responses and dummy credentials. If a removed rule
changes the provider contract, restore that rule independently.

## Interfaces and Dependencies

This change upgrades the LiteLLM Python SDK. Public API DTOs and provider
environment variables keep their existing contracts.

---
title: Upgrade LiteLLM to 1.106.2 and assess redundant compatibility code
---

## Purpose / Big Picture

Upgrade the backend from LiteLLM 1.102.0 to the newest available stable release,
1.106.2, while preserving minimum thinking, structured output, streaming, tools,
and billing. Compare each application compatibility patch with native SDK
behavior and remove only code whose product contract the SDK now supplies.

## Progress

- [x] 2026-10-23 09:40 CST: Fetched `origin/main` and created
  `sunner/upgrade-litellm-1-106-2` from the clean current revision.
- [x] 2026-10-23 09:42 CST: Verified PyPI and the official GitHub release list;
  selected 1.106.2 and excluded the withdrawn, compromised 1.107.0 artifacts.
- [x] 2026-10-23 09:46 CST: Installed the complete requirements and CI tooling
  in isolated Python 3.11.17; `uv pip check` and `pip check` passed.
- [x] 2026-10-23 09:48 CST: Compared all 31 compatibility rows in 444 scenarios,
  then compared the four removable allowlist fields in 84 wire-level scenarios.
- [x] 2026-10-23 09:49 CST: Removed GPT-6 Sol/Luna metadata injection and four
  DashScope GLM reasoning allowlists; retargeted the real SDK contract.
- [x] 2026-10-23 09:53 CST: Passed the complete backend suite (12,711 tests,
  107 skips, 50 subtests), then the final 448-case focused suite including
  eight real-SDK Responses requests. Dependency, Ruff, repository harness,
  architecture, and development-tool checks passed.
- [x] 2026-10-23 09:54 CST: Recorded the assessment, prepared the ready PR
  description and validation evidence, and archived the implementation plan.

## Surprises & Discoveries

- The checkout's `.venv` links to a shared environment containing 1.102.0.
  Use an isolated environment under `/private/tmp` to avoid changing other work.
- LiteLLM 1.106.2 requires `packaging>=24.0` and `PyYAML>=6.0.3`, while the
  existing direct pins are 23.2 and 6.0.1. Raise both to the required minimum.
- The official [October 21 incident report](https://docs.litellm.ai/blog/security-incident-oct-21-2026)
  identifies 1.107.0 as compromised and removed; 1.106.2 precedes that release.
- The inspected macOS ARM wheel matches PyPI SHA256
  `cc778d01ed65a8dd57d5211d581ec237e06df239a09c3d573ace33e0feea76c9`.
  All 3,778 RECORD entries verified; no `.pth`, `cook`, or `sitecustomize`
  files were present. Seven core source files match the official release tag.
  PyPI's provenance endpoint was unavailable; these checks are not an
  independent signature verification.
- An initial combined test order loaded the lightweight LiteLLM stub before
  provider-boundary tests, causing missing `token_counter` failures unrelated
  to native SDK behavior. Running provider boundaries first loads the real
  SDK; the 447-case combined suite then passed.
- A real OpenAI Pro completion exposed a new SDK import regression:
  `responses.main` imports the MCP gateway handler before checking whether
  tools need it. Base LiteLLM lacks the `mcp` dependency, so the request fails
  before HTTP. The same network-disabled request reaches HTTP under 1.102.0.
  The official `[mcp]` extra restores that path without FastAPI or proxy extras.

## Decision Log

- Pin the latest available stable release exactly; do not use a floating pin or
  a prerelease. Primary sources are [PyPI](https://pypi.org/project/litellm/1.106.2/)
  and the [official release](https://github.com/BerriAI/litellm/releases/tag/v1.106.2).
- Require actual adapter and wire-body evidence before deleting an exception.
  Capability metadata alone cannot establish provider request compatibility.
- Keep this PR focused on the dependency upgrade and compatibility code it
  supersedes. Record other cleanup candidates with their required validation.
- Remove the Sol/Luna capability shim because the SDK now includes their exact
  catalogue entries. Preserve configured output-limit registration and verify
  capabilities and actual requests after a native catalogue refresh.
- Remove only `allowed_openai_params=["reasoning_effort"]` from the four
  DashScope GLM-5.3 patches. Native DashScope now declares this parameter.
- Preserve Gemini 3.7/3.8 exact rows: native `none` now maps to the same `low`
  thinking level but sets `includeThoughts=false`, while current rows use
  `includeThoughts=true`. Deleting them would change reasoning observability.
- Use `litellm[mcp]==1.106.2` to satisfy the SDK's unconditional Responses
  imports. Add native stream and non-stream Responses coverage so ordinary
  Pro calls cannot regress behind optional-parameter-only tests.

## Outcomes & Retrospective

The backend now pins `litellm[mcp]==1.106.2`, with only the necessary packaging
and PyYAML minimum-version increases. The complete backend suite passed with
12,711 tests, 107 skips, and 50 passing subtests; the final focused suite passed
448 tests, including the new eight-request Responses contract. All native
requests used mock transports and dummy credentials; live provider availability
and deployment are outside this code-upgrade validation.

No complete compatibility rule was redundant. The verified deletions preserve
the existing request and observation contracts. The assessment is:

| Code | Assessment and evidence |
| --- | --- |
| GPT-6 Sol/Luna metadata injection | Removed: native catalogue supports `none`; configured caps and catalogue refresh preserve it. |
| Four DashScope GLM reasoning allowlists | Removed: native support yields identical optional parameters, HTTP bodies, stream content, and usage across 84 cases. |
| Qwen/Silicon disabled thinking | Retained: provider-wide overrides are still needed; native generic reasoning parameters do not replace these wire values. |
| Ark/ZAI response-format allowlists | Retained: SDK supported-parameter lists still omit the required structured-output parameter. |
| Thirteen ZAI model thinking patches | Retained: top-level thinking still reaches the OpenAI client incorrectly; `extra_body` is required. |
| Four GLM minimum-effort values | Retained: native capability fallback does not enforce the same `low` product minimum. |
| Three Gemini minimum-effort rows | Retained: 3.7/3.8 thought visibility differs; 2.5 Pro still needs a nonzero thinking budget. |
| OpenAI Pro/Astra minimum-effort rows | Retained: native capability defaults do not enforce the same minimum levels; actual Responses requests additionally need the SDK's MCP extra. |
| Stream retries, cancellation, repeated-chunk handling | Retained: direct `completion` does not perform Router fallback, and app rules forbid replay after text or tool output. |
| Global `asyncio.run` workaround | Retained pending separate gevent integration proof: the SDK still calls it directly in a logging path. |
| Routing, discovery, token limits, metering, Langfuse | Retained: these implement application configuration and business contracts; tokenization already delegates to LiteLLM. |
| `invoke_llm` / `chat_llm` overlap | Separate refactor: termination, tool-call, cancellation, span-update, and billing semantics differ. |

## Context and Orientation

`src/api/requirements.txt` pins backend dependencies. Shared provider integration
lives in `src/api/flaskr/api/llm/__init__.py`, including the versioned compatibility
table, model registration, minimum-thinking policy, stream recovery, usage, and
Langfuse reporting. `src/api/tests/test_llm.py` includes stub unit tests and a
subprocess contract that loads the real SDK and captures HTTP requests with
`httpx.MockTransport`. Gateway and learner tests cover downstream consumers.
The previous assessment is in
`docs/exec-plans/completed/litellm-1-102-upgrade.md`.

## Plan of Work

1. Verify release metadata and inspect downloaded wheel contents as data.
2. Resolve all backend requirements on Python 3.11 in an isolated environment.
3. Compare provider-wide patches, exact-model rows, and GPT-6 metadata injection
   with native 1.106.2 behavior, including conflicting caller parameters.
4. Delete only redundant behavior; update remaining version-labelled contracts.
5. Verify downstream behavior and document retained compatibility responsibilities.

## Concrete Steps

The isolated environment is `/private/tmp/ai-shifu-litellm-1-106-2`. Install
`src/api/requirements-ci.txt` there and run `python -m pip check`. From
`src/api`, run provider-boundary, LLM, Responses, OpenAI, gateway, and learner
tests, then `python -m pytest tests/ -n 2 --dist loadfile -q --tb=short`.
Regenerate knowledge indexes and run repository harness, architecture,
development-tool, Ruff, and all-files lefthook checks before committing. The
all-files run excludes the managed read-only `.codex/**` and `.agents/**`
surfaces and uses `--no-stage-fixed`; all checks passed without unrelated edits.

## Validation and Acceptance

- The real SDK contract runs under exactly 1.106.2, without a version skip.
- Provider requests preserve the minimum-thinking and JSON response contracts,
  stream content, usage, tools, and caller conflict handling.
- Deleted patches have equivalent native behavior under the upgraded SDK.
- The complete dependency set resolves and passes dependency checks.
- Relevant downstream tests and repository checks pass; unrelated changes are
  excluded. Delivery is a ready PR, never a merge into `main`.

## Idempotence and Recovery

Mock transports use dummy credentials and do not contact provider services.
The isolated test environment and inspection artifacts can be recreated.
Restore any compatibility row if its removal changes the required wire behavior.

## Interfaces and Dependencies

Public API DTOs and provider environment variables retain their contracts.
LiteLLM's official MCP extra is required by its Responses import path, even
without MCP tools. Its capability, request transformation, streaming, model registration,
and token-counting APIs are used by authoring, learning, the model gateway,
metering, and Langfuse. Application credit rates remain database-owned.

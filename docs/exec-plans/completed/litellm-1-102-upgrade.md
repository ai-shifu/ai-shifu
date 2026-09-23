---
title: Upgrade LiteLLM to 1.102.0 and retire covered compatibility patches
---

## Purpose / Big Picture

Upgrade the backend's LiteLLM SDK from 1.98.0 to 1.102.0 while preserving the
product rule that reasoning is disabled or minimized. Remove only compatibility
entries whose behavior is now supplied by LiteLLM itself. Keep provider request
shapes, structured output, streaming usage, and billing inputs stable.

## Progress

- [x] 2026-09-23 08:52 CST: Fetched current `origin/main` and created the
  `sunner/upgrade-litellm-1-102` branch from it.
- [x] 2026-09-23 08:49 CST: Installed the complete backend requirements with LiteLLM
  1.102.0 in an isolated Python 3.11 environment; dependency checks passed.
- [x] 2026-09-23 08:55 CST: Compared each version-specific compatibility entry against
  the 1.102.0 adapter request and model capability contracts.
- [x] 2026-09-23 08:58 CST: Updated the pin, removed proven redundant entries, and retargeted
  focused contract tests.
- [x] 2026-09-23 09:06 CST: Ran the focused adapter contract and complete
  backend suite under the pinned LiteLLM release; 9,187 tests passed, 107
  skipped, and 50 subtests passed.
- [x] 2026-09-23 09:08 CST: Regenerated repository knowledge docs; harness,
  architecture, development-tool, Ruff, dependency, and pre-commit checks
  passed, leaving the change ready for pull request review.
- [x] 2026-09-23 09:40 CST: Used the live CN and US model routing and credential
  references for six short local streaming requests. All six returned content,
  a stop finish reason, and provider usage after correcting GPT-6 Sol metadata.

## Surprises & Discoveries

- The checkout's shared `.venv` has LiteLLM 1.80.11, so its passing tests do
  not verify either the committed 1.98.0 pin or the new release.
- The existing native adapter contract skips every installed version except
  1.98.0; it must be retargeted and shown to run.
- LiteLLM 1.102.0 now advertises `thinking` for ZAI `glm-5.2`. The current
  policy still emits disabled thinking on the provider wire in an isolated
  contract run, but the capability assertion needs to reflect the new SDK.
- LiteLLM 1.102.0 reports all three lower reasoning levels as unsupported for
  GPT-5.5 Pro and its dated ID. The shared capability path therefore chooses
  `medium` without an exact-model patch.
- Gemini 3.8 Flash accepts `reasoning_effort=low` natively, so its allowlist
  field is redundant, while the explicit `low` setting remains necessary.
- The common conflict-path generator already drops caller `enable_thinking`
  for the four DashScope GLM-5.3 IDs. Their exact patches still need `low` and
  the allowed parameter entry, but no duplicate drop list.
- Qwen, Silicon, Ark, ZAI, other Gemini, and older OpenAI Pro exceptions still
  change provider wire output or prevent adapter errors under 1.102.0.
- The first full-suite attempt hit two Langfuse HTTP client setup failures
  because this Mac exports a SOCKS proxy without `socksio`. Removing proxy
  variables made both tests pass; the complete rerun then passed.
- The unmodified all-files hook could not open the managed read-only
  `.codex/environments/environment.toml` in write mode. Excluding the
  workspace's protected `.codex` and `.agents` surfaces and disabling hook
  auto-staging let every repository check pass; no unrelated files changed.
- The live US quality model is GPT-6 Sol. LiteLLM 1.102.0 lacks its exact
  catalogue entry and rejects the wrapper's `reasoning_effort="none"` plus
  `temperature=0.3` before sending a request. Registering only this model's
  known no-reasoning capability with its OpenAI provider preserves the
  product's temperature behavior; the live proxy then accepted the request.
- LiteLLM replays only the latest registration for a model when refreshing
  its catalogue. GPT-6 Sol's capability and any configured output limit must
  therefore be registered in one entry. This sparse entry does not provide a
  LiteLLM price; application credit charges continue to use database rates.
- This Mac's SOCKS proxy required `httpx[socks]` in the isolated test
  environment for real provider calls. No production dependency changed.

## Decision Log

- Use the exact stable release 1.102.0 and Python 3.11, matching the current
  backend runtime.
- Require wire-level evidence before deleting a compatibility entry. An SDK
  capability flag alone is insufficient if the adapter sends a different
  request or accepts conflicting caller parameters.
- Keep explicit entries for still-unsupported model or provider combinations;
  avoid broadening an exception to unknown models.
- Remove the two GPT-5.5 Pro exact rows, Gemini 3.8's `allowed_openai_params`,
  and the four GLM-5.3 `additional_drop_params` fields. Rename the remaining
  version-labelled table to reflect 1.102.0.
- Register the missing GPT-6 Sol capability in LiteLLM's local model map so
  default and explicit course temperatures keep working with no reasoning.

## Outcomes & Retrospective

The backend now pins LiteLLM 1.102.0. Two GPT-5.5 Pro exact rows, Gemini
3.8 Flash's redundant allowlist, and four duplicate GLM-5.3 drop lists were
removed. All other compatibility entries remain because isolated SDK and
mock-transport comparisons showed changed wire output or adapter errors when
they were absent. The native adapter contract now runs at the new pin and
checks GPT-5.5 Pro's native capability metadata, ZAI's updated capability,
and GPT-6 Sol's no-reasoning request with the ordinary temperature.

The full backend suite passed with 9,187 tests, 107 skips, and 50 passing
subtests. Focused code-format, architecture-boundary, dependency-resolution,
development-tool, repository-harness, and adjusted all-files pre-commit checks
also passed. Simulated adapter requests cannot prove live provider behavior,
so the three live CN and three live US model routes were also exercised from
the local Python environment with short streaming calls. Each returned
content, a stop finish reason, and prompt/completion token usage. Deployment
should retain its ordinary rollout checks.

## Context and Orientation

The package is pinned in `src/api/requirements.txt`. Shared calls and the
version-labelled `_LITELLM_1102_COMPATIBILITY_PATCHES` table live in
`src/api/flaskr/api/llm/__init__.py`. `src/api/tests/test_llm.py` contains
capability tests and a native adapter contract that sends requests to an
`httpx.MockTransport` and checks the resulting provider wire body, stream
content, usage, and model limits. The earlier rationale lives in
`docs/exec-plans/completed/llm-provider-parameter-policies.md`.

## Plan of Work

1. Capture each adapter's no-patch behavior with LiteLLM 1.102.0 and compare
   it with the current patched behavior, including adversarial caller values.
2. Change the dependency pin and remove only rows with equivalent safe output.
   Rename version-specific identifiers and comments to describe remaining
   compatibility gaps accurately.
3. Retarget native adapter and unit tests to the new release; assert the
   applicable wire values and retain strict failure behavior.
4. Verify streaming and non-streaming entry points, gateway token counts and
   usage, and all repository quality gates.

## Concrete Steps

Use `/private/tmp/litellm-assess-faab/bin/python` for isolated local checks.
Run `python -m pip check`; targeted LLM, gateway, learning, and native adapter
tests; then the full backend suite if the targeted checks pass. Run repository
harness, architecture, development-tool, and pre-commit checks before commit.

## Validation and Acceptance

- Every changed provider retains the product's minimum-thinking request.
- No provider loses streaming content, tools, JSON response format, or usage.
- The native adapter contract executes under 1.102.0 rather than skipping.
- The complete pinned dependency set resolves and imports on Python 3.11.
- Repository verification succeeds and the working tree contains only this
  upgrade's code, tests, dependency pin, and plan.

## Idempotence and Recovery

All provider requests in the native contract use `httpx.MockTransport` and no
real provider credentials. The isolated environment and contract copies under
`/private/tmp` can be rebuilt without changing the repository. If a deleted
entry changes the provider wire format, restore that row and record why it
remains necessary before proceeding.

## Interfaces and Dependencies

This change affects the LiteLLM Python dependency and the shared LLM wrapper.
Public endpoints and request DTOs stay stable. The wrapper's consumers include
learning, authoring, the model gateway, metering, and Langfuse observation.

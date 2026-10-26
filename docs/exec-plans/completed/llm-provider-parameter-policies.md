# LiteLLM-First Minimum-Thinking Parameters

## Purpose / Big Picture

AI-Shifu applies a product-wide rule that model reasoning should be disabled or
set to the lowest supported level. The earlier implementation encoded this rule
in provider callbacks and then proposed a custom policy language. That made the
application duplicate behavior already supplied by LiteLLM and made each new
exception harder to reason about.

This change makes LiteLLM 1.98.0 the default source of adapter capabilities and
reasoning mappings. One request-preparation function serves both streaming entry
points. A small, version-labelled, flat compatibility table contains only
confirmed LiteLLM 1.98.0 gaps, so a future exception normally requires one table
row and one contract assertion rather than a new callback or merge framework.

## Progress

- [x] 2026-09-01 07:20 CST: Rebased the two focused model fixes onto current
  `origin/main` and removed the previous policy-DSL refactor commit.
- [x] 2026-09-01 08:00 CST: Replaced provider reload callbacks with one
  LiteLLM-first request preparation function and a flat compatibility table.
- [x] 2026-09-01 08:07 CST: Added capability, precedence, conflict, temperature,
  adapter-wire, strict-error, and both-entry-point tests; 69 focused tests pass
  with LiteLLM 1.98.0.
- [x] 2026-09-01 08:36 CST: Re-ran the complete backend suite after the final
  OpenAI Responses conflict fix; 3601 tests pass and 17 are skipped.
- [x] 2026-09-01 08:36 CST: Repository harness, architecture-boundary, and
  development-tool checks pass; final formatting, diff, and pre-commit gates
  are run after this archival move regenerates repository documentation.
- [x] 2026-09-01 08:36 CST: Archived this implementation plan for the single
  replacement refactor commit. Exact force-with-lease push and live CI/review
  convergence are recorded on PR #2733 after the commit exists.
- [x] 2026-09-01 09:00 CST: Addressed a live review finding that the ZAI
  provider-wide patch reached legacy GLM-4 models. Kept provider-wide
  `response_format`, enumerated the 13 LiteLLM 1.98/current-contract thinking
  models as exact rows, and added legacy no-thinking wire coverage.

## Surprises & Discoveries

- LiteLLM 1.98.0 already maps `reasoning_effort=none` to native minimums for
  Gemini and DeepSeek, and maps standard `thinking={"type":"disabled"}` for
  Volcengine. Provider-specific reload functions duplicated these mappings.
- Gemini 3 model metadata leaves the individual effort flags unset, but its
  adapter supports `reasoning_effort`; `none` therefore correctly delegates to
  the adapter's native minimum. Gemini 3.7 Flash is the exact exception because
  Google documents `low`, not `minimal`, as its minimum.
- DashScope does not list `reasoning_effort` for the ZHIPU GLM-5.3 IDs. Passing
  the standard field through `allowed_openai_params` produces the required
  `reasoning_effort=low` wire shape without `enable_thinking=true`.
- ZAI's top-level `thinking` support is incomplete in LiteLLM 1.98.0: it reaches
  the OpenAI SDK as an unsupported keyword. Keeping `thinking.disabled` in
  `extra_body` works.
- ZAI's adapter gap is not provider-wide. Legacy models such as `glm-4-flash`
  do not accept `thinking`, while LiteLLM 1.98 also omits the capability for
  several GLM-4.5 variants and `glm-5.2` that do accept it. The provider row
  must therefore contain only `response_format`; supported current IDs need
  explicit exact rows, and unknown future IDs must not match implicitly.
- A flat `additional_drop_params` entry also removes an `extra_body` field with
  the same name for OpenAI-compatible adapters. Provider patches that own a
  nested `thinking` or `enable_thinking` field therefore set the caller's
  top-level copy to `None`, shallow-merge the patch value, and reserve precise
  drop paths for other conflicts.
- Caller-supplied drop paths can name a compatibility patch's whole ancestor
  object, the exact protected path, or one of its descendants. Filtering all
  three overlap forms is necessary; otherwise a broad `extra_body` drop can
  erase a provider-owned minimum-thinking control.
- Volcengine is a special case of that overlap rule: LiteLLM maps the standard
  root `thinking` control to `extra_body.thinking` before its own drop filter
  runs. Ark request preparation must therefore protect and sanitize both paths
  even though the application policy remains the standard root field.
- The OpenAI completion-to-Responses bridge has the inverse hazard: a caller's
  root or `extra_body.reasoning` object is promoted to the final Responses API
  `reasoning` object and takes precedence over `reasoning_effort`. Both exact
  paths must be dropped so a caller cannot raise a Pro model above the product
  minimum; unrelated `extra_body` values remain intact.
- LiteLLM 1.98.0 incorrectly reports `minimal` support for GPT-5 Pro, GPT-5.2
  Pro, and GPT-5.4 Pro. Its GPT-5.5 Pro flags correctly reject the three lower
  levels but do not explicitly identify `medium`. Exact compatibility rows are
  required for the documented minimums.
- The existing automatic `temperature=0.3` overrides Gemini 3's adapter default
  and is invalid for OpenAI reasoning efforts above `none`. Omitting an
  application default preserves native behavior while leaving explicit caller
  values available for strict validation.

## Decision Log

- Decision: ask `litellm.get_supported_openai_params()` first and use
  `get_model_info()` only to select among explicitly declared effort levels.
  Rationale: LiteLLM owns provider mapping; model flags only refine the minimum.
- Decision: select explicit `none`, then `minimal`, then `low`; select `medium`
  only when all three lower flags are explicitly false; otherwise use `none`
  when the adapter supports the field. Rationale: `None` means metadata is
  missing, not unsupported.
- Decision: use one `_LITELLM_198_COMPATIBILITY_PATCHES` mapping keyed by
  `(provider, None)` or `(provider, exact_casefold_model_id)`. Rationale: this
  provides provider-wide then exact-model precedence without prefix matching,
  dataclass rules, recursive merge, sentinels, or dynamic builders.
- Decision: merge scalar parameters shallowly, union allow/drop lists in stable
  order, and merge only the first level of `extra_body`, with later patches
  winning. Rationale: the behavior is easy to inspect and matches LiteLLM's
  request boundary.
- Decision: do not enable `drop_params=True`. Use only targeted
  `additional_drop_params` generated for conflicting thinking controls.
  Rationale: unrelated invalid `stop`, `top_p`, reasoning, and structured-output
  parameters must continue to fail loudly.
- Decision: reject caller drop paths that overlap a compatibility-owned control
  at the ancestor, exact, or descendant level, including LiteLLM's mapped
  `extra_body.thinking` target for standard Ark thinking. Rationale: conflict
  cleanup may remove caller values, but callers may not remove the forced
  product minimum itself.
- Decision: include both `reasoning` and `extra_body.reasoning` in the targeted
  conflict list whenever a minimum-thinking control is active. Rationale:
  LiteLLM 1.98's Responses bridge otherwise promotes the caller object and lets
  it override the selected `reasoning_effort`.
- Decision: keep explicit incompatible temperature values unchanged, but omit
  the automatic default for Gemini 3 and OpenAI non-`none` reasoning requests.
  Rationale: callers retain strict provider feedback and ordinary requests use
  native defaults.
- Decision: enumerate the LiteLLM 1.98.0 OpenAI Pro base IDs and known snapshots
  as exact rows. Rationale: the first version deliberately avoids a prefix DSL;
  new aliases must be added explicitly.
- Decision: enumerate the 13 confirmed ZAI thinking IDs as exact rows sharing
  one literal disabled-thinking patch, while leaving legacy and unknown IDs on
  the capability-only path. Rationale: this preserves LiteLLM-first behavior
  and the no-prefix contract without sending an unsupported vendor field to
  older endpoints.

## Outcomes & Retrospective

The implementation now delegates ordinary minimum-thinking selection to
LiteLLM 1.98.0 and limits application exceptions to one flat, versioned table.
Both public invocation paths share the same preparation function; provider
callbacks and the proposed policy DSL are gone.

The final local behavior evidence is 70 focused LiteLLM 1.98.0 tests and 3602
passing backend tests with 17 skips. The wire contracts cover native provider
mappings, exact compatibility rows, strict unsupported parameters, Ark's mapped
thinking field, legacy ZAI exclusion, and the OpenAI completion-to-Responses
reasoning conflict. Independent and live reviews found the broad-drop,
Responses-bridge, and legacy-ZAI bypasses; all were fixed and re-reviewed.

The remaining operational follow-through is to publish the replacement commit
with an exact force-with-lease, update the PR description, and wait for checks
and review threads on that immutable head. Those live results belong to the PR
rather than a commit that must already exist before CI can run.

## Context and Orientation

`src/api/flaskr/api/llm/__init__.py` registers model providers, resolves display
IDs to actual provider model IDs, prepares LiteLLM arguments, and implements
`invoke_llm()` plus `chat_llm()`. Both entry points previously received a
`reload_params` callback through `ProviderConfig` and `ProviderState`.

`src/api/tests/test_llm.py` contains request-preparation unit tests, both complete
invocation paths, and a subprocess contract pinned to the installed LiteLLM
1.98.0 distribution. The subprocess uses mock HTTP transports to inspect final
provider request bodies without external API calls.

## Plan of Work

Remove the callback field from provider config/state and delete all provider
reload functions. Resolve the provider adapter from the registered config, ask
LiteLLM for supported standard controls, and calculate the lowest effort from
explicit model metadata. Merge the versioned provider and exact-model patches
after that baseline. Determine the final control, discard superseded controls,
and attach targeted drop paths so caller conflicts cannot defeat the product
minimum while unrelated arguments remain strict.

Apply this single preparation function in `invoke_llm()` and `chat_llm()` after
their messages and stream options are prepared. Preserve their public function
signatures, routing, token limits, streaming, billing, and observability.

Replace callback-oriented tests with capability and patch matrices. Verify the
actual LiteLLM 1.98.0 mapping for DeepSeek, DashScope, Volcengine, ZAI, Gemini,
and OpenAI Pro models. Complete full repository validation, then replace only
the old third PR commit and converge the live PR state.

## Concrete Steps

1. Remove `reload_params` from `ProviderConfig`, `ProviderState`, initialization,
   and all provider registrations.
2. Add the LiteLLM capability resolver, shallow patch merger, conflict-drop
   builder, temperature decision, and versioned compatibility table.
3. Route both LLM invocation functions through the shared preparation helper.
4. Rewrite focused tests around capabilities, exact/provider precedence,
   casefold matching, list/extra-body merges, caller conflict handling, native
   wire shapes, and strict unsupported-parameter errors.
5. Run the focused and complete backend suites, Ruff, diff checks, harness
   checks, and repository pre-commit hooks.
6. Move this file to `docs/exec-plans/completed/`, regenerate repository
   knowledge docs, commit, push with an exact force-with-lease, update the PR
   description, and wait for all checks and review threads on the new head.

## Validation and Acceptance

- Models with standard LiteLLM `reasoning_effort` or `thinking` support require
  no compatibility table entry.
- Capability flags `True`, `False`, and `None`, plus missing model metadata, map
  to the documented minimum-selection behavior.
- Provider rows apply before exact rows with case-insensitive exact model IDs.
- Qwen GLM-5.3 and GLM-5.3-Flash send only `reasoning_effort=low`; ordinary
  Qwen and SiliconFlow send `enable_thinking=false`.
- DeepSeek and Ark use LiteLLM native disabled-thinking mappings. ZAI sends
  nested `thinking.disabled` and still permits `response_format`.
- Gemini 3.7 Flash maps to `thinkingLevel=low`; Gemini 2.5 Pro maps to its
  128-token minimum budget.
- GPT-5 Pro maps to `high`; GPT-5.2/5.4/5.5 Pro and their known snapshots map to
  `medium`, with no automatic sampling temperature.
- Caller conflicts cannot override the minimum. Unrelated `extra_body` fields
  and parameters remain, and no global `drop_params=True` is introduced.
- Removing the DashScope or Gemini exact row exposes LiteLLM 1.98.0's original
  unsupported request or wrong minimum wire shape.
- Focused and complete backend tests, Ruff, `git diff --check`, repository
  harness checks, and all pre-commit hooks pass.
- PR #2733 ends CLEAN/MERGEABLE with all current-head checks terminal and no
  unresolved actionable review thread.

## Idempotence and Recovery

Request preparation creates fresh dictionaries and does not mutate the
compatibility table. Repeated calls therefore cannot accumulate parameters.
Focused tests use mock transports and do not contact providers.

The replacement refactor will remain one commit above the two preserved model
fix commits. Before push, re-fetch the remote branch and use an exact
`--force-with-lease` value. If the refactor must be rolled back after merge,
revert that single commit; model routing, configuration, credentials, and the
two focused fixes remain unchanged.

## Interfaces and Dependencies

The implementation depends on LiteLLM 1.98.0 APIs
`get_supported_openai_params`, `get_model_info`, `allowed_openai_params`, and
`additional_drop_params`. It does not change the signatures of `invoke_llm()`
or `chat_llm()`, environment variables, Kubernetes configuration, model IDs,
token limits, streaming responses, billing, or database schemas.

The compatibility values follow the provider documentation for
[Gemini 3.7 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash),
[GPT-5 Pro](https://developers.openai.com/api/docs/models/gpt-5-pro), and
[GPT-5.4 Pro](https://developers.openai.com/api/docs/models/gpt-5.4-pro).

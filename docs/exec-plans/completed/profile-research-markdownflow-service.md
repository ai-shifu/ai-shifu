# Independent MarkdownFlow Profile Research Service

## Purpose / Big Picture

Move the guided learner-profile research runtime out of `service/learn/` and
make it a small profile-research service that invokes the public
`markdown-flow` API directly. The learner and operator preview endpoints keep
their existing product behavior, but the research runtime no longer imports
course runtime contexts, course DTOs, lesson preview adapters, course progress,
or any other `flaskr.service.learn` module.

The visible flow remains unchanged: a learner who does not have a familiar AI
agent answers the configured MarkdownFlow questions, reviews the generated
profile draft, and saves it. The implementation should preserve the current
retry-safe session protocol while emitting only the small SSE event shape the
profile UI actually consumes.

## Progress

- [x] 2026-08-03: Re-inspected the current user/admin routes, frontend SSE
  consumer, installed `markdown-flow==0.3.0` public API, and service boundaries.
- [x] 2026-08-03: Confirmed that the frontend accepts direct `content` and
  `interaction` events plus one terminal `done` summary; Learn element DTOs are
  not part of the required contract.
- [x] 2026-08-03: Implemented the independent profile-research runtime and thin
  LLM provider.
- [x] 2026-08-03: Repointed user, configuration, and operator-preview callers;
  removed the old
  Learn runtime and its DTO exports.
- [x] 2026-08-03: Replaced the oversized Learn runtime test suite with focused
  profile-research tests and update route/config tests.
- [x] 2026-08-03: Ran focused backend/frontend tests, Ruff, architecture checks,
  repository
  harness checks, and the commit-sized verification gate.
- [x] 2026-08-03: Prepared the verified commit-sized change for the existing PR
  branch and synchronized its documented scope.
- [x] 2026-08-04: Removed the feature-specific rate-limit configuration, Redis
  counters, response errors, and frontend compatibility branches.
- [x] 2026-08-05: Moved the locked summary prompt into the shared backend prompt
  directory and made its result contract one plain-text learner profile.

## Surprises & Discoveries

- `MarkdownFlow.process()` already owns document parsing, interaction rendering,
  button/text input validation, variable updates, output-language handling, and
  content streaming. The old runtime wrapped these through `MdflowContextV2`
  and then converted results through lesson-preview element adapters.
- The profile UI deliberately supports a much smaller fallback wire format:
  direct `content` or `interaction` events, a stable generated-block id, and a
  terminal `done` event containing `next_block_index` and eventually
  `profile_draft`.
- The library consumes context but does not persist sessions or advance a cursor.
  Redis TTL, owner/purpose authorization, a per-session lock, and retry replay
  therefore remain application concerns rather than MarkdownFlow customization.
- The product-wide LiteLLM route and metering live below `flaskr.api.llm`, so a
  thin `LLMProvider` adapter can preserve model routing, usage records, and
  Langfuse without importing `service/learn`.
- MarkdownFlow expects a native language name rather than an application locale
  code, so the standalone service uses the neutral shared locale resolver before
  calling `set_output_language()`.
- MarkdownFlow preprocessing means the public `LLMResult.prompt` is the correct
  content-history source for generated content. Preserved content has no LLM
  prompt, so only the library-restored output is retained as assistant history.

## Decision Log

- Create `flaskr.service.profile_research` as the only owner of guided profile
  MarkdownFlow execution. Its production source must contain no import from
  `flaskr.service.learn`.
- Instantiate `MarkdownFlow` directly for each run step and use
  `get_all_blocks()`, `process()`, `set_model()`, `set_temperature()`, and
  `set_output_language()` without a second syntax parser or interaction parser.
- Keep the platform-owned final summary block because the saved profile has a
  fixed five-area product contract; load its language-neutral template from the
  shared `src/api/prompts` directory and let MarkdownFlow enforce output language.
- Preserve endpoint paths, request identity, cursor checks, TTL, owner/purpose
  scope, locking, and exact replay of an ambiguous completed request.
- Allow independent sessions for the same owner and purpose instead of keeping a
  separate active-session index. Session deletion takes the same lock as a run,
  preventing an in-flight run from recreating a deleted session.
- Remove Learn DTO and preview-adapter coupling. Emit direct profile-research
  SSE dictionaries and accumulate streamed MarkdownFlow chunks under one stable
  generated-block id.
- Keep the profile call non-billable while using the shared LiteLLM, metering,
  and Langfuse layers. Do not add profile-specific redaction.
- Leave course-prompt composition and all other learner-profile course behavior
  in their existing paths; this plan changes only profile research execution.

## Outcomes & Retrospective

The profile research runtime now lives entirely under
`flaskr.service.profile_research` and its production import graph contains no
`flaskr.service.learn` dependency. It calls MarkdownFlow 0.3.0 directly for
parsing, interaction rendering and validation, variable handling, preserved
content, output-language translation, and streaming. The old Learn adapter,
course DTO summary, preview element conversion, and profile-specific redaction
surface were removed.

The application-specific remainder is deliberately narrow: Redis-backed TTL
sessions, owner/purpose authorization, a cursor and per-session lock, bounded
inputs, retry replay, the fixed five-area final profile prompt,
the shared non-billable LLM/Langfuse route, and the SSE envelope consumed by the
existing UI.

Profile research intentionally has no feature-specific rate limiter or Redis
counter. Cross-cutting traffic controls, if needed, belong outside this service.

Latest verification covered 24 standalone runtime tests within a 119-test
focused backend matrix, 12 focused frontend conversation tests, frontend type
checking, Ruff 0.15.13, translation checks, architecture boundaries, and the
repository harness. The all-files hook also exposed unrelated repository-wide
Ruff debt under a newer locally installed Ruff; its automatic unrelated changes
were discarded, and the expected 0.15.13 checks were run on the changed Python
surface.

## Context and Orientation

The old runtime is
`src/api/flaskr/service/learn/transient_markdownflow.py`, re-exported from
`src/api/flaskr/service/learn/api.py`. User session creation/run/cleanup is in
`src/api/flaskr/route/user.py`; operator preview calls are in
`src/api/flaskr/service/shifu/admin_operations/profile_onboarding.py` and
`route.py`; configuration validation is in
`src/api/flaskr/service/common/profile_onboarding.py`.

The frontend runtime consumer is
`src/cook-web/src/components/profile-onboarding/ProfileOnboardingConversation.tsx`.
It can render direct MarkdownFlow strings through `markdown-flow-ui` and only
needs a stable cursor and terminal profile draft from the backend.

## Plan of Work

1. Add a standalone `profile_research` package with a compact Redis session
   model/store, a thin shared-LLM provider, direct MarkdownFlow execution, and
   SSE serialization.
2. Change user/config/admin callers to import this public service directly and
   move profile-specific messages to the profile i18n namespace.
3. Delete the transient Learn runtime and its Learn DTO/re-export surface.
4. Add focused runtime coverage for direct MarkdownFlow calls, interaction
   advancement, generated drafts, retry replay, authorization, and import
   independence; update route/config tests to patch the new boundary.
5. Verify the exact changed surface and then the repository architecture and
   commit gates before updating the existing PR.

## Concrete Steps

From the repository root:

1. Inspect references with
   `rg -n "transient_markdownflow|TransientMarkdownFlow" src/api`.
2. Implement with `apply_patch`, keeping the public HTTP paths stable.
3. Run the focused profile runtime and route tests under `src/api`.
4. Run the exact Ruff 0.15.13 binary on changed Python files, then
   `python scripts/check_architecture_boundaries.py`,
   `python scripts/check_repo_harness.py`, and
   `python scripts/check_dev_tools.py`.
5. Run the relevant frontend conversation/API tests if the wire adapter changes.
6. Run `lefthook run pre-commit --all-files`, record any unrelated baseline
   limitations, commit with the required `Changed:` and `Benefit:` body, and
   push to `sunner/profile-onboarding-markdownflow` through the GitHub remote.

## Validation and Acceptance

Acceptance requires all of the following:

- No source file in `flaskr.service.profile_research` imports
  `flaskr.service.learn`, and no profile onboarding user/admin/config caller
  imports the removed Learn transient API.
- Configured documents are parsed and executed by `markdown-flow` itself; the
  product has no separate MarkdownFlow syntax parser.
- Learner and operator preview sessions render interactions, accept answers,
  advance content blocks, return the final editable profile draft, and replay an
  identical retried request without a second model call or cursor advance.
- The current user/admin endpoint paths and frontend-visible behavior remain
  compatible.
- Focused tests, Ruff, architecture boundaries, harness validation, and the
  available commit gate pass or have an explicitly documented environment-only
  limitation.

## Idempotence and Recovery

Session state is a TTL cache snapshot. Starting a new session does not mutate
course state or the saved learner profile. Each run holds a per-session lock;
the persisted `(request_id, expected_block_index, user_input)` replay record
allows a client to repeat an ambiguous request safely. Failed or abandoned
sessions expire automatically, and profile completion/skip performs best-effort
session deletion after the durable profile/state transaction succeeds.

All code edits are ordinary version-controlled changes. If a focused test
reveals a contract mismatch, adjust the standalone serializer/caller before
removing the old implementation; do not modify course runtime behavior as a
workaround.

## Artifacts and Notes

- Installed library version: `markdown-flow==0.3.0`.
- Required frontend event forms are direct `content` / `interaction`, `error`,
  and terminal `done`; lesson `ElementDTO` metadata is not consumed.
- The existing PR is https://github.com/ai-shifu/ai-shifu/pull/2238.

## Interfaces and Dependencies

The new public service exports profile-specific constants, errors, document
validation, session start/run/delete functions, and the SSE response builder.
Internally it may depend on `flaskr.api.llm`, `flaskr.api.langfuse`, shared cache,
shared metering, i18n, database session cleanup, and the public `markdown_flow`
package. It must not depend on `flaskr.service.learn` or course persistence.

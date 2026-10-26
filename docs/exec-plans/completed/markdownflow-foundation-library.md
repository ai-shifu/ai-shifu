---
title: Shared MarkdownFlow foundation library
status: completed
owner_surface: backend
last_reviewed: 2026-10-23
---

# Shared MarkdownFlow foundation library

## Purpose / Big Picture

Extract the existing course MarkdownFlow 2.0 engine from `main` into an
application-independent library. Courses consume one shared application
binding for execution, model routing and localized controls. Preserve course
runtime behavior, prompt bytes, engine version and saved Session JSON.

PR #3163 is the foundation and targets `main`. PR #3161 subsequently depends
on it to migrate Profile to MarkdownFlow 2.0. Profile remains on MarkdownFlow
1.0 throughout the foundation change.

## Progress

- [x] 2026-10-24 CST: Integrate main 042481534 while rebasing the foundation.
  Preserve its failed-turn output, memory-generation and follow-up fallback
  fixes; migrate the new capacity-error imports to the shared binding. Keep
  the historical Session fixture and verify its defaulted generation metadata.
- [x] 2026-10-24 CST: Validate that rebased foundation with 4,822 library,
  learning, shared LLM and existing Profile tests, 93 expected skips and four
  subtests passed. The complete repository pre-commit gate also passed.
- [x] 2026-10-24 CST: Confirm the delivery order: foundation PR #3163 starts
  from `main` at 5991ac21a; Profile migration PR #3161 depends on the foundation.
- [x] 2026-10-24 CST: Move the existing course engine, prompts, formatter and
  bridge into the application-independent markdownflow package.
- [x] 2026-10-24 CST: Separate explicit-label question rendering from course DTO
  translation; move gateway/budget handling into the shared application layer.
- [x] 2026-10-24 CST: Coordinate course imports, prompt resources, release and
  evaluation tooling, portable test ownership and architecture enforcement.
- [x] 2026-10-24 CST: Keep the `main` engine's runtime semantics in the
  foundation. Leave Profile response buffering and its regression tests with
  the dependent Profile migration.
- [x] 2026-10-24 CST: Restore the existing Profile implementation and its
  product specification; update foundation documentation to the correct order.
- [x] 2026-10-24 CST: Re-run portable, course, shared gateway and existing
  Profile 1.0 tests against the standalone foundation branch: 4,963 passed,
  93 expected skips and 82 subtests passed across non-overlapping groups.
- [x] 2026-10-24 CST: Complete local repository gates and independent review
  for the corrected foundation diff; commit the standalone implementation as
  d650a16f on its branch based directly on `main`.
- [x] 2026-10-24 CST: Replay all fourteen Profile migration commits separately
  on the foundation and adapt their imports to the shared binding. The
  dependent branch's backend suites passed 4,995 tests, with 93 skips and
  82 subtests passed. The dependent branch's complete repository pre-commit
  gate passed; remote checks remain tracked under PR #3161.
- [x] 2026-10-24 CST: Review the foundation's local implementation acceptance
  and archive this plan. Remote branch updates and exact-head CI remain tracked
  in PR #3163 and the dependent PR #3161, outside this local archival.

## Surprises & Discoveries

- Main added memory_generations to Session after the extraction was prepared.
  Preserve that native serialization contract and its empty default when
  restoring historical JSON; do not rewrite the old compatibility fixture.
- Moving api.py alone would retain reverse dependencies: Engine imports the
  course marker filter and importing learn.agent initializes ORM models.
- The old legacy protocol combines a reusable controls codec, request locale
  resolution and course DTO translation. Those responsibilities need separate
  owners while preserving their exact output.
- Thread/gevent bridge capacity counters and cancellation ContextVars must have
  one implementation; duplicated compatibility modules would split runtime state.
- Version release scripts, evaluation fingerprints and tests also refer to old
  engine locations. Update these consumers with the implementation move.
- Coverage reporting included only flaskr/*. Include markdownflow/* so the
  existing 95.01% gate continues measuring every moved runtime module.
- Profile's optional model-response buffering was added by its migration and
  is absent from `main`. Copying that branch's complete engine into the
  foundation would mix a product behavior change into the structural extraction.

## Decision Log

- Put the portable implementation in src/api/markdownflow. It must not import
  flaskr, Flask or SQLAlchemy. Keep all prompt bytes and the engine version.
- Expose application bindings through flaskr.api.markdownflow. GatewayModel
  continues using shared chat_llm and existing metering/tracing.
- Keep course ORM, progress, rewind, TTS and DTO adapters in learn. Profile
  remains on its existing 1.0 runtime until the separate migration consumes
  the foundation.
- Preserve native Session JSON. The extraction requires no DB, Redis or
  Profile schema migration and no provider or dependency-pin changes.
- Build PR #3163 directly on `main`; make PR #3161 depend on it. Put Profile
  runtime, API, frontend, private-summary and migration-specific engine changes
  in PR #3161, together with their regressions and product documentation.
- Revalidate the standalone foundation after changing its base. Verification
  performed on a combined Profile branch is not evidence for this base.

## Outcomes & Retrospective

The portable implementation and shared application bindings have been
extracted, with the course engine's existing behavior retained. Documentation
now records the foundation as the prerequisite for the Profile migration.
Standalone regression suites passed 4,963 tests, with 93 expected skips and
82 subtests passed. Local repository gates and independent review also passed;
the standalone foundation is committed as d650a16f. These results belong to the
foundation based directly on `main`, not the combined Profile-migration branch.
The fourteen dependent migration commits have been replayed independently on
that foundation. Their new backend validation passed 4,995 tests, with 93 skips
and 82 subtests passed. Its complete repository pre-commit gate also passed.
Remote delivery and exact-head CI for both PRs must be checked separately and
are not claimed here.

## Context and Orientation

The implementation being extracted is the course engine at
`flaskr/service/learn/agent/engine` on `main`, together with its adjacent bridge,
formatting and gateway modules. The neutral library owns native script/session/
event execution; flaskr/api owns shared application bindings; services own
product behavior. Profile's existing MarkdownFlow 1.0 implementation is outside
this extraction's runtime scope.

## Plan of Work

Move the core and pure presentation/runtime support, split the localized codec
from course DTO conversion, and move gateway integration. Coordinate course
consumers, tests, release scripts, diagnostics and documentation. Keep Profile
migration changes out of the foundation and enforce the library dependency
boundary. Verify this standalone base before reapplying the dependent migration.

## Concrete Steps

1. Move the `main` core and prompts, preserving their behavior and bytes.
2. Supply control labels explicitly and share one codec across validation
   and presentation. Keep course DTO projection outside the library.
3. Migrate course imports to the shared binding and move the shared LLM
   adaptation out of the course package. Preserve Profile 1.0 consumers.
4. Update resource access, offline test ownership, release version paths,
   evaluators and architecture enforcement.
5. Verify native behavior, Session compatibility, thread/gevent state, course
   integration, existing Profile behavior and repository gates on this base.
6. Update PR #3163 with the independent foundation diff; make PR #3161 consume
   that foundation and validate its separate migration behavior.

## Validation and Acceptance

An isolated process must import the library and execute a native turn while
flaskr imports are forbidden. Existing complex course Session JSON must restore
and resume multiple pending interactions without schema changes. Course
orchestration, follow-up handling and shared application bindings must reference
the same native classes and bridge. The Profile 1.0 runtime and public contracts
must remain unchanged.

Run the portable library and evaluation tests, affected course/gateway tests,
existing Profile/configuration/route tests, release metadata checks,
architecture checks/fixtures and the complete pre-commit gate. Compare all
prompt bytes with `main` and confirm that model routing, billing and locale
behavior remain unchanged. Record exact commands and totals only after these
checks run against the corrected foundation branch.

Recorded standalone results on 2026-10-24 CST:

- Portable library and both evaluation suites: 1,453 passed.
- Learning service, course integration and shared LLM tests: 3,059 passed,
  93 skipped and four subtests passed.
- Existing Profile 1.0 runtime, configuration and route tests: 413 passed.
- Release workflow and image metadata: 38 passed and 78 subtests passed.
- Total across these non-overlapping groups: 4,963 passed, 93 skipped and
  82 subtests passed.
- Developer-tool checks, the complete pre-commit gate, repository harness,
  architecture checks/fixtures and the unit-of-work ratchet passed locally.
- Independent review confirmed that the extracted core preserves `main`
  semantics, Session JSON and all fifteen prompt files.
- The dependent Profile branch subsequently passed 1,460 library/evaluation,
  3,059 learning/shared-LLM, 438 Profile/configuration/route and 38 release tests:
  4,995 passed, 93 skipped and 82 subtests passed. These are separate results for
  the migration branch; they do not replace the standalone foundation totals.
  Its final repository gates and remote PR checks remain separate acceptance work.

The four test invocations used the backend virtual environment. The first
three ran from src/api:

```bash
python -m pytest tests/markdownflow tests/scripts/test_evaluate_mdf2_memory.py tests/scripts/test_mdf2_exercise_quality.py -q --disable-warnings --tb=short
python -m pytest tests/service/learn tests/test_llm.py -q --disable-warnings --tb=short
python -m pytest tests/service/profile_research tests/service/common/test_profile_onboarding_prompt.py tests/service/common/test_profile_research_request_validation.py tests/service/config/test_profile_onboarding_publication.py tests/service/user/test_profile_onboarding_contract.py tests/service/user/test_profile_onboarding_config.py tests/service/user/test_profile_onboarding_guided_routes.py -q --disable-warnings --tb=short
```

The release checks ran from the repository root:

```bash
python -m pytest scripts/test_release_workflow.py scripts/test_docker_image_metadata.py -q --disable-warnings --tb=short
```

## Idempotence and Recovery

Work uses the feature branch sunner/markdownflow-foundation-base, starting at
`main` 5991ac21a. Saved backups preserve the previous PR heads while their
base order is corrected. No persisted-data schema changes are introduced;
the extraction can be reverted as a structural change and Session JSON remains
readable by the prior implementation. The dependent Profile work now uses
sunner/profile-after-engine-refactor with fourteen migration commits replayed
on d650a16f; its runtime and frontend state match the previously verified
combined implementation. Validate that dependent branch before remote delivery.

## Interfaces and Dependencies

The markdownflow package accepts native Model instances and exposes Engine,
Session, ScriptBundle, turns/events, iter_turn and explicit-label rendering.
The shared application binding supplies GatewayModel and localized wrappers.
The native model SDK, MarkdownFlow formatter and markdown-it dependencies remain
pinned as before; this task does not publish an external package. Profile's
native-session adapter consumes this API in the separate dependent migration.

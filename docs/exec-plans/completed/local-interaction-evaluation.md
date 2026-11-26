---
title: Local Interaction Evaluation
status: completed
owner_surface: backend
last_reviewed: 2026-11-13
canonical: false
---

# Local Interaction Evaluation

## Purpose / Big Picture

Developers can run representative course interactions after changing the
MarkdownFlow prompts. Replay gives stable parser and recovery checks. Live runs
send the current prompts to a model and compare the resulting learner paths.

## Progress

- [x] 2026-11-13 11:36 CST: Created the task branch at the verified remote main head and sampled production Langfuse observations.
- [x] 2026-11-13 11:49 CST: Added the local runner, the gateway adapter, and catalog tests. Ran all 57 replay cases with network access denied.
- [x] 2026-11-13 11:52 CST: Verified 48 distinct source sessions across 17 courses. Reviewed the rewritten content and coverage inventory.
- [x] 2026-11-13 11:54 CST: Verified a model baseline and prompt candidate with the same settings, including the exact system instructions at the provider call.

## Surprises & Discoveries

- Production observations retain assembled model text and tool arguments. The
  replay reconstructs responses and uses deterministic framing.
- The course gateway normally records usage. The standalone process uses a
  scoped no-op recorder and trace handle while preserving provider token counts.
- After a bound text answer, the current engine requires explicit feedback with
  the current answer identifier and supporting learner evidence before finishing.

## Decision Log

- 2026-11-13. Deliver a Python CLI with reusable public-safe fixtures and opt-in
  provider calls. Use direct engine and renderer checks for the first version.
- 2026-11-13. Re-author course content and learner replies. Select distinct source
  sessions, preserve interaction topology, and document reconstructed repairs.
- 2026-11-13. Treat historical failure reproduction as an explicit replay result
  and keep the intended live outcome visible in the fixture.

## Outcomes & Retrospective

The catalog includes 48 trace-derived cases and nine synthetic gap cases. Replay
reports 43 first-attempt successes, 12 recoveries, and two expected failures
reproduced. The locked MarkdownFlow suite passed 3,376 tests. The focused
runner and live adapter suite passed 11 tests. A live SiliconFlow DeepSeek-V3.2
baseline and candidate verified that a local system prompt edit reached the
provider and was visible in the comparison report. A second pair caught a
duplicated question in the candidate's response after a retry. A single pair
cannot attribute model variation to the prompt edit. Browser rendering and
course persistence are outside this CLI's runtime boundary.

## Context and Orientation

See the [interaction evaluator guide](../../../src/api/scripts/README.md#evaluate_mdf_interactionspy)
for CLI usage and the [coverage inventory](../../../src/api/scripts/mdf_interactions/README.md)
for sample distribution and curation. The
[Langfuse trace contract](../../design-docs/langfuse-trace-association.md)
describes the course prompt, generation, and interaction observations.

## Plan of Work

Curate a reusable catalog from course trace observations. Replay the model side
of each case against the course engine. Add an explicit live model mode and
compare comparable runs by case and repeat. Keep results local and run the
repository checks before committing.

## Concrete Steps

1. Identify controls and rejections in `teaching` and `interact` observations.
   Validate course source, session uniqueness, and input/output shape before
   rewriting content.
2. Drive `ScriptBundle` and the engine's typed turns from case steps. Use the
   course renderer and optionally round-trip session state before answering.
3. Feed replay calls or real gateway streams to the same runner. Capture stage
   failures, prompts by fingerprint, and model outcomes in the report.

## Validation and Acceptance

From `src/api`, run `python scripts/evaluate_mdf_interactions.py`, repeat with
`--suite smoke`, and run `python -m pytest tests/markdownflow/ tests/scripts/test_evaluate_mdf_interactions.py tests/scripts/test_mdf_interaction_live.py -q`.
Check that an omitted question, malformed control, premature completion, or
incorrect memory value fails the associated stage. Run a live baseline and
candidate on the same case and model, and verify a change in the request
instruction fingerprint. Review the JSON catalog before including it in a PR.

## Idempotence and Recovery

Every case and repeat starts a fresh session. A provider failure produces a
separate report status, and a rerun can select just that case. Catalog updates
can be checked offline before a live run. The report writer protects the
selected input catalog and baseline from overwrite.

## Interfaces and Dependencies

The CLI runs with the pinned backend Python dependencies. Offline mode needs
only the local fixture and prompt files. Live mode uses configured provider
credentials and the existing gateway adapter. The model provider receives the
rewritten lesson and current system instructions. The CLI does not start the
web server, database, or Redis.

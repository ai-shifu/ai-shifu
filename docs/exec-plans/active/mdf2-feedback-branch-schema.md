# MDF 2.0 Feedback Branch Schema

## Purpose / Big Picture

Prevent supported learner feedback from entering avoidable missing-branch retries.
The enabled host already requires a feedback declaration before showing ordinary
feedback or pausing/finishing, but the model-visible tool schema still advertises
that declaration as optional. Align the offered schema with the current state
while preserving native validation and portable-host compatibility.

## Progress

- [x] 2026-10-13 04:00 UTC: Identify optional-schema/required-runtime mismatch in
  the retained tenth original-model check. Three generations settle 5.80 credits;
  final visible explanation omits the requested program/two iterations. Original
  classroom/source and all prior failures remain retained; no new learner/summary.
- [x] 2026-10-13 04:05 UTC: Two enabled initial/reloaded SDK cases first fail;
  disabled-host cases already pass. Add request-local schema preparation for
  interact/finish without changing call validation, branch choices or limits.
- [x] 2026-10-13 04:09 UTC: Ten schema/compatibility SDK cases and 101 existing
  feedback-contract cases pass. Cover unsupported anchors, fresh sessions on the
  same engine, null/missing branches, legacy sibling declarations and later calls
  after a committed branch. Initial full suite passes 3836 plus 50 subtests with
  three expected skips. Final suite passes 3842 plus 50 subtests, three expected
  skips, with developer tools, harness and all repository hooks.
- [x] 2026-10-13 04:13 UTC: Complete final broad checks and repository gates.
- [ ] Push an Open/Ready PR.
- [ ] Reply to every AI opinion in its original thread with pushed fixes/tests.
- [ ] Integrate sim, verify both replicas and assess one frozen actual-model
  response within original source/input/model/standards/budgets.

## Surprises & Discoveries

The original tenth reply has a concrete acyclic branch draft, then a control-only
repair, then a generic final definition. Only the final definition was displayed;
none satisfies the requested two loop iterations. Repeated textual guidance is
not reliable evidence that the model follows it. A schema requirement reduces an
avoidable protocol mismatch but cannot establish factual teaching correctness.

## Decision Log

- 2026-10-13: Keep this tool-contract issue separate from #3122 worked-example
  consistency and #3123 clarification/correction scope. Stack on #3123 for the
  actual combined runtime, without automatically merging any PR.
- 2026-10-13: Prepare only primary interaction/finish definitions while the
  enabled host has a supported reply and no committed review. The interaction
  retains both direction and ordinary-review choices. Native validation remains
  response-wide so old sibling declarations continue to work.
- 2026-10-13: Keep inactive fields omitted in the canonical model schema; null
  cannot stand in for its required declaration. Disabled/unsupported/initial
  states retain the exact original optional definitions.

## Outcomes & Retrospective

Implementation and controlled SDK compatibility checks are available. Final
CI, review and deployed actual-model acceptance are pending. All previous factual
and missing-example failures remain open; no full fresh-classroom pass is claimed.

## Context and Orientation

`src/api/flaskr/service/learn/agent/engine/tools.py` owns Deps, feedback validation
and request-local tool preparation. `engine.py` registers the SDK tools.
`tests/service/learn/agent/engine/test_feedback_tool_schema.py` validates actual
SDK-offered JSON schemas and executes native tools. The canonical contract is in
`docs/references/markdownflow-memory-quality.md`; broader acceptance remains in
`mdf2-broader-classroom-acceptance.md`.

## Plan of Work

Prepare copies of existing tool definitions. For a supported undeclared reply,
require interaction direction/review or finish review, retaining original nested
schemas and all other fields. Skip preparation for portable hosts, unsupported
anchors, initial teaching and committed feedback branches. Keep existing runtime
validation, history isolation, memory admission and author constraints intact.

## Concrete Steps

1. Run schema tests against original behavior and retain expected failures.
2. Register preparation on interact/finish; test missing/null branches and valid
   direction/review, reusable definitions and native sibling/later-call paths.
3. Run full learning/script suite, developer-tool check, harness and all hooks.
4. Push a focused Ready PR, handle original-thread reviews, integrate sim and
   verify deployed fingerprints plus native SDK checks before one actual replay.

## Validation and Acceptance

A supported reply offers a valid non-null branch before model execution. Initial,
unsupported and disabled states retain optional declarations, including on another
session using the same Engine. Old native sibling declarations and later calls
remain usable. Author source, pending input and memory rules are unchanged.
Controlled outputs prove these contracts only. The original-model replay must
actually answer the requested illustration correctly and retain the pending
exercise, with verbatim trace/billing attribution and unchanged persisted state.
Complete fresh ordinary HTTP natural-compaction classroom acceptance remains a
separate broader gate; prior failures cannot be replaced by a narrow pass.

## Idempotence and Recovery

Never mutate cached tool definitions or reset existing classrooms. Retain failed
outputs and recover transport results read-only rather than repeating provider
requests. Revert the focused commit to restore optional advertised schemas; this
requires no database migration or saved-session conversion. No production write
is authorized by this plan.

## Interfaces and Dependencies

Uses the pinned pydantic-ai Tool.prepare hook and existing Deps/ToolDefinition.
The gateway already sends the SDK's declared parameter schemas unchanged. No
provider, model, grading criterion, DTO, library pin or request limit changes.

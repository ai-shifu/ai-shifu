# MDF 2.0 Feedback Branch Schema

## Purpose / Big Picture

Prevent supported learner feedback from entering avoidable missing-branch retries.
The enabled host already requires a feedback declaration before showing ordinary
feedback or pausing/finishing, but the model-visible tool schema still advertises
that declaration as optional. Align the offered schema with the current state
while preserving native validation and portable-host compatibility.

## Progress

- [x] 2026-10-13 05:07 UTC: Offline pinned-provider conversion reproduces removal
  of the interaction root anyOf on OpenAI; Ark preserves it without strict mode.
  Seven canonical/provider cases first fail. Use one required non-null feedback
  property with its direction/review union nested inside. Legacy native calls
  remain accepted, canonical evidence remains original, and mixed/ambiguous
  declarations are rejected. All 27 schema/compatibility cases and the combined
  182-case schema/phase/direction suite pass. Full suite passes 3859 plus 50 subtests, three expected skips; all
  repository gates pass. Final state-scoped descriptions preserve legacy models
  and canonical field guidance; the complete suite passes again. An initial candidate exceeded the unchanged 64 KiB regression by
  145 bytes; omit the new field in inactive states and retain the old schemas.
  All 30 schema/history checks then pass. No new paid request or learner yet.
- [ ] Push canonical provider-compatible fix, reply in original threads, redeploy
  and verify the actual current candidate before any paid model check.

- [x] 2026-10-13 04:27 UTC: Adopt Codex finding 4254687333 about simultaneous
  interactions. Three real two-interaction SDK cases first fail. Treat identical
  parsed review objects as one response-wide decision; keep differing reasons
  and phases rejected before display. All 13 schema/compatibility cases plus
  101 feedback-contract cases pass; valid multi-input delivery needs one model
  response and no extra planning call. Full learning/script suite passes 3845
  plus 50 subtests, three expected skips; developer tools, harness and all
  repository hooks pass.

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
- [x] 2026-10-13 04:16 UTC: Push 774e1a46a and open Ready PR #3125.
  Integrated sim ce8c44774/build 624/Drone 5413; hold paid actual verification
  until the accepted simultaneous-interaction finding is fixed and redeployed.
- [x] 2026-10-13 04:45 UTC: Reply to every AI opinion in its original thread.
  Codex multi-input finding adopted in pushed 9749ae5c7; CodeRabbit withdrew
  the sibling finding after the compatibility explanation. Actual new-head
  review reports Minimal/no new blocking issue; all seven CI checks pass.
- [x] 2026-10-13 04:45 UTC: Integrate sim 978aca95c/build 625/Drone 5414.
  Full integration suite passes 3865 plus 50 subtests, three expected skips,
  and all gates. Both Ready API replicas match 68 files and pass 451 SDK cases;
  Web runs the same tag. One frozen original-model check remains a failure:
  three generations/5.84 settled credits, no summary or new learner.
- [ ] Resolve model/schema-adherence and factual acceptance limitations before
  claiming the broader original-model gate or fresh classroom passes.

## Surprises & Discoveries

The eleventh actual original-model check still omits its declaration in the first
interaction despite the offered required schema. Two existing native retries
recover the protocol, but final visible prose ignores an addition when tracing
successive loop tests and claims an incorrect stop iteration. Hidden first-draft
prose also claims termination after reloading unchanged input each cycle. Neither
is accepted as correct teaching. All outputs/token tuples match actual usage and
attempt/block attribution; source, persisted classroom and memory are unchanged.

The schema offer is not constrained decoding. `gateway_model.map_tools` passes
the parameter schema through but does not enable provider strict mode. The
[Ark function-calling reference](https://docs.volcengine.com/docs/ark/function-calling?lang=en)
describes strict mode separately, with every property required and optional
values represented as nullable. Enabling a flag on the current schemas is not a
validated drop-in correction. No provider strictness/model/configuration change
or repeated unchanged paid request is made here.

A per-tool branch requirement must have a legal multiple-interaction payload.
Rejecting every repeated review made the initial schema incompatible with that
supported path. Matching parsed objects now declare one logical decision;
conflicting objects retain the existing rejection. Legacy sibling declarations
remain valid, with no new learner criterion or additional model request.

The original tenth reply has a concrete acyclic branch draft, then a control-only
repair, then a generic final definition. Only the final definition was displayed;
none satisfies the requested two loop iterations. Repeated textual guidance is
not reliable evidence that the model follows it. A schema requirement reduces an
avoidable protocol mismatch but cannot establish factual teaching correctness.

## Decision Log

- 2026-10-13: Replace the initial root branch combinator with a required feedback
  property. Pinned Ark and OpenAI transformations must both retain its requirement
  and both legal choices. Keep optional native aliases for saved callers; never
  rewrite the original canonical call into a synthetic historical declaration.

- 2026-10-13: Keep legacy native sibling payloads accepted while advertising a
  canonical delivery declaration to new model requests. CodeRabbit 4254709240
  identifies this deliberate narrower offer; restoring optional fields would
  recreate the missing-branch retries. Existing real SDK tests cover legacy
  payload acceptance and committed-review reuse; repeated identical reviews
  provide the schema-valid multiple-interaction path.

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

The canonical property candidate has local focused validation; its final checks
and deployed acceptance are pending. The previous implementation, all seven CI
checks, actual review and both deployed
replicas and controlled SDK compatibility checks pass on functional head
9749ae5c7. The frozen original-model check fails both initial schema adherence
and factual teaching correctness; it does not establish fewer retries or broader
merge readiness. All prior failures remain open; full fresh-classroom acceptance
is pending. Later documentation-only receipts are checked separately.

## Context and Orientation

`src/api/flaskr/service/learn/agent/engine/tools.py` owns Deps, feedback validation
and request-local tool preparation. `engine.py` registers the SDK tools.
`tests/service/learn/agent/engine/test_feedback_tool_schema.py` validates actual
SDK-offered JSON schemas and executes native tools. The canonical contract is in
`docs/references/markdownflow-memory-quality.md`; broader acceptance remains in
`mdf2-broader-classroom-acceptance.md`.

## Plan of Work

Prepare copies of existing tool definitions. For a supported undeclared reply,
require primary feedback containing direction/review or finish review, retaining
original nested schemas and other fields; legacy native spellings remain valid. Skip preparation for portable hosts, unsupported
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

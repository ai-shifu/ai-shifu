# Keep follow-up memory answers within available evidence

## Purpose / Big Picture

A current memory answer must report the verified value without inventing why
an earlier preference differs or is missing. Explicit historical questions
retain original wording, without treating assistant confirmations as database
receipts. This is a focused answer-quality change, not a new memory audit log.

## Progress

- [x] 2026-10-10T06:16:06Z: Confirmed #3084 manually merged as a0ea6324a;
  final technical CI succeeded. Its live accounting sample remains separate
  from the three retained historical-cause failures.
- [x] 2026-10-10T06:21:16Z: Inspected original failed transcripts and actual
  tool/context flow. Current reads provide no historical write receipts.
- [x] 2026-10-10T06:22:47Z: All 42 focused tool cases and 3,075 learning/
  profile tests pass, plus four subtests and one expected skip. Exact UTF-8
  boundary cases preserve the 8192-byte return contract. Developer tools and
  repository all-files gates pass. Language-model quality is not yet verified.
- [ ] Publish one focused PR and the approved runtime/test delta to sim.
- [ ] Verify both ready replicas, replay the original natural scenarios once,
  preserve failures and reconcile the scoped read-only usage ledger.
- [ ] Review all AI opinions and reply in their original discussions; leave
  manual merge to the user and keep remaining milestone acceptance explicit.

## Surprises & Discoveries

The earlier final run correctly recalled current values but invented an earlier
failed save, failed overwrite, and never-saved explanation in three answers.
The existing final-question reminder forbade this, but system instructions and
the tool description did not explain the evidence boundary and desired concise
response. A partial lesson conversation cannot establish cross-lesson history.

## Decision Log

- Supply the same evidence policy in system instructions, the current-question
  projection and the follow-up-only recall description. Use the original tool
  implementation and exact return contract, including its 8192-byte limit.
- Distinguish found, unavailable and too_large without inferring past writes.
  Answer current facts directly; admit uncertainty if explicitly asked why a
  past value changed. Only this run's remember result supports a write outcome.
- Preserve raw input authorization, original messages, history quotations,
  write limits, admission and deletion/version protections. Do not introduce
  output word filters, extra classifiers, new storage or a fabricated audit log.
- Treat this as model guidance requiring natural acceptance, not deterministic
  enforcement. Earlier failed evidence remains failed even if this sample passes.

## Outcomes & Retrospective

Implementation and acceptance are in progress. No new live result is claimed.
The original three failures remain in the memory quality reference.

## Context and Orientation

`src/api/flaskr/service/learn/follow_up_memory_writer.py` owns the native Agent,
the projected host reminder, policy-controlled remember and existing recall.
`agent/engine/recall.py` returns a request-local snapshot, not save history.
`test_follow_up_memory_writeback.py` drives real tool calls with FunctionModel;
it verifies protocol and trust boundaries, not language-model answer quality.
See the [quality reference](../../references/markdownflow-memory-quality.md#remaining-natural-answer-quality)
and the [completed current-value plan](../completed/mdf2-natural-memory-follow-up.md).

## Plan of Work

Add explicit provenance/response guidance to the existing follow-up tool and
instructions. Verify the wrapper does not change exact values, discovery,
same-run writes or raw permission. Release only this delta to sim, then run a
small natural HTTP journey on the existing dedicated internal learner.

## Concrete Steps

Use conda ai-shifu for backend commands. Run the focused memory-writeback suite,
then learning/profile tests. Regenerate knowledge indexes, check developer tools
and run lefthook all-files before plain git commit and GitHub-origin push.
Use the ordinary sim build/deploy workflow; verify both API hashes before HTTP.
Preserve private baseline/answers and query only this learner's usage window.

## Validation and Acceptance

Current-value reads must remain correct after cross-lesson update and menu
deletion, without unsolicited explanations that a past save failed or never
happened. An explicit historical question must quote the original preference,
not substitute the current one. An explicit why question must acknowledge the
absence of historical operation evidence. Exact UTF-8 results at 8192 bytes
must remain complete, and one byte over must return too_large. Preserve all
original elements, canonical profile, unrelated memory and completed sessions;
delete only the dedicated test preference. Reconcile new answer/progress IDs,
ownership, settlement and costs. Retain each initial failure without overwriting
or repeated paid calls to obtain a pass. Other models/providers and humans
remain separate acceptance items.

## Idempotence and Recovery

Sim shares the China production database. Only the dedicated internal learner
may receive temporary preference writes via existing HTTP APIs; no SQL writes.
Keep evidence in restrictive private files, never commit credentials or raw
transcripts. Preserve independent sim changes and all engine 1.0 code. Revert
only this runtime delta if required; do not alter production configuration.

## Interfaces and Dependencies

No schema, API, frontend, dependency, analytics or metering contract changes.
Use Pydantic AI's existing Tool description override; the recall implementation,
return bytes, raw learner write evidence and native bridge remain unchanged.

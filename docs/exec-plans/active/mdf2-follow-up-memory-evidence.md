# Separate current memory from past save outcomes

## Purpose / Big Picture

A current memory answer must report the verified value without inventing why
an earlier preference differs or is missing. Preserve historical messages and
do not treat assistant confirmations as database receipts. This is a focused
current-memory/causal-quality change, not a new memory audit log. Exact historical
quoting remains a separately demonstrated failure, recorded below.

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
- [x] 2026-10-10T06:37:31Z: Published #3087 as ed6d8d4e9 and sim delta
  dc69297b5. Both API replicas match 39 runtime hashes; API/web are ready.
- [x] 2026-10-10T06:37:31Z: Retained the first eight-HTTP replay: current
  values are correct, but a deleted fresh-lesson answer still implies never
  saved and discloses unrelated background. The historical answer labels an
  assistant's suggested wording as the learner's exact quote. This is failed
  quality evidence. All 17 requests settle (9.43 credits), with correct answer/
  progress/owner attribution; 168 original elements and completed state survive.
- [x] 2026-10-10T06:37:31Z: Added a separate post-read host interpretation
  using ToolReturn, preserving the original exact tool bytes. Clarified present-
  tense absence, unrelated fields and verbatim learner quotations. All 43
  focused cases pass, including gateway ordering and host-notice write rejection.
- [x] 2026-10-10T06:40:20Z: Six post-read integration cases fail without the
  correction. Restored code passes 3,076 learning/profile tests plus four subtests,
  one expected skip, developer tools and repository all-files gates.
- [x] 2026-10-10T06:52:03Z: Published correction 12aa03571 and sim d501ff4a0.
  Both ready API replicas match 39 runtime hashes; API/web are ready. Functional
  head technical CI passes, including runtime-harness.
- [x] 2026-10-10T06:52:03Z: Separate final eight-HTTP sample: four current
  reads and the explicit cause question do not invent earlier save outcomes.
  Fresh deleted-memory wording and unrelated background disclosure improve.
  Exact historical quotation still fails: the analogy is right but suggested
  assistant wording is claimed as a learner quote. Verbosity and generic unrelated
  field lists in the why answer also remain. Do not call full quality accepted.
- [x] 2026-10-10T06:52:03Z: All 18 final requests match eight new answer blocks,
  real progress and owner, zero failures/missing IDs, fully settled 10.25 credits.
  All 184 original elements, profile, unrelated memory, eleven progress rows and
  nine completed sessions survive; the temporary preference is deleted.
- [x] 2026-10-10T06:52:03Z: CodeRabbit substantively reviewed 12aa03571 with
  no actionable code comments; its docstring advisory has an original-discussion
  reply explaining the D102/D103 pytest exemption and verification. Codex/Devin
  first-head reviews have no findings; verify the final increment separately.
- [ ] Verify final documentation-head checks and any new opinions before
  handoff. Manual merge belongs to the user. Keep exact quotes and remaining
  milestone acceptance open in the named quality reference.

## Surprises & Discoveries

The earlier final run correctly recalled current values but invented an earlier
failed save, failed overwrite, and never-saved explanation in three answers.
The existing final-question reminder forbade this, but system instructions and
the tool description did not explain the evidence boundary and desired concise
response. A partial lesson conversation cannot establish cross-lesson history.
The first candidate still failed after read-tool output, and copied assistant
suggestions as a supposed exact learner quotation. Keep those failures; place
the fixed interpretation after exact reads, beside the result used to answer.

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
- Use ToolReturn's separate UserPromptPart for post-read host interpretation.
  Do not append metadata to the bounded tool value, add calls or modify stored
  history. Discovery returns stay unchanged. The notice never joins the raw
  learner input tuple used for write authorization.
- Keep this PR focused on the original save-cause defect. The attempted
  quotation guidance did not fix exact wording in either natural sample;
  transfer that newly demonstrated issue to
  [exact follow-up quotations](../../references/markdownflow-memory-quality.md#remaining-exact-follow-up-quotations).
  Do not relabel either failed quotation or broaden the current acceptance claim.

## Outcomes & Retrospective

The post-read correction passes the narrow final sample's four current-value
questions and explicit unknown-cause question without the earlier false save
diagnoses. Eighteen requests fully settle (10.25 credits), with correct current
answer/progress/owner attribution and all 184 original elements preserved.
The first eight-HTTP sample and 17 settled requests (9.43 credits) remain failed
quality evidence. Final exact quotation still fails; verbose suggestions and
generic unrelated field lists also remain. Neither this sample nor a prompt
assertion establishes complete memory, human, provider or language acceptance.
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

The original additional exact-quotation criterion remains failed, not waived
or marked passed. Transfer it to the named quotation backlog in the quality
reference. The final acceptance claim is limited to current facts and unknown
historical save causes, with all storage/protocol boundaries preserved.

## Idempotence and Recovery

Sim shares the China production database. Only the dedicated internal learner
may receive temporary preference writes via existing HTTP APIs; no SQL writes.
Keep evidence in restrictive private files, never commit credentials or raw
transcripts. Preserve independent sim changes and all engine 1.0 code. Revert
only this runtime delta if required; do not alter production configuration.

## Interfaces and Dependencies

No schema, API, frontend, dependency, analytics or metering contract changes.
Use Pydantic AI's existing Tool description override and ToolReturn content;
the recall implementation, return bytes, raw learner write evidence and native
bridge remain unchanged. The existing gateway maps tool returns before the
separate host UserPromptPart and counts both toward its total input budget.

# Ground historical quotations in original learner messages

## Purpose / Big Picture

A follow-up must not present an assistant's suggested wording as the learner's
exact earlier words. Read original user-role messages from the already authorized
bounded window; acknowledge when that window does not supply the original.

## Progress

- [x] 2026-10-10T07:04:16Z: Confirmed #3087 merged as 85ee0afff with final
  technical CI successful. Its current-memory/cause acceptance remains narrow.
- [x] 2026-10-10T07:13:00Z: Inspected source roles and retained failed sample.
  Sim uses the default ten-message window. The HTTP history initially appeared
  to contain both sources; read-only reconstruction using actual DB ordering
  showed the last ten were all answers. Run-local sequence numbers grouped
  questions before answers across requests, dropping original learner text.
- [x] 2026-10-10T07:15:28Z: All 75 focused checks pass, including exact
  UTF-8 boundaries, pagination, role exclusion and historical-write refusal.
  Two real-SDK quotation cases and two SQLite ordering cases fail on the
  corresponding prior implementations, then pass with the correction.
- [x] 2026-10-10T07:15:28Z: Learning/profile suite passes 3,089 tests plus
  four subtests and one expected skip. The first broad run exposed three old
  two-tool schema expectations; updated them to verify the new offset-only tool.
- [x] 2026-10-10T07:16:00Z: Developer-tool checks and all-files repository
  gates pass. Publication and natural sim acceptance remain pending.
- [x] 2026-10-10T07:17:40Z: Published #3088 as 2de5baf35 and initial sim
  delta df571448e. Sim gates/hooks and 116 focused cases pass. No paid sample
  has run against that candidate.
- [x] 2026-10-10T07:27:00Z: Accepted Devin and Codex provenance findings.
  Preserve raw ask content and existing payload.user_input, retain escaped
  transport prompts, and pass explicit proven quote sources separately from
  general history. Exclude ambiguous old brace encoding, embedded legacy
  history and synthesized classroom joins. Two literal-brace two-request
  SQLite paths fail on the old producer. Final 123 focused and 3,096 learning/
  profile checks pass, plus four subtests and one expected skip.
- [x] 2026-10-10T07:35:00Z: Published provenance correction d3bb23ad9 and
  sim de850ef9c, with both original Devin/Codex threads answered. Both ready
  sim API replicas match 42 runtime hashes. No paid sample has run yet.
- [x] 2026-10-10T07:36:16Z: Verified CodeRabbit finding that Live persistence
  trims transcripts. Two missing-raw Live cases fail before the correction;
  exclude those sources while retaining general conversation and supporting
  explicit raw provenance. All 3,099 learning/profile tests pass plus four
  subtests and one expected skip. Docstring advisory is a distinct policy decision.
- [ ] Publish final correction, answer CodeRabbit in its original discussion,
  verify final sim hashes and retain the distinct natural quotation sample.
- [ ] Reconcile usage/preservation, handle every AI opinion in its discussion.

## Surprises & Discoveries

The retained #3087 final answer uses the right library analogy but quotes an
assistant's re-save suggestion as learner text. The actual bounded model window
contained ten assistant answers, not the original request. API display order
was insufficient evidence of model input. A correct analogy is not proof of
an exact quotation. Preserve failed
transcripts rather than replaying unchanged code for a favorable answer.

## Decision Log

- Order anchor-bound sidecars by original question row ID and bind answer
  snapshots via their existing ask_element_bid. Run-local counters only order
  elements within a turn. Legacy unlinked rows retain insertion order.
- Add a read-only learner_quotes tool over immutable original user-role messages
  captured before host projection. Pass proven canonical ask inputs separately
  from general history; do not infer exactness merely from a user role. Exclude
  system/assistant/current-question text, synthesized classroom joins and
  ambiguously escaped old records. No additional history query or wider scope.
- Return only complete messages, with role, source index and explicit bounded-
  window coverage. Page within 8192 UTF-8 JSON bytes; never truncate a quote.
- Keep current recall, raw current-input permission, deletion/version guards,
  admission and three-write ceiling unchanged. Reserve bounded read calls in
  the same Agent budget. Do not add a classifier or output keyword filter.

## Outcomes & Retrospective

Implementation and model-quality acceptance are pending. FunctionModel verifies
source/protocol invariants, not whether a production language model follows them.
Exact quotation in #3087 remains failed evidence until a distinct new sample.

## Context and Orientation

follow_up_context.py selects anchor-bound user/assistant history with a default
of ten sidecar messages. follow_up_memory_writer.py projects prompts and runs
the native Agent. follow_up_quotations.py supplies exact learner-only evidence.
See [memory quality](../../references/markdownflow-memory-quality.md#remaining-exact-follow-up-quotations).

## Plan of Work

Exercise the new read tool through actual SDK/gateway mapping, including absent
originals and oversized entries. Publish a focused branch, preserve independent
sim work, verify runtime hashes, then sample known-original and absent-original
questions. Retain failures and report sample limits.

## Concrete Steps

Use conda ai-shifu; run focused tests then learning/profile regressions. Stage
plans before regenerating knowledge indexes. Run developer tools and all-files
lefthook gates before plain git commit and GitHub-origin push. Do not auto-merge.

## Validation and Acceptance

Only user-role historical messages may appear as quote sources. Preserve exact
Unicode/whitespace and complete JSON byte limits, pagination and missing-window
semantics. Reading old explicit remember text must not authorize a write or
restore deleted notes. Natural answers must quote the learner's source exactly,
or explicitly admit its exact wording is unavailable; assistant wording is not
an acceptable substitute. Preserve original elements, profiles, unrelated memory
and completed sessions; reconcile actual new answer/progress/owner IDs and costs.

## Idempotence and Recovery

Sim shares the China production DB. Use only the existing dedicated internal
learner via HTTP; no SQL writes. Use a new private evidence directory, do not
replace old failures. Preserve independent sim changes and engine 1.0. Revert
only this delta if needed; do not mutate production configuration.

## Interfaces and Dependencies

No schema, endpoint, dependency or metering change. Populate the existing
sidecar payload.user_input with raw input and pass an internal quotation_messages
tuple through the shared context DTO and native factory. General history stays
compatible; old ambiguous records are not decoded heuristically or rewritten.
The tool reads only captured sources and adds no persistent memory. Existing total
input budgeting covers its result; all source content remains untrusted data.

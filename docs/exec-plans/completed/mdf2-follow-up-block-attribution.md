# Attribute follow-up model usage to its answer block

## Purpose / Big Picture

Each text follow-up's model usage must identify its newly created answer block.
The learner's historical teaching anchor and current question are distinct
blocks. Existing user, course, lesson, progress, scene and learning mode remain
unchanged. This closes the missing block field seen in the natural course
ledger without rewriting historical usage or retiring engine 1.0.

## Progress

- [x] 2026-10-10T03:22:03Z: Confirmed #3083 manually merged as caa1211e1 with
  successful final technical CI. Preserved its separate causal-quality failures.
- [x] 2026-10-10T03:22:03Z: Traced the handler through the guardrail, ordinary
  LLM and native Agent factories: the immutable UsageContext was created before
  answer allocation and never included the new answer's generated_block_bid.
- [x] 2026-10-10T03:22:03Z: Sixteen regression cases failed on the missing
  block field, covering ordinary/fallback/synthesis, admission, preview, actual
  guardrail replies and interleaved request snapshots.
- [x] 2026-10-10T03:27:00Z: Constructed the frozen context after answer flush,
  before any billed call. All 41 handler cases and 3,097 learning/profile/metering
  tests plus four subtests pass, with one expected skip.
- [x] 2026-10-10T03:35:00Z: Developer tools, repository gates and hooks
  pass; published non-draft #3084 as fa6e735e3. Sim delta 2eb24b508 passes
  the same gates and all 41 handler cases.
- [x] 2026-10-10T03:35:00Z: Both ready sim-2eb24b5 API replicas match all
  39 runtime hashes. Three real HTTP follow-ups produce six successful, settled
  model requests (one semantic admission), 2.87 credits; every request matches
  its new persisted answer block and real progress, with zero missing fields.
- [x] 2026-10-10T03:35:00Z: Preserved all 162 original elements across nine
  lessons, profile and unrelated memory; deleted only the temporary test note.
  Eleven original progress rows and nine completed sessions remain unchanged.
- [x] 2026-10-10T03:35:00Z: Devin and Codex report no findings; CodeRabbit
  has no actionable code comments. Replied to its docstring coverage advisory
  in the original discussion, explaining behavior-named pytest exemptions.
- [x] 2026-10-10T06:16:06Z: Confirmed manual merge #3084 as a0ea6324a and
  successful final technical CI, including runtime-harness. No new actionable
  AI comments; the docstring advisory already has an original-discussion reply.
  Archive this accepted accounting scope. Historical-cause quality continues
  in the [evidence plan](mdf2-follow-up-memory-evidence.md).

## Surprises & Discoveries

All 49 earlier natural follow-up requests had matching real progress IDs and
settled successfully, but lacked generated-block IDs. The defect is a missing
handler binding, not a progress-record problem or settlement failure. A flushed
answer placeholder already exists before guardrail, provider or model calls.
Guardrail auditing still uses the learner's question block; its generated model
reply must use the answer block that is shown to the learner.

## Decision Log

- Construct the existing frozen UsageContext after answer allocation/flush,
  including the answer's actual ID. Reuse it for all existing factories.
- Preserve raw questions, SSE block identities, caller transaction boundaries,
  memory admission, retry accounting, external provider-only routing and Live.
- Do not backfill the earlier ledger or use old anchor/ask IDs. This does not
  change billing classification or costs and introduces no schema/configuration.
- Keep historical-save causal explanations as separate
  [quality work](../../references/markdownflow-memory-quality.md#remaining-natural-answer-quality).

## Outcomes & Retrospective

The focused binding and live default-LLM accounting sample pass: six requests
across three answers, including one admission, have matching answer and progress
IDs, correct owner/course and complete settlement (2.87 credits). Original
history, profile, unrelated memory and completed sessions are preserved.
Fallback, synthesis and guardrail are covered offline, not claimed as live
provider acceptance. Final technical CI passed and #3084 was manually merged.
The initial exact-substring marker assertion rejected an inserted space before
the digits; the original response was retained and its normalized marker was
verified without another billed request. A pre-rollout hash probe correctly
rejected mixed old/new pods; only the post-rollout 39-hash checks count as passed.
Prior missing-attribution rows and causal-quality failures remain unchanged.

## Context and Orientation

`src/api/flaskr/service/learn/handle_input_ask.py` allocates question and answer
blocks and supplies UsageContext to check_text and the shared/default factories.
The native Agent creates answer and admission GatewayModels with that same
context. `context_v2.py` persists the completed follow-up history and admitted
patch together. `metering/recorder.py` owns the frozen context and autonomous
usage persistence. See the [completed memory fix](../completed/mdf2-natural-memory-follow-up.md)
for the original ledger failure; no metering API change is needed.

## Plan of Work

Extend the real handler/factory coverage before changing construction order.
Assert reply ID agreement with SSE, correct scene/mode/progress and immutable
per-request snapshots. Cover rejection via the actual check_text orchestration.
Run learning/profile and metering checks, then normal build/deploy to sim.
Reconcile dedicated internal learner requests against persisted answer blocks.

## Concrete Steps

Use the ai-shifu conda environment from `src/api`: run the provider handler
suite, learning/profile and metering suites. From the repository root regenerate
knowledge indexes, check developer tools and run lefthook pre-commit all-files.
Commit with repository-default identity and push only GitHub origin. Open a PR
to main. Apply only the approved runtime/test delta to sim, preserving its other
changes; wait for the normal build and check both ready API replicas' hashes.
Use existing dedicated internal learner credentials privately for a small real
HTTP sample, then query the matching read-only ledger window after settlement.

## Validation and Acceptance

Ordinary LLM, fallback, GetBiji synthesis, all Agent requests including semantic
admission, and guardrail replies must receive the current answer's ID before
their model calls. Scene and learning mode remain correct for preview, read,
listen and classroom. Two deferred generators must retain distinct frozen
snapshots even on the same progress/anchor. External-only answers must not add
model calls and Live remains rejected on this path. In sim, every sampled actual
request must map to the new persisted answer block, matching user, course,
lesson and progress, with correct settlement. Preserve original course records
and unrelated memory. Full provider quality and historical causal explanations
remain out of scope.

## Idempotence and Recovery

Sim shares the China production database. Use only the existing dedicated test
learner and its own temporary preference; no other learner or config writes.
Keep failed evidence and earlier usage unchanged. Do not blindly repeat billed
requests. Preserve private tokens/transcripts locally with restrictive access.
Manual merge belongs to the user; retain 1.0 and avoid production deployment.

## Interfaces and Dependencies

No new API, frontend, dependency, migration or analytics event. UsageContext is
already frozen and includes generated_block_bid. Providers and gateway wrappers
consume it unchanged, and caller-owned units of work still own persistence.

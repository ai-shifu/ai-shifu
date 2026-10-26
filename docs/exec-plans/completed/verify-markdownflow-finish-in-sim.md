---
title: Verify MarkdownFlow completion in SIM
status: completed
owner_surface: backend
last_reviewed: 2026-10-26
---

# Verify MarkdownFlow completion in SIM

## Purpose / Big Picture

Deploy the accepted-completion repair from PR #3189 to SIM and exercise the
previously affected lesson with a real model. Check the model request boundary,
lesson output, completion state, session restoration and recorded usage.

## Progress

- [x] 2026-10-26 CST: Inspect the current SIM branch, actual images and shared-data
  topology; recover the affected lesson and historical model identifiers.
- [x] 2026-10-26 CST: Integrate the repair into SIM and build immutable images.
- [x] 2026-10-26 CST: Deploy and independently verify ready replicas and code.
- [x] 2026-10-26 CST: Run the original lesson through an isolated real-model
  preview session, inspect completion history and usage, then verify reopening.
- [x] 2026-10-26 CST: Record the result and remaining limits.

## Surprises & Discoveries

SIM shares production MySQL, Redis and billing. Its branch also contains old,
unmerged computed-example experiments and predates the shared engine extraction.
Deployment has no migration init container: the API starts gunicorn directly.

## Decision Log

- Preserve both branch histories in an integration merge, but use PR commit
  `fa4ffe1057f5e458c739a6e3cac3de655333fa12` for the complete API, Web and i18n
  runtime trees. This temporarily removes the older SIM experiments from the
  runtime; preserving their commits does not preserve their behavior.
- Do not run database migrations, reset learner progress or reuse historical
  learner sessions. Use a fresh debug-session identifier through the existing
  author preview API. This still uses the real gateway and billing path.
- Read configuration without exposing credentials; verify the actual model from
  the resulting message history rather than assuming a configured alias.

## Outcomes & Retrospective

The target completion contract passed a real-model SIM run of the original
lesson. No production service was deployed and no main-branch merge occurred.

Build [5501](https://ci.pillowai.cn/ai-shifu/ai-shifu/5501) produced
`sim-277e7ad` from integration commit `277e7ad9b9f19beaa17ee9287b4ed9186659f42c`.
API deployment record 3360 and Web record 3361 completed successfully. Independent
readback showed API 2/2 and Web 1/1 available, zero restarts, and the expected
images. The API runs pydantic-ai 2.53.0; `finish_run.py` SHA-256 is
`21dd413ac4f15dddc067d6ad3644f5151a756a2077ab363c2692203c112c3bcc`, identical
to the reviewed PR. The shared database already has revision `a7c1e3f5b9d2` and
the reset-record table; no migration was executed.

The original published lesson row 210649 has the expected 1,108-character script
and hash. Current draft course row 28229 selects slot 1; the real gateway used
`ark/deepseek-v4-1-flash-261017`, which differs from the historical `260910` model.
The current course prompt contains 928 characters, SHA-256
`d96bc7824bf5d0d3483d3dbe4d2f4c6a0e767903a891531a8a7945a6fff00447`.
This is a real current-runtime check, not a historical cost-controlled comparison.

The isolated debug run was `finish-ce460031c89f48d482b9952272760bf5`.
It returned five HTML presentations, seven text elements and the authored learner
interaction. The answer was accepted, the session finished, pending questions
cleared, and one finish call has its matching tool return. There are zero model
responses and zero retry prompts after that accepted completion. Its four real
model requests align exactly with four successful preview usage rows:

| Usage ID | Input tokens | Cached input | Output tokens | Credits consumed |
| --- | ---: | ---: | ---: | ---: |
| 812117 | 18,995 | 16,384 | 1,613 | 4.12 |
| 812118 | 20,681 | 18,816 | 112 | 4.15 |
| 812120 | 21,973 | 18,432 | 2,643 | 4.93 |
| 812121 | 23,564 | 20,608 | 84 | 4.73 |

The run consumed 17.93 credits in four distinct consumption ledger entries, one
per usage. Session totals match the usage table: 85,213 input, 74,240 cached input
and 4,452 output tokens. The final usage is the accepted finish; no usage follows
it in this run. HTTP correlation IDs appear in `bill_usage.trace_id`; internal
gateway request IDs differ and must not be confused with these HTTP IDs:

- Initial interaction: `632e0c0253ea442f9efb07bcd2aebde8`, two model calls.
- Answer and completion: `3ecf9bc94f994f5fae93715f21adc788`, two model calls.
- Reopen completed session: `97d0b3a4af3c43c8bb2405124ad4666c`, zero usage rows
  and zero added credits. The session history and usage remain unchanged.

One existing preview-protocol issue was also observed: reopening a completed
debug session emits only `preview_engine`, with no terminal `done` event, so the
strict SSE probe exits 1. Parent-commit and current debug-preview source are
identical; an offline reproduction with the real preview adapter produces the
same result in both versions. This is an existing host behavior, separate from
the verified zero-request/zero-usage completion contract, and remains a follow-up
for the preview host. No browser-layout acceptance or historical-model cost
comparison is claimed.

## Context and Orientation

CI/CD project 17 builds branch `sim`; the API target is
`ai-shifu/sim-shifu-api-deployment` and the Web target is
`ai-shifu/sim-cook-web-deployment`. The public origin is
`https://sim.ai-shifu.cn`. Automatic deployment is currently disabled in the
live project configuration.

The affected lesson is outline `70bb4e7bc528456a9e33899c91c36215` in course
`ba91abb2b57e4edfb5855144dc780220`. Its historical 1,108-character script has
SHA-256 `94f82238770f1f7861f01c952e9116536e54a68cc27ac1a6ba4a24ed926eae83`.
The observed historical model is `ark/deepseek-v4-1-flash-260910`.

## Plan of Work

Keep the tested runtime identical to the PR, build the SIM integration, deploy
only SIM targets, and confirm the new revision is serving. Drive the original
lesson via an isolated preview session and inspect real gateway requests and the
stored debug history around the accepted finish.

## Concrete Steps

Run the repository dev-tool and commit gates. Push the integration to `sim`,
track the matching build, and deploy its immutable image tag. Verify actual
running replicas. Read the original published lesson without changing it, then
use the existing creator authentication with a fresh preview debug session.

## Validation and Acceptance

- API, Web and i18n trees match the tested PR runtime exactly.
- The intended immutable images are ready on SIM and serve requests.
- A real model accepts completion, with paired tool history and no subsequent
  model response or retry after the final accepted completion batch.
- Visible lesson content, summary, usage and final-question answers survive.
- Reopening the completed debug session does not add model requests or usage.
- Report any model or prompt-version difference from the historical sample.

## Idempotence and Recovery

Pre-test SIM tip: `61c239b09012df0222531190d16f3f7a225f48ca`. Running images
before this task: API `sim-f14654a`, Web `20261023-f14654a`. Rollback can deploy
those immutable tags. The previous SIM runtime can also be restored in a new
commit from its saved tree; do not assume merging an old experimental ancestor
will restore files that this integration intentionally omits.

## Interfaces and Dependencies

The existing preview route uses independent Redis debug state with a 30-minute
TTL. It does not write learner progress or generated lesson records. Real
preview requests still create gateway usage and charge the course owner.

---
title: Verify MarkdownFlow completion in SIM
status: active
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
- [ ] 2026-10-26 CST: Integrate the repair into SIM and build immutable images.
- [ ] 2026-10-26 CST: Deploy and independently verify ready replicas and code.
- [ ] 2026-10-26 CST: Run the original lesson through an isolated real-model
  preview session, inspect completion history and usage, then verify reopening.
- [ ] 2026-10-26 CST: Record the result and remaining limits.

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

Verification is in progress. No production deployment or main-branch merge is
authorized by this plan.

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

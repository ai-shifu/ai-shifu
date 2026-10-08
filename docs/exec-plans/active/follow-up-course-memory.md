---
title: Explicit course memory in follow-up prompts
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# Explicit course memory in follow-up prompts

## Purpose / Big Picture

Continue merged PR 3034 by making authorized source-course values available to
text follow-up questions when the effective Course Prompt explicitly reads them.
Use the existing sidecar conversation, provider registry and SSE protocol.
The durable authorization contract remains
[Explicit Course Memory References](../../references/course-memory-references.md).

## Progress

- [x] 2026-10-08 00:48 UTC: Confirm PR 3034 merged and inspect both follow-up
  transports. Text loads profiles without an author context; the shared builder's
  fallback does the same. Live deliberately omits course instructions.
- [x] 2026-10-08 00:48 UTC: Pass the raw effective prompt to memory resolution
  before formatting, preserving supplied snapshots and Live isolation.
- [x] 2026-10-08 00:48 UTC: Verify 231 focused tests and four subtests, including
  real SQLite source revisions, revocation, isolation and provider prompts.
- [ ] 2026-10-08 00:48 UTC: Complete broader regression and repository gates,
  push a focused PR, reply to AI opinions and verify final CI and sim.
- [ ] 2026-10-08 00:48 UTC: Wait for the human main merge and verify rollout.

## Surprises & Discoveries

Live intentionally suppresses the Course Prompt to avoid text formatting rules.
It must not fetch references merely because a text lesson declares them. The
shared context builder resolves only its effective prompt, including a supplied
voice fallback. Existing explicit snapshots, including empty snapshots, remain
authoritative and do not trigger a second memory read.

## Decision Log

- 2026-10-08: Deliver the remaining follow-up read path as a focused continuation
  of explicit read-only sharing. Shared writing, semantic recall, compression and
  full agent-conversation follow-up integration remain separate work.
- 2026-10-08: Use the raw effective Course Prompt rather than learner input,
  generated conversation, another lesson's script or the composed prompt.
  Publication, destination definition, ownership and learner checks still apply.
- 2026-10-08: Keep provider adapters, history limits, persistence, protocol,
  environment flags and Live course-prompt isolation unchanged.

## Outcomes & Retrospective

Implementation and focused regression pass. Disabling effective-prompt resolution
makes five SQLite cases fail; disabling text Ask forwarding makes one contract
case fail. The corrected files are restored. Broader learning/profile regression passes 2,597 tests (one skipped, four
subtests). Review, CI, sim and human main merge are pending. This increment does not complete the
entire follow-up or memory milestone.

## Context and Orientation

`learn/context_v2.py` prepares text Ask snapshots. `follow_up_context.py` composes
shared prompts and anchor-bound history; `handle_input_ask.py` sends those messages
to LLM and external providers. `live_follow_up_routes.py` uses a voice fallback
without course instructions. `profile/course_references.py` remains the sole
source authorization resolver; no new reader or storage is introduced.

## Plan of Work

Pass raw author prompt context from text Ask and from the shared builder's
unsupplied-snapshot fallback. Exercise actual source data through composed LLM
and provider prompts, verify revocation on subsequent requests and retain the
existing text/voice tests. Record deployed checks and reply to every AI opinion.

## Concrete Steps

1. Update the two memory call sites and affected snapshot test contracts.
2. Add SQLite follow-up authorization and source-lifecycle regressions.
3. Run focused and learning/profile tests in conda `ai-shifu`, then dev-tool,
   harness, architecture and all pre-commit checks.
4. Push GitHub origin, open a non-draft PR and synchronize sim for isolated and
   fresh-guest acceptance. Never automatically merge main.

## Validation and Acceptance

Both LLM and external-provider text prompts contain the latest exact authorized
source value. An unrelated prompt, fenced example, comment, deleted source,
revoked publication, changed owner or different learner does not receive it.
Reads create no source or destination values. The supplied-snapshot contract,
post-stream persistence and Live suppression of course instructions still pass.

## Idempotence and Recovery

Resolution is read-only and rechecks authorization each request. Roll back this
increment independently if needed; source values and classroom history remain.
Use temporary SQLite for source fixtures and fresh internal-course guests for
HTTP checks; never reset real learners or seed shared production course data.

## Interfaces and Dependencies

Reuse `load_memory(..., reference_text=...)`, existing prompt formatting and
follow-up history. No migration, dependency, frontend, provider or environment
change. Production stays on MarkdownFlow 1.0; sim remains 2.0.

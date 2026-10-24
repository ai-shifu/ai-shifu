---
title: Explicit course memory in follow-up prompts
status: completed
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
- [x] 2026-10-08 00:57 UTC: Complete 2,597 learning/profile tests (one skipped,
  four subtests), all repository gates and six deliberate mutation failures.
  Open [PR 3035](https://github.com/ai-shifu/ai-shifu/pull/3035). Initial sim
  e3e9cf189 (build 372 / Drone 5163) has API 2/2 and web 1/1 ready; both API
  replicas pass 34 isolated checks and 14 module hashes. Fresh guest read,
  audio backfill (2.72 seconds), listen and follow-up (1.75 seconds) pass with
  unchanged canonical profile.
- [x] 2026-10-08 01:01 UTC: Evaluate CodeRabbit's additional argument assertion
  suggestion and implement it in all six existing shared-context permutations.
  Production runtime code remains identical to the deployed sim revision.
- [x] 2026-10-08 01:01 UTC: Push the test-only review correction, reply to every
  independent AI opinion, synchronize sim and confirm final CI.
- [x] 2026-10-08 01:02 UTC: PR 3035 passes final technical CI and was manually
  merged at 01:01:12 UTC as ba74b577e. Build 373 / Drone 5164 succeeds;
  production rollout verification is in progress.
- [x] 2026-10-08 01:02 UTC: Verify the production rollout and submit the pending
  test-only review correction as a separate PR; the user merged 3035 before
  that correction was pushed. Never merge main automatically.

- [x] 2026-10-08 01:18 UTC: PR 3036 manually merged at 01:09:33 UTC as
  250891ffb. Build 375 / Drone 5166 delivers the unchanged runtime. China API
  6/6 and US API 2/2 ready; each region passes 34 isolated checks and all
  14 runtime hashes match the accepted feature. Production remains 1.0.
  Final sim ac2ebb462 had API 2/2 and web 1/1 ready, with both replicas
  passing the same checks. All independent AI opinions were replied to.
  PR 3036 focused tests pass 124 cases; removing forwarding fails all six
  strengthened cases. Its applicable technical CI passes. Broader classroom
  context now continues in `follow-up-classroom-history.md`.

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

PRs 3035 and 3036 are manually merged and verified in sim and production.
The feature passes 2,597 learning/profile tests (one skipped, four subtests);
the review supplement passes 124 focused cases. Deliberate mutations fail the
five SQLite authorization cases, one text Ask contract and all six strengthened
shared-context assertions. The accepted runtime is identical across the two PRs.
Both sim replicas and one production pod per region pass 34 isolated checks and
14 runtime hashes. Actual guest read, audio backfill, listen and text follow-up
pass with canonical profile unchanged. All independent AI opinions have replies.
This closes explicit follow-up memory reads; shared writes, recall, compression
and complete conversation-context acceptance remain separately tracked.

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

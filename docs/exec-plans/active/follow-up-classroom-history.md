---
title: Preserve the classroom context of anchored follow-ups
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# Preserve the classroom context of anchored follow-ups

## Purpose / Big Picture

Continue merged PRs 3035/3036 with the next follow-up increment. A follow-up about
a 2.0 explanation must also see the recent preceding teaching and actual learner
answers. Keep the existing inserted sidecar, provider adapters and voice boundary.
The durable contract is [Follow-up Classroom Context](../../references/follow-up-classroom-context.md).

## Progress

- [x] 2026-10-08 01:13 UTC: Confirm 3036 merged and inspect the persisted 2.0
  block bridge and shared history builder. Existing sidecars discard prior lesson
  context; the no-sidecar fallback can include blocks after a selected old anchor.
- [x] 2026-10-08 01:16 UTC: Add SQLite regressions; six fail against the original
  runtime. Include real answers, exact anchors, limits, scope, lifecycle and shared
  LLM/provider composition. Implement bounded prior classroom reads.
- [x] 2026-10-08 01:17 UTC: Initial focused regression passes 122 tests.
- [x] 2026-10-08 01:23 UTC: Complete 2,616 learning/profile tests (one skipped,
  four subtests), including four actual Live-entry read/listen and preview/formal
  permutations. The local isolated probe passes 48 checks and 14 module hashes.
- [x] 2026-10-08 01:25 UTC: All repository gates pass. Reverting to the original
  runtime fails ten of the 19 new cases; restore the implementation before commit.
- [ ] 2026-10-08 01:25 UTC: Push GitHub origin, open a non-draft PR and
  synchronize sim.
- [ ] 2026-10-08 01:18 UTC: Verify both deployed sim replicas and fresh guest
  HTTP/read/listen/follow-up; reply to every AI opinion and check final CI.

## Surprises & Discoveries

2.0 already persists visible teaching and real learner answers in the existing
block tables. Reading raw agent sessions would introduce internal tool/prompt
content and version-dependent deserialization unnecessarily. A single generated
block can contain multiple elements, including text after the selected anchor.

## Decision Log

- 2026-10-08: Read active classroom blocks strictly before the anchor's block,
  then retain only the selected element from that turn. Scope to its attempt,
  learner, course and lesson; reject mismatched resolved anchors.
- 2026-10-08: Share the existing extra-message limit, prioritizing recent sidecar
  messages and keeping the anchor additional. Do not expand overall history limits.
- 2026-10-08: Preserve canonical/legacy sidecars and the unresolved-element legacy
  fallback. Do not add agent-session reads, provider calls, writes or migrations.

## Outcomes & Retrospective

Implementation passes 2,616 learning/profile tests and all repository gates.
The original runtime fails ten of the 19 new cases. Deployment, review and final CI remain
pending; the entire follow-up milestone and human teaching acceptance are not done.

## Context and Orientation

`agent/lesson_record.py` stores visible 2.0 teaching as content blocks. Interaction
blocks hold actual learner responses. `follow_up_context.py` builds history for
`handle_input_ask.py` and `live_follow_up_routes.py`; the former keeps existing
external-provider adapters. Sidecar element queries already isolate the anchor.

## Plan of Work

Use the existing active generated-block bridge to prepend bounded prior teaching
and answers to anchor-bound history. Keep the anchor exact, exclude later rows and
other sidecars, and validate shared transport/provider behavior through SQLite and
existing route/provider tests. Ship one independent PR, then verify sim.

## Concrete Steps

1. Add focused SQLite regression and confirm failure on the unchanged implementation.
2. Implement scoped reads and update the canonical reference and this plan.
3. Run learning/profile tests in conda ai-shifu, developer tools, generated indexes,
   harness, architecture and all pre-commit gates.
4. Push only GitHub origin, open the PR and integrate sim after current main.
5. Run isolated deployed probes and actual fresh-guest acceptance. Reply to every
   independent AI opinion with disposition and validation; never merge main.

## Validation and Acceptance

Both shared prompt streams include preceding explanations and real answers before
the exact anchor and its own sidecar. Future text, another anchor's questions,
deleted/retired rows, other attempts/users/courses/lessons and internal generation
configuration are absent. Zero and positive limits retain the anchor and stay
bounded. Missing active anchor blocks do not widen context. Reads create no rows.
Existing text/Live/provider and bound-publication tests remain green.

## Idempotence and Recovery

History loading is read-only. Roll back this increment independently without
changing stored sessions or progress. Construct fixtures only in local or isolated
pod SQLite; sim shares the production database. Real HTTP probes use fresh internal
course guests and never reset existing learners or seed shared course fixtures.

## Interfaces and Dependencies

Reuse generated blocks, selected element snapshots and the shared builder. No new
provider, environment, frontend, dependency or database contract. Production stays
on the 1.0 engine while sim remains fully 2.0.

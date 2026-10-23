---
title: Profile questionnaire MarkdownFlow 2.0 runtime
status: active
owner_surface: backend
last_reviewed: 2026-10-23
---

# Profile questionnaire MarkdownFlow 2.0 runtime

## Purpose / Big Picture

Run the complete frozen Profile questionnaire in one native MarkdownFlow 2.0
Session. The shared engine owns progression, questions, deferred answers,
history, memory and completion. The host retains ownership, Redis persistence,
locks, request replay, frontend rendering and private profile transformation.
The canonical contract is in
[`profile-onboarding-startup.md`](../../product-specs/profile-onboarding-startup.md).

## Progress

- [x] 2026-10-23 CST: Migrated execution from the 1.0 provider to shared 2.0
  primitives and opened PR #3161; completed the initial review cycle.
- [x] 2026-10-24 CST: Confirmed that the initial per-block compatibility layer
  duplicated native progression; pulled the PR branch before refactoring.
- [x] 2026-10-24 CST: Removed block execution and cursor state; the complete
  original questionnaire is one native Session's ScriptBundle.
- [x] 2026-10-24 CST: Coordinated request revisions, native pending question IDs,
  frontend accepted-answer state and private summary phase across all callers.
- [x] 2026-10-24 CST: Passed 1,175 shared engine/host tests, complete frontend
  TypeScript checking against the pinned UI package, and repository boundaries.
- [ ] 2026-10-24 CST: Complete the final focused regression and pre-commit gates.
- [ ] 2026-10-24 CST: Update PR #3161, process live review and confirm exact-head CI.

## Surprises & Discoveries

- The original implementation created one Session per authored block. This
  reused the execution kernel but retained 1.0 orchestration. It is superseded
  by a complete-script Session; compatibility must not drive script progression.
- Native Engine can defer several interactions in a single turn. The host
  displays the first and persists native answers until the complete batch can
  resume. A partial batch can change durable state without increasing Engine.turn.
- Appending the private summary to the public script could expose personal
  profile text through ContentDelta. Private transformation therefore uses the
  existing provider and prompts after native completion, outside the script.
- The local shared node_modules has an older MarkdownFlow UI package. Complete
  TypeScript validation uses an isolated mapping to the pinned package without
  changing shared dependencies or lockfiles.

## Decision Log

- Reuse Engine, ScriptBundle, Session, StartTurn, ContinueTurn,
  InteractionResponseTurn, the synchronous bridge, gateway, interaction renderer
  and pager through the public learn.agent.api boundary.
- Preserve authored 1.0 controls with a source-contract check over all controls,
  without indexing them, restricting their execution order, counting pending
  calls or splitting script execution. Natural-language 2.0 scripts are allowed.
- Replace block cursor fields with turn_index, a host request revision used
  solely for stale-request rejection and replay. Every successful committed
  request increments it, including an intermediate native batch answer.
- Preserve answer bindings and mixed inputs. Public question controls follow
  native pending order; only accepted input marks the matching frontend control
  answered. Native tool IDs are independent of stable presentation identities.
- Generate private drafts from accepted native interaction answers and validated
  supplemental evidence. Exclude nickname, navigation clicks, instructions and
  model memory notes. Do not create a separate summary Engine Session.
- Schema 3 expires incompatible schema 1/2 per-block sessions. Deploy matching
  API and web revisions together; the existing missing-session path allows restart.
- Preserve existing analytics meaning, ownership, expiration and nonbillable
  provider routing. No new package, database migration or user action is needed.

## Outcomes & Retrospective

Implementation is complete and final validation/review/CI convergence is in
progress. No merge or deployment is authorized. The first migration retained
too much old orchestration; this revision makes native state authoritative.

## Context and Orientation

Profile learner routes and operator previews enter profile_research.api.
The runtime owns request admission and atomic host persistence; engine_runtime
adapts a native turn and projects accepted evidence. Redis stores the full native
Session in the owner-scoped record. Frontend clients consume native pending and
finished state through the existing cumulative element SSE presentation.

## Plan of Work

Remove block execution rather than renaming its cursor. Coordinate producers,
DTOs, routes, frontend hooks, controls and tests around request revisions. Keep
source validation at the authoring/control boundary. Validate real native
pause/resume behavior, replace obsolete block-only tests, update canonical docs,
then push and converge current review plus exact-head checks.

## Concrete Steps

1. Persist one native Session containing the complete original document.
2. Dispatch native turns and retain every deferred call and accepted result.
3. Adapt public output and expose native waiting/completion to both clients.
4. Transform accepted evidence privately after completion or assistant import.
5. Verify focused tests, shared engine tests, static and repository gates.
6. Update the existing ready PR, process review and verify terminal CI results.

## Validation and Acceptance

The same native Session and complete script must survive several questions,
branches and Redis round trips. Multiple pending calls must collect independent
answers, reject stale tokens and replay an identical request without model calls.
Malformed answers remain pending without contaminating profile evidence. Retried
model text must not appear in public content or private summaries. Private
transformation/provider/cache failures preserve the previous durable native
state and replay identity. Native completion and assistant import must return
private drafts only in terminal events. Learner/admin clients must use the
same contract, enable only the current pending control and continue from native
state rather than authored block counts. Expired old schemas permit restart.

## Idempotence and Recovery

Work remains on the feature branch for PR #3161. No database schema changes.
Keep ownership locks through persistence and readback of uncertain assistant
writes. Deploy API workers and web together. Old schema 1/2 sessions cannot be
converted reliably from a single saved block and are rejected as missing.
Rollback requires expiring new active sessions or waiting thirty minutes before
restoring the older runtime. No merge or deployment is part of this task.

## Interfaces and Dependencies

Public requests use expected_turn_index, request_id and the pending native
expected_interaction_id. Done events expose next_turn_index, input_accepted,
pending_interaction_ids, awaiting_input and done. A phase event announces private
summary work. The existing profile store, provider, interaction input utility,
renderer and analytics remain in use. No dependency pin changes are required.

---
title: Independent Profile collection sessions
status: completed
owner_surface: backend
last_reviewed: 2026-11-07
---

# Independent Profile collection sessions

## Purpose / Big Picture

Allow the same learner to collect Profile information in independent browser
dialogs concurrently. Each generated session advances and rewinds on its own.
A draft is reviewed before saving, and the latest successful explicit save
sets the account's learner profile.

## Progress

- [x] 2026-11-07 12:38 CST: Verify browser-local session IDs and serialized
  canonical profile saves.
- [x] 2026-11-07 12:43 CST: Remove owner-wide supersession and run exclusion.
- [x] 2026-11-07 12:43 CST: Verify independent progress, cleanup and replay;
  343 runtime and route tests and 50 profile save tests passed.
- [x] 2026-11-07 12:47 CST: Complete focused checks and independent review;
  prepare the isolated change for the existing PR.

## Surprises & Discoveries

The frontend already creates separate session IDs per dialog. The backend
invalidates older sessions through one active owner-purpose pointer and holds
an owner lock across model generation. The canonical profile already uses a
database user-row lock for saves.

## Decision Log

Retain owner and purpose authorization, per-session locks, request revisions,
exact retries, and the existing expiration. Clean up only the supplied session
after explicit completion or skip. A request without a collection session ID
has no session to clean up. Interpret completion as the learner's explicit
save, preserving the review step.

## Outcomes & Retrospective

Implementation and focused verification are complete. The regression suites
cover independent runs, same-session exclusion, authorization, replay, targeted
cleanup, and both explicit save orders. Independent code review found no
blocking issues. CI and review follow-up are tracked on PR #3357. Generic
stale-revision recovery remains paused for product discussion.

## Context and Orientation

`profile_research/session.py` and `runtime.py` own transient session state.
`route/profile.py` triggers best-effort cleanup after a durable save or skip.
`profile/learner_profile.py` serializes canonical profile saves.

## Plan of Work

Store each session independently and lock only that session during a run,
import or deletion. Remove the active pointer and its owner-wide lock. Retain
independent lifecycle cleanup without changing draft or canonical save APIs.

## Concrete Steps

1. Remove active-session supersession and validation.
2. Remove unused public active-session cleanup helpers and consumers.
3. Update concurrency, deletion, uncertain-write and replay regressions.
4. Document independent browser journeys and the last-save rule.

## Validation and Acceptance

Two same-owner sessions must remain usable. A locked session must not block a
different session, while the same-session lock continues to reject overlap.
Completing or skipping one session must leave the other intact. Missing IDs
must not remove another dialog's work. Owner and purpose checks and exact
request replay must remain valid.

## Idempotence and Recovery

The session ID scopes state, lock and replay identity. Uncertain writes use
the existing durable readback. Old active-pointer Redis keys can expire on
their existing TTL. Deploy the API worker change together to avoid a remaining
older worker reintroducing supersession.

## Interfaces and Dependencies

The frontend already sends its own session ID on run, import and explicit
completion. Existing journey and outcome analytics retain their payloads and
count concurrent dialogs as separate journeys.

---
title: Editor Debug Cross-Lesson Memory
status: completed
owner_surface: backend
last_reviewed: 2026-11-06
canonical: false
---

# Editor Debug Cross-Lesson Memory

## Purpose / Big Picture

A topic saved by the model during editor Debug should appear in the variable
panel and be available to the next lesson when the write has course scope.

## Progress

- [x] 2026-11-06 CST: Reproduced the lost overwrite in the backend stream and browser cache with offline models and synthetic SSE.
- [x] 2026-11-06 CST: Implemented and verified saved-turn publication, browser cache handoff, and automatic continuation.

## Surprises & Discoveries

The model's write already reaches the Debug session cache. Ordinary answers
do not publish a saved snapshot, and answer-edit snapshots update only the
current panel. The browser caches the initial interaction answer.

## Decision Log

- Use the current adapter boundary and an explicit committed Debug event.
- Keep the session snapshot and course writes separate to preserve memory scope.

## Outcomes & Retrospective

The offline model and editor tests verify that the committed topic reaches
the next request and that lesson-only writes remain local to the panel.

## Context and Orientation

The backend runner in `src/api/flaskr/service/learn/agent/run_agent.py` owns
native writes and turn saves. `debug_session.py` adapts Debug events. The
editor hook in `src/web/src/components/lesson-debug/` manages the current
panel and browser course cache.

## Plan of Work

Capture saved variables and eligible writes on the current Debug request.
Publish them at the matching adapter boundary. Keep course seed values
separate from transient panel state and retain explicit author edits.

## Concrete Steps

Run the Debug session and lesson entry pytest suites, then run the editor and
Debug hook Jest suites and repository checks.

## Validation and Acceptance

After a recommended topic is saved, the panel and next lesson request use
the concrete topic. A session-only write changes the current panel. Cover
paused, failed, and superseded requests and automatic continuation.

## Idempotence and Recovery

Applying a committed value again is a key overwrite. Closing or superseding
a request fences out its later updates.

## Interfaces and Dependencies

The event contract is documented in
`docs/references/markdownflow-draft-classroom-history.md`.

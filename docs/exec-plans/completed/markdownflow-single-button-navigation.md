---
title: Use single-button navigation in MarkdownFlow
status: completed
owner_surface: learner
last_reviewed: 2026-11-18
canonical: false
---

# Use single-button navigation in MarkdownFlow

## Purpose / Big Picture

Use the same MarkdownFlow control for every continue button. Learners click the
authored button to advance. Lessons without a requested pause advance on their
own, and a fixed selection remains ineligible for learner memory.

## Progress

- [x] 2026-11-18 12:42 CST: Traced navigation through the tool, renderer,
  Course and Profile runtimes, and offline replay catalog.
- [x] 2026-11-18 12:48 CST: Migrated the native schema, renderer, hosts, and replay fixtures.
- [x] 2026-11-18 12:50 CST: Verified the engine, Profile, Course history and
  protocol regressions, the interaction catalog, and the translation contract.

## Surprises & Discoveries

Authored navigation already uses `single` in normal Course and Profile flows.
The obsolete type supplies separate defaults and submission text. Exercise
statistics already checks the purpose of a single-button click in its evidence.

## Decision Log

- Use one explicit `single` option with its authored display and stored value.
- Keep the host's automatic continuation for unsolicited pauses.
- Keep the memory admission rule based on the resolved control.
- Drop compatibility for saved sessions that contain controls of the retired type.

## Outcomes & Retrospective

Course and Profile use ordinary `single` submissions for continue buttons.
The engine suite passed 3,394 tests. All 57 offline interaction cases met their
expectations. The host tests verify click handling, replay, and Profile evidence.

## Context and Orientation

The native tool and session live under `src/api/markdownflow/engine/`. The
library renders the same controls for Course and Profile. See the
[engine design](../../design-docs/markdownflow-engine-library.md) and
[memory admission rules](../../product-specs/learner-memory-admission.md).

## Plan of Work

Retire the dedicated type from validation, storage, rendering and model
instructions. Move pause handling onto the single-button shape where a
navigation click is requested. Update dependent host code and replay fixtures.

## Concrete Steps

Run the engine, Course and Profile tests with pinned backend dependencies. Replay
the interaction catalog and run the repository checks before opening the PR.

## Validation and Acceptance

An authored continue button keeps its label and value. A valid click advances
the lesson, including after restoring a newly saved session. An unsolicited
pause in a lesson without an authored pause advances automatically. One fixed
option skips memory and genuine choices with alternatives still save answers.

## Idempotence and Recovery

Submitting a continue button uses the same validation and queue handling as
other `single` controls. Existing memory records need no migration.

## Interfaces and Dependencies

`interact` takes the existing `single` type with one explicit option. Course
and Profile keep the existing MarkdownFlow button wire format.

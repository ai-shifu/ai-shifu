---
title: Use one question for MarkdownFlow answers
status: active
owner_surface: learner
last_reviewed: 2026-11-08
canonical: false
---

# Use one question for MarkdownFlow answers

## Purpose / Big Picture

Use the learner-facing question from `interact.question` as both the displayed
question and the key under which the course records the answer. A lesson can
ask an exercise without declaring a key in its source and still record the
response. Preserve earlier named answers, short references and pending turns.

## Progress

- [x] 2026-11-08 08:27 UTC: Confirmed that all answer interactions record course
  memory and that historical short references must continue to resolve.
- [x] 2026-11-08 08:47 UTC: Implemented the engine, presentation, storage and
  editor Debug alias path. Verified the portable suite, the focused frontend
  tests, and upgrade and downgrade of the alias table on SQLite.
- [x] 2026-11-08 08:53 UTC: Passed the engine and Profile suite and the
  affected course, memory, and guest migration tests. Verified queued Profile
  questions after cache reload and completed the repository checks.
- [ ] Verify remote checks on the updated pull request and await maintainer review.
- [x] 2026-11-08 09:07 UTC: Verified model-first question delivery, with no
  generated question or duplicate title from tool arguments. Passed 3,507
  engine and Profile tests, 379 course-host tests, and repository checks.
- [x] 2026-11-08 09:20 UTC: Replaced alias matching and persistence with exact
  authored question text. Added regressions for identical controls, localized
  and omitted input hints, and direct recall of an older course answer.
- [x] 2026-11-08 09:35 UTC: Verified review fixes for question visibility,
  pending structured feedback, retained system bindings, navigation values,
  and text-input repair. The engine suite and repository checks passed.

## Surprises & Discoveries

The old title was not rendered in reading mode. Simply renaming the field
would leave readers reliant on a separately generated question. The current
runtime also serializes raw calls and pending controls independently. Exact
authored question text distinguishes otherwise identical bound controls.

## Decision Log

- 2026-11-08: New answer calls carry complete question text, including for
  corrections. Authored navigation and `confirm` do not collect an answer.
- 2026-11-08: The model asks each ordinary question in prose before calling the
  tool with the same wording. The engine sends the controls without creating
  a question or panel title from the call. Historical question metadata retains
  its display treatment.
- 2026-11-08: An answer control waits for visible model-authored question prose.
  Retry missing or filtered questions. On Profile reload, restore saved structured
  guidance ahead of its pending correction control.
- 2026-11-08: The text inside an authored binding is the question and storage
  key, even when it is a short label. Remove the unreleased alias table and
  use exact keys across courses, Profile, and editor Debug.

## Outcomes & Retrospective

The engine uses the text inside the binding as the question and memory key.
Explicit references can read earlier course answers by their original text.

## Context and Orientation

`src/api/markdownflow/engine` owns model tools, question rendering events, and
portable session history. `src/api/markdownflow/interaction_rendering.py`
rebuilds the controls. The application maps events to course and Profile
streams and writes admitted course memory with its existing transaction.

## Plan of Work

1. Replace model-facing title and binding inputs with `question`. Normalize old
   calls for replay without changing historical answers or their identifiers.
2. Prompt the model to ask the question before the controls. Keep structured
   correction feedback and authored navigation boundaries. Use options for
   new navigation labels.
3. Record accepted course answers under the exact question, including the
   literal text of an authored binding. Keep system profile and other course
   scopes separate.
4. Migrate Profile evidence, update canonical guidance, and verify all paths.

## Concrete Steps

Run the offline engine suite under `src/api`, followed by affected course and
Profile tests and repository harness checks. Regenerate the knowledge index
after updating the plan and canonical references.

## Validation and Acceptance

A new answer call without `question` is rejected. The model's question appears
before the controls, and an accepted answer is recorded under that exact
question. A bound short label is used verbatim in prose, the tool call, and
the memory key. Continue and navigation clicks do not update memory. Legacy
sessions and Profile evidence continue to restore and resume.

## Idempotence and Recovery

Do not rewrite historical tool history or answers. Read old and new stored
shapes during the transition. Persist course memory in the accepted turn's
existing transaction. The released schema needs no migration for this change.

## Interfaces and Dependencies

`interact.question` is the model-facing source for presentation and new course
answer identity. `options` and `placeholder` remain control configuration. The
existing interaction and memory events carry normalized state into application
storage. No changes to analytics payloads are needed for this contract.

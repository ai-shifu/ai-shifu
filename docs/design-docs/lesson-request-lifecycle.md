---
title: Shared lesson request lifecycle
status: implemented
owner_surface: learner
last_reviewed: 2026-10-26
canonical: true
---

# Shared lesson request lifecycle

## Boundaries

Formal learning, whole-course preview and editor debug use the shared
MarkdownFlow course host. They retain different content sources, permissions,
session storage and history policies. The teaching engine and the lifecycle of
one HTTP response are shared concerns.

Three endings have different meanings:

- A native `TurnDone` ends an engine turn. The course host may automatically
  continue teaching before it pauses or finishes.
- A terminal SSE `done` ends one HTTP response. A pending interaction can remain
  answerable in the next request.
- A finished Session ends the lesson. The accepted engine `finish` must not
  request another model response, as specified in the
  [engine design](markdownflow-engine-library.md#completing-a-turn).

A transport terminal event must not independently mark a lesson complete, clear
a pending answer, or create a generated learning block.

## Backend event contract

Keep the current element protocol and legacy compatibility:

- `done` with `is_terminal: false` is a block boundary. It can precede more
  content or the terminal event and must not close the transport.
- `done` with `is_terminal: true` closes the HTTP response. An existing terminal
  event must not be duplicated.
- On normal exhaustion without a terminal event, including an already-finished
  session producing no teaching events, the request boundary adds one terminal
  event. The event is ephemeral and does not create history or element rows.
- Error translation retains the existing business-error payload and supplies
  the terminal event at the request boundary when that path maps the error.
- Client disconnect, generator cancellation and source cleanup do not fabricate
  successful completion or yield more events to a closed consumer.
- Session saving, committed progress changes and required audio-readiness
  notifications happen before the terminal event, because clients stop reading
  on that event.

The legacy editor-preview source also holds its terminal event until the
existing preview context cache has been updated. The common boundary can then
close that source without losing the current reply from the next turn's history.

Shared lifecycle handling belongs at the existing serialization boundaries:
the formal run queue consumer and the editor-preview response wrapper. The
debug generator supplies engine events and its preview-engine identifier; it
does not implement a separate normal-EOF completion rule.

## Frontend transport contract

Formal learning and editor preview use the shared lesson SSE transport, built
on the existing request, language, trace and business-error infrastructure.
The page and editor hooks continue to own their respective history, rewind,
element rendering and interaction state.

Transport settlement is once per source. Terminal, EOF, error and cancellation
must release the active request's streaming state without treating EOF as proof
that the lesson completed. A retired source cannot change the state of its
replacement. Legacy completion events remain supported, and an intermediate
block event is not a request terminal.

Business-error detection must complete before normal EOF cleanup is classified;
an authentication or credit error returned as JSON is still an error, not an
empty successful lesson. Authentication, locale and trace headers, billing-error
audience and existing analytics callbacks stay on their shared owning paths.

This work adds no new interaction, endpoint or analytics family. Existing
product events keep their names, payloads, eligibility and business triggers;
transport cleanup is not a new lesson-completion signal.

## Session saving

The course host selects a save strategy once per turn. The streaming conversion
then calls one save interface at its existing persistence boundaries:
prepared feedback before visible output, terminal turn completion and retained
partial output after interruption.

The debug strategy uses the existing temporary, script-bound Redis session.
Formal and whole-course preview strategies use the existing persistence path,
including their separate namespaces, generation checks, reset/rewind behavior,
memory handling and transaction boundaries. Dynamic turn metadata is read when
saving, not frozen before the bridge starts.

Shared save dispatch must not change whether a save is kept or discarded, move a
save across a generator yield, persist preview teaching into learner progress,
or introduce a database/cache schema change.

## Verification

Regress the empty finished-preview response, ordinary completion, interaction
pause, repeated terminal events, errors, disconnects and source cleanup at the
request boundary. Verify frontend EOF and stale-source races with business-error
fallback and existing consumers. Exercise each save strategy at every persistence
boundary, including failed saves, discarded generations and partial output.

Use isolated debug sessions for real-model SIM checks. SIM shares production
storage and billing; report the actual model and deployed revision, compare
Session usage with recorded gateway usage, and verify completed-session replay
adds no model calls or credits.

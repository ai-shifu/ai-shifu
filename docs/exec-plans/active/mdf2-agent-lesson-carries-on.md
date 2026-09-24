# MarkdownFlow 2.0: a lesson carries on until it waits or ends

## Purpose / Big Picture

A 2.0 turn ends one of three ways: waiting on the learner, finished, or simply out of content
for that turn (`TurnDone(reason="end")`) -- the model stopped without calling `finish`, which it
often does even when the script is all delivered. That third ending reached the browser as
nothing: the element protocol keeps a non-terminal boundary off the stream (`runscript_v2`,
`_should_suppress_live_payload`, since #1477), and the stream then closes with a terminal event.
The browser reads that as the request being over and asks for nothing more. So a lesson whose
last turn ended that way stayed "in progress" -- with everything already on the page -- until
the learner opened it again, at which point the browser's history-load path asked for a turn.

That turn was the host's "continue", and it produced the second symptom. Told to carry on with
nothing left, the model either wrote the previous turn again (caught by `_repeats_previous_turn`,
but only after the copy had streamed to the learner) or called `finish` first and then wrote a
line -- the previous turn's last sentence, or "脚本内容已全部呈现完毕。" -- which the engine let
through because the turn had delivered nothing yet. Observed on sim, 2026-09-24, boundary lessons
3-2, 3-3 and 4-2: a duplicated sentence appeared on switching back to the lesson, and only then
did its status change.

After this change a request runs turns until one waits or ends, the way a 1.0 request runs block
after block; a host-initiated continue never shows the learner the previous turn again, nor
anything written after `finish`; and opening a finished lesson writes nothing.

## Progress

- [x] 2026-09-24: Reproduced on sim from the stored sessions and rows (three lessons), then
  locally with the same course and model (`ark/deepseek-v4-1-flash-260910`).
- [x] Engine: on a continue turn, text is held while it reads as the previous turn starting over
  and released whole when it differs; a repeat (whole or prefix, at or above the floor) is
  dropped and ends the lesson; nothing written after `finish` is shown. Tests fail with the
  change reverted.
- [x] Host: `run_agent_lesson` returns a `TurnOutcome`; `agent_lesson_events` runs the next turn
  in the same request while the last ended with content still to come and said something, up to
  `_MAX_TURNS_PER_REQUEST`. Tests fail with the change reverted.
- [x] Host: a turn asked of a finished session runs nothing and writes nothing (it used to leave
  an empty block, an element and the outline's rows on every visit, then an orphan element).
- [x] Local browser verification: 3-2 (content only), 3-3 (code block and table), 4-2 (a question
  then a closing line). Each finished within one request, once, with no duplicated text; the
  finished lesson revisited wrote no rows.
- [ ] Sim verification after merge.

## Surprises & Discoveries

- The browser's `TEXT_END` auto-continue branch is dead code under the element protocol: the
  non-terminal boundary never reaches it, and the framing appends a terminal event to every
  stream that lacks one. The only auto-run the browser does is on loading a lesson whose history
  does not end on a question -- which is why a revisit "fixed" the status.
- `run_agent_lesson` delegates to `_stream_turn` with a bare `yield from`, so a return value set
  in `_stream_turn` was silently dropped; the first local run showed the loop not looping.
- A terminal event yielded from the host on a finished session is persisted as an element with no
  block (`progress_record_bid=""`), while the framing's own closing event is ephemeral.

## Decision Log

- The lesson is carried on by the host, not by the browser. The browser has no way to tell a
  turn's end from the lesson's under the element protocol, and 1.0 never needed it to.
- A turn that ended out of content having said nothing is not followed: the model has nothing to
  add and did not say so, and asking again would loop. The engine's turn limit is the final brake;
  `_MAX_TURNS_PER_REQUEST` is only a guard against a model that keeps writing something new.
- The held text is compared whitespace-insensitively against the previous turn's text, the same
  normalisation `_repeats_previous_turn` uses. A short repeat (under `_REPEAT_FLOOR_CHARS`) is
  still shown, as before: a drill line said twice is the script's.
- On a continue turn, text after `finish` is never shown, regardless of whether the turn had
  delivered anything. The "closing line after `finish`" exception stays for other turns.

## Outcomes & Retrospective

(To be filled in after sim verification.)

## Context and Orientation

- `src/api/flaskr/service/learn/agent/engine/engine.py` -- `run_turn`, `_repeats_previous_turn`.
- `src/api/flaskr/service/learn/agent/run_agent.py` -- `run_agent_lesson`, `_stream_turn`,
  `TurnOutcome`.
- `src/api/flaskr/service/learn/agent/lesson_entry.py` -- `agent_lesson_events`, the loop.
- `src/api/flaskr/service/learn/runscript_v2.py` -- `_should_suppress_live_payload` and the
  closing event the framing appends (unchanged; the reason the browser cannot carry on).

## Validation and Acceptance

- A pure-content 2.0 lesson finishes within one request with no learner action.
- A continue turn that repeats the previous turn, or writes after `finish`, shows nothing new.
- Revisiting a finished lesson adds no rows.
- `cd src/api && python -m pytest tests/service/learn -q` (2050 passed).

# MarkdownFlow 2.0: a lesson carries on until it waits or ends

> Lifecycle review, 2026-09-26: Completed original scope. Recorded deterministic and live continuation simulations complete the approved scope; no engine implementation is changed by this audit. Merge evidence: [#2953](https://github.com/ai-shifu/ai-shifu/pull/2953) (`d5ba0d03e`)

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
  in the same request while the last ended with content still to come and said something. Tests
  fail with the change reverted.
- [x] Host: a turn asked of a finished session runs nothing and writes nothing (it used to leave
  an empty block, an element and the outline's rows on every visit, then an orphan element).
- [x] Local browser verification: 3-2 (content only), 3-3 (code block and table), 4-2 (a question
  then a closing line). Each finished within one request, once, with no duplicated text; the
  finished lesson revisited wrote no rows.
- [x] 2026-09-24 17:33 CST: Sim verification on the sim branch (image `sim-bf003b3`): 3-2 finished within one request (two turns, 8 s) and 4-2 right after its answer, each sentence shown once; the stored sessions show the model wrote "本节内容已全部呈现完毕。" and the answer line again after `finish`, and neither reached the page.

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
  add and did not say so, and asking again would loop. The engine's turn limit is the brake for a
  lesson that will not end; it ends the lesson as finished. There is no cap per request (review):
  one would close the stream mid-lesson with a terminal event, which the browser cannot tell from
  a finished request, so a long lesson would stop until reopened -- the symptom being fixed.
- A question the model typed as text (`?[...]`, shown by `_narrated_question`) makes the turn a
  wait: `TurnOutcome.reason` is "interaction" for it, or the loop would run past it (review).
- On a continue turn, text held back when `finish` is seen is dropped whatever its length
  (review suggested keeping it below the repeat floor): the floor exists for a script that says a
  short thing twice as content; a turn that says the previous turn's opening words and then
  `finish` on being told to carry on has not delivered content, it has repeated and stopped.
- The held text is compared whitespace-insensitively against the previous turn's text, the same
  normalisation `_repeats_previous_turn` uses. A short repeat (under `_REPEAT_FLOOR_CHARS`) is
  still shown, as before: a drill line said twice is the script's.
- On a continue turn, text after `finish` is never shown, regardless of whether the turn had
  delivered anything. The "closing line after `finish`" exception stays for other turns.

## Outcomes & Retrospective

Both symptoms were one gap seen from two sides: the browser cannot carry a 2.0 lesson on, and the host had left that to it. Carrying on in the request also put the model's "nothing left" turn where the engine could keep its output off the page. Verified locally with the same course and model before sim, which made the missing return value in `run_agent_lesson` visible on the first run rather than after a deploy.

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

## Plan of Work

The delivered host loop runs additional turns of the same lesson within one
request while the previous outcome is `end` and has taught content. It stops
when a turn waits, finishes, errors, or ends without teaching more. The engine
suppresses repeated prior-turn text and output after `finish` on host-initiated
continue turns; revisiting a finished session runs no turn and writes no new rows.
This is not context transfer between lessons. Deterministic simulations and the
recorded live continuation runs cover that same-lesson boundary.

## Concrete Steps

For a continuation regression, reproduce a content-only lesson that needs
another turn inside the same request, then verify wait/finish and empty-turn
termination, repeat/after-finish suppression, and a finished-session revisit with
no new rows. Run `tests/service/learn/agent/engine/`,
`tests/service/learn/agent/test_lesson_entry_contracts.py`, and
`tests/service/learn/agent/test_run_agent.py` with `python -m pytest ... -q` from
`src/api`. Keep the request turn loop and engine suppression boundary separate
from unrelated cross-lesson memory work.

## Idempotence and Recovery

Resume from persisted lesson state; do not replay an answered interaction or duplicate a generated block to reconstruct context. Keep simulation fixtures deterministic and isolate live acceptance from offline verification.

## Interfaces and Dependencies

The vendored MarkdownFlow engine, learner-agent integration and persisted lesson context form the boundary. Offline tests use FunctionModel; live provider simulations require the separately configured environment.

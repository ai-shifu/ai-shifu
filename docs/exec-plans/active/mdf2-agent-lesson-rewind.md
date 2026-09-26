# MarkdownFlow 2.0: rewind a lesson to an earlier turn

> Lifecycle review, 2026-09-26: The backend/frontend change is merged; the planned browser refresh acceptance lacks a visible onRefresh trigger. Retain the acceptance gap explicitly.

## Purpose / Big Picture

A learner on a 1.0 lesson can go back: pick a different option on a question they already
answered (the browser asks "确定重新生成此内容？" and truncates everything after it), or
regenerate a piece of content. The request carries `reload_generated_block_bid` /
`reload_element_bid`, and the 1.0 run deactivates the superseded rows and continues from there.

On a course taught by the 2.0 engine the same request is routed back to **1.0**
(`runscript_v2._teaches_with_agent` returns False whenever a reload is present). 1.0 then
regenerates from rows the 2.0 engine wrote while the 2.0 session is left untouched, still waiting
on the question it last asked; the next ordinary request goes back to 2.0 and the page and the
engine disagree. Observed on sim, boundary lesson 6-1, 2026-09-24: re-answering the first
question produced 1.0 output and the 2.0 session stayed on the second question.

After this change a reload on a 2.0 lesson is handled by 2.0: the engine session is restored to
the point the learner chose, the superseded rows are deactivated the way 1.0 deactivates them, and
the turn is run again with the learner's new answer (or, for regenerated content, with the input
that turn originally had). A lesson whose turns predate this change cannot be rewound and says so
("use 重修"); it never falls back to 1.0.

## Progress

- [x] 2026-09-24 12:40 CST: Reproduced on sim and traced the routing (`_teaches_with_agent`).
- [x] 2026-09-24 13:00 CST: Chose the design (checkpoint per turn block); wrote this plan.
- [x] 2026-09-24 13:40 CST: Checkpoint written with every 2.0 turn (`block_content_conf`).
- [x] 2026-09-24 13:40 CST: Rewind planning and session restore (`agent/rewind.py`), unit tests.
- [x] 2026-09-24 13:50 CST: Wiring: reloads routed to 2.0, plan applied in `run_agent_lesson`,
  rows retired at persist; rollback of each layer turns its tests red.
- [x] 2026-09-24 13:50 CST: i18n message for a lesson that cannot be rewound (five locales).
- [x] 2026-09-24 14:00 CST: Browser verification on sim, boundary lesson 6-1: re-answering the
  first question ("后端" → "数据") continued with data-direction options; after a page reload the
  history showed only the new branch; the session held `Learner chose: 数据` and the new question
  pending; the superseded blocks had status 0. A lesson from before checkpoints (6-3) showed the
  "use 重修" message and nothing changed server-side.
- [ ] Content regenerate (`onRefresh`) has no visible trigger in the reading UI today; covered by
  tests only.

## Surprises & Discoveries

- When a reload is refused, the browser has already truncated the page locally; a page reload
  restores it. Only lessons whose turns predate checkpoints can be refused, so this ages out.

- 2.0 turn blocks all have `position = 0`, so 1.0's `position >=` filter is meaningless for them;
  ordering by `id` within the progress record is what identifies "later" blocks.
- The frontend sends the *block* bid in both reload fields for an interaction re-answer
  (`reload_element_bid: sourceBlockBid`), while 1.0 treats `reload_element_bid` as an element bid
  first. Resolution here does the same: element row first, block bid otherwise.

## Decision Log

- Checkpoints live in the turn block's `block_content_conf` (a Text column 2.0 has always written
  as `""`), not in the session document: they are per turn, host-owned (they name blocks, which
  the engine knows nothing about), and retired together with the block they describe. The
  session's `schema_version` does not change, so no stored session becomes unreadable.
- A checkpoint is the state *before* the turn: message count, session memory, pending questions,
  collected answers, turn counter, finished flag, plus the learner values the turn was run with.
  Messages are append-only, so a count is enough to restore them; no copy of the history is kept.
- Re-answering a question asked in block B restores the checkpoint of the **next** turn block
  after B (the turn that received the old answer, which began with exactly that question pending)
  and runs it with the new values. Regenerating content in block B restores B's own checkpoint and
  replays B's recorded values. `_turn_input` rebuilds the same turn kind from the restored session.
- Rows are deactivated from the target block onwards (status 0), follow-up (ask/answer) blocks
  excepted, as 1.0 does; this is staged inside the turn's own persist transaction, so it commits
  with the restored session or not at all.
- A rewind does **not** reopen a lesson already completed (revised after review): reopening only
  that record would leave its chapter completed and the next lesson started, ahead of a lesson
  that says it is unfinished. The outline follows the same rule (`apply_outline_progression`
  never reopens a finished lesson), and progression stays idempotent if the lesson finishes again.
- A reload on an allowlisted lesson whose script is gone (`LessonNotTeachable`) is refused rather
  than sent to 1.0, which cannot take the 2.0 session back.
- Profile (user-scope) memory written after the target is not undone; 1.0 does not undo it either.
- Preview has no blocks to rewind; a reload in preview is refused the same way as a legacy turn.

## Outcomes & Retrospective

(To be filled in when the work is complete.)

## Context and Orientation

- `src/api/flaskr/service/learn/runscript_v2.py` — `_teaches_with_agent` decides the engine per
  request; `run_script_inner` / `context_v2.MdflowContextV2.reload` is the 1.0 reload.
- `src/api/flaskr/service/learn/agent/lesson_entry.py` — `agent_lesson_events`, the 2.0 entry.
- `src/api/flaskr/service/learn/agent/run_agent.py` — `run_agent_lesson`, `_load_or_start`,
  `_turn_input`, `_stream_turn`, `_persist` (the turn's single write transaction).
- `src/api/flaskr/service/learn/agent/lesson_record.py` — turn blocks (`stage_turn_block`,
  `record_turn_content`), progress records.
- `src/api/flaskr/service/learn/agent/engine/session.py` — `Session.to_dict` / `from_dict`.
- Frontend (unchanged): `src/web/src/app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx`
  sends `input` + `reload_*` for a re-answer and `input: ''` + `reload_*` for `onRefresh`.

## Plan of Work

1. `agent/rewind.py` (new): `checkpoint_of(session)`, `restore(session, checkpoint)`,
   `plan_rewind(...) -> RewindPlan` (anchor → target block, checkpoint, replay values, blocks to
   retire; raises `RewindUnavailable`), `stage_rewind(...)` (deactivate rows).
2. `lesson_record.record_turn_content` also writes the turn's checkpoint and values.
3. `run_agent`: capture the pre-turn checkpoint once the session is loaded (and restored); apply a
   rewind plan in `_load_or_start`; stage the retirement and record status in `_persist`.
4. `lesson_entry.agent_lesson_events` accepts the reload identifiers, plans the rewind before the
   turn starts, and raises `server.learn.agentRewindUnavailable` when it cannot.
5. `runscript_v2._teaches_with_agent` routes reloads to 2.0 (follow-up questions stay on 1.0).
6. i18n: `server.learn.agentRewindUnavailable` in every locale.

## Concrete Steps

    cd src/api && python -m pytest tests/service/learn -q
    lefthook run pre-commit --all-files

Then push the branch to sim (after merging the latest main) and verify in the browser.

## Validation and Acceptance

- Re-answering an earlier question on a 2.0 lesson continues the lesson from that question with
  the new answer; the 2.0 session's history ends at that question plus the new answer; later
  rows are gone from history.
- Regenerating a content element re-runs that turn with its original input.
- A lesson whose turns carry no checkpoint answers a reload with the "use 重修" message and changes
  nothing; no reload on an allowlisted course reaches 1.0 (except follow-up questions).
- Each behaviour has a test that fails with the change reverted.

## Idempotence and Recovery

A rewind changes nothing until the turn's persist transaction commits. A turn that fails before it
leaves the session and rows as they were; the browser's local truncation is undone by a reload.
Turns written before this change simply have no checkpoint; nothing needs migrating.

## Interfaces and Dependencies

- `block_content_conf` of 2.0 turn blocks becomes a JSON document
  `{"agent_turn": {"version": 1, "checkpoint": {...}, "values": [...]}}`. 1.0 never reads this
  column for content-type blocks it did not write.
- New i18n key `server.learn.agentRewindUnavailable`.
- No schema migration.

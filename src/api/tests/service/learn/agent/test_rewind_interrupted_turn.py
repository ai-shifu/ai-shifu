"""Check whether an answer can still be changed after the turn that received it was cut off.

Each test drives real 2.0 turns end to end -- the real engine on a scripted model, the real
turn block lifecycle (`_open_turn`, `record_turn_content`, `retire_unused_block`) and the real
session store -- then plans the answer edit the browser sends for the question before the
interrupted turn (`rewind.plan_rewind(..., answering=True)` anchored on the question's block).

The question is whether an interruption can leave a live turn block without its checkpoint
record, which `plan_turn_rewind` refuses with `RewindUnavailableError`.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import rewind, run_agent, session_store
from flaskr.service.learn.agent.models import LearnAgentSession
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from markdownflow.engine import ContentDelta, Engine
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from pydantic_ai.messages import ModelMessage

SCRIPT = "# Lesson\n\nAsk which way the learner goes, then teach about it."


def _spec(question: str, *options: str) -> str:
    return json.dumps(
        {
            "type": "single",
            "prompt": question,
            "options": [{"display": o, "value": o} for o in options],
            "variable": question.split(maxsplit=1)[0].lower(),
        }
    )


def _answers_seen(messages: list[ModelMessage]) -> list[str]:
    """Tool results the model was given: where a learner's answers reach it."""
    return [
        str(part.content)
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolReturnPart) and part.tool_name == "interact"
    ]


class _Memory:
    def as_variables(self) -> dict:
        return {}


@pytest.fixture
def lesson(app: object, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    key = uuid.uuid4().hex
    monkeypatch.setattr(run_agent, "load_memory", lambda *_a, **_k: _Memory())
    monkeypatch.setattr(
        run_agent, "course_memory_deletion_state", lambda *_a, **_k: ({}, frozenset())
    )
    yield SimpleNamespace(app=app, user=key, course=key, outline=key)
    with app.app_context(), unit_of_work():
        LearnGeneratedElement.query.filter_by(user_bid=key).delete()
        LearnGeneratedBlock.query.filter_by(user_bid=key).delete()
        LearnProgressRecord.query.filter_by(user_bid=key).delete()
        LearnAgentSession.query.filter_by(user_bid=key).delete()


def _drive(make_events: object, **_kwargs: object) -> Iterator[object]:
    """Run the engine to completion on this thread, standing in for the bridge."""

    async def collect() -> list:
        return [event async for event in make_events()]

    return iter(asyncio.run(collect()))


def _turn(
    lesson: SimpleNamespace,
    model: object,
    *,
    user_input: str | None = None,
    plan: rewind.RewindPlan | None = None,
    iter_turn: object = _drive,
) -> Iterator[object]:
    return run_agent.run_agent_lesson(
        lesson.app,
        engine=Engine(FunctionModel(stream_function=model), render="none"),
        script=SCRIPT,
        user_bid=lesson.user,
        shifu_bid=lesson.course,
        outline_bid=lesson.outline,
        user_input=user_input,
        rewind=plan,
        iter_turn=iter_turn,
    )


def _blocks(lesson: SimpleNamespace) -> list[LearnGeneratedBlock]:
    with lesson.app.app_context():
        return (
            LearnGeneratedBlock.query.filter_by(user_bid=lesson.user)
            .order_by(LearnGeneratedBlock.id.asc())
            .all()
        )


def _stored(lesson: SimpleNamespace) -> object:
    return session_store.load_agent_session(lesson.app, lesson.user, lesson.outline)


def _plan_answer_edit(lesson: SimpleNamespace, question_block: str) -> object:
    with lesson.app.app_context():
        return rewind.plan_rewind(
            user_bid=lesson.user,
            outline_bid=lesson.outline,
            anchor=question_block,
            answering=True,
        )


class _Script:
    """A scripted model: turn 1 asks q1; `answered` decides what the answer turn does."""

    def __init__(self, answered: object) -> None:
        self.calls = 0
        self.answered = answered
        self.seen: list[list[str]] = []

    async def __call__(
        self, messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        self.calls += 1
        self.seen.append(_answers_seen(messages))
        if self.calls == 1:
            yield "Welcome.\n"
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="q1",
                    json_args=_spec("Way?", "Left", "Right"),
                )
            }
            return
        async for chunk in self.answered(self.calls):
            yield chunk


async def _teach(_call: int) -> AsyncIterator[str]:
    yield "Thanks, let us go on.\n"


def _ask_question(lesson: SimpleNamespace, model: _Script) -> str:
    """Run turn 1 (asks q1) and return its block, which the browser anchors an answer edit on."""
    list(_turn(lesson, model))
    (block,) = _blocks(lesson)
    assert rewind.read_turn_record(block) is not None
    assert [p.tool_call_id for p in _stored(lesson).pending] == ["q1"]
    return block.generated_block_bid


def _content(events: list) -> str:
    return "".join(
        str(e.content)
        for e in events
        if getattr(e, "type", None) == GeneratedType.CONTENT
    )


# --- variant A: provider error after output started ----------------------------------------


def test_provider_error_after_output_keeps_a_recorded_block_and_the_answer_edit_works(
    lesson: SimpleNamespace,
) -> None:
    """The engine turns a provider failure into ErrorEvent, so the host still saves the turn."""

    async def fail_after_text(call: int) -> AsyncIterator[str]:
        if call == 2:
            yield "You went left, so\n"
            message = "provider dropped the stream"
            raise RuntimeError(message)
        yield "You went right.\n"

    model = _Script(fail_after_text)
    question_block = _ask_question(lesson, model)

    events = list(_turn(lesson, model, user_input="Left"))
    outcome_text = _content(events)
    assert "You went left" in outcome_text

    _, interrupted = _blocks(lesson)
    assert (interrupted.status, interrupted.deleted) == (1, 0)
    assert interrupted.generated_content.startswith("You went left")
    record = rewind.read_turn_record(interrupted)
    assert record is not None
    assert record["values"] == ["Left"]
    stored = _stored(lesson)
    assert stored.interrupted is True
    assert stored.pending == []

    plan = _plan_answer_edit(lesson, question_block)
    assert plan is not None
    assert plan.retired_block_bids == [interrupted.generated_block_bid]
    assert plan.checkpoint["pending"][0]["tool_call_id"] == "q1"

    list(_turn(lesson, model, user_input="Right", plan=plan))
    assert model.seen[-1][-1].endswith("Right")
    assert [b.status for b in _blocks(lesson)] == [1, 0, 1]


# --- variant B: learner disconnects mid-stream (real bridge, engine cancelled) ------------


def test_disconnect_mid_stream_retires_the_block_and_the_edit_answers_q1_afresh(
    lesson: SimpleNamespace,
) -> None:
    from flaskr.api.markdownflow import iter_turn as bridge_iter_turn

    async def hang_after_text(call: int) -> AsyncIterator[str]:
        if call == 2:
            yield "You went left, so\n"
            await asyncio.sleep(30)  # the learner closes the page while this waits
        yield "You went right.\n"

    model = _Script(hang_after_text)
    question_block = _ask_question(lesson, model)

    stream = _turn(lesson, model, user_input="Left", iter_turn=bridge_iter_turn)
    for event in stream:
        if event.type == GeneratedType.CONTENT:
            break
    stream.close()

    _, interrupted = _blocks(lesson)
    assert (interrupted.status, interrupted.deleted) == (0, 1)
    assert interrupted.generated_content == ""
    assert interrupted.block_content_conf == ""
    stored = _stored(lesson)
    assert [p.tool_call_id for p in stored.pending] == ["q1"]
    assert stored.interrupted is False

    # Nothing to take back: q1 is still pending, so the edit is simply an answer.
    assert _plan_answer_edit(lesson, question_block) is None
    list(_turn(lesson, model, user_input="Right"))
    assert model.seen[-1][-1].endswith("Right")
    assert _stored(lesson).pending == []


# --- variant C: an exception escapes the engine/bridge after output -----------------------


def test_exception_escaping_the_bridge_retires_the_block_and_keeps_q1_pending(
    lesson: SimpleNamespace,
) -> None:
    model = _Script(_teach)
    question_block = _ask_question(lesson, model)

    def explode_after_first_delta(make_events: object, **kwargs: object) -> object:
        for event in _drive(make_events, **kwargs):
            yield event
            if isinstance(event, ContentDelta) and event.text:
                message = "bridge re-raised a producer failure"
                raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="bridge re-raised"):
        list(
            _turn(lesson, model, user_input="Left", iter_turn=explode_after_first_delta)
        )

    _, interrupted = _blocks(lesson)
    assert (interrupted.status, interrupted.deleted) == (0, 1)
    assert rewind.read_turn_record(interrupted) is None
    assert [p.tool_call_id for p in _stored(lesson).pending] == ["q1"]
    assert _plan_answer_edit(lesson, question_block) is None


# --- variant D: the cleanup never lands (DB failure in retire, or the worker is killed) ---


def test_an_unretired_interrupted_block_does_not_block_later_answer_edits(
    lesson: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted turn whose cleanup never ran stays live, empty and without a record.

    `_retire_block` swallows its own failure, and a killed worker (OOM, rollout, gunicorn
    timeout) never runs it. No saved session included that turn, so rewind planning skips it:
    the edit answers q1 afresh, and once a retry has answered q1 the edit goes back to the
    retry and retires the abandoned block with it.
    """
    model = _Script(_teach)
    question_block = _ask_question(lesson, model)

    def broken_cleanup(**_kwargs: object) -> None:
        message = "database unavailable during cleanup"
        raise RuntimeError(message)

    monkeypatch.setattr(run_agent, "retire_unused_block", broken_cleanup)

    def explode_after_first_delta(make_events: object, **kwargs: object) -> object:
        for event in _drive(make_events, **kwargs):
            yield event
            if isinstance(event, ContentDelta) and event.text:
                message = "turn interrupted"
                raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="turn interrupted"):
        list(
            _turn(lesson, model, user_input="Left", iter_turn=explode_after_first_delta)
        )
    monkeypatch.undo()
    monkeypatch.setattr(run_agent, "load_memory", lambda *_a, **_k: _Memory())
    monkeypatch.setattr(
        run_agent, "course_memory_deletion_state", lambda *_a, **_k: ({}, frozenset())
    )

    _, orphan = _blocks(lesson)
    assert (orphan.status, orphan.deleted) == (1, 0)
    assert orphan.generated_content == ""
    assert orphan.block_content_conf == ""
    assert [p.tool_call_id for p in _stored(lesson).pending] == ["q1"]

    # Nothing was saved after the question, so there is nothing to take back: q1 is answered now.
    assert _plan_answer_edit(lesson, question_block) is None

    # The learner retries; the retry answers q1 and records a valid checkpoint.
    list(_turn(lesson, model, user_input="Left"))
    _, orphan, retry = _blocks(lesson)
    assert (
        rewind.read_turn_record(retry)["checkpoint"]["pending"][0]["tool_call_id"]
        == "q1"
    )
    plan = _plan_answer_edit(lesson, question_block)
    assert plan is not None
    assert plan.checkpoint["pending"][0]["tool_call_id"] == "q1"
    assert plan.retired_block_bids == [
        retry.generated_block_bid,
        orphan.generated_block_bid,
    ]


# --- variant E: interrupted right after an empty-text turn was saved ------------------------


def test_a_saved_question_only_turn_survives_a_disconnect_and_can_be_taken_back(
    lesson: SimpleNamespace,
) -> None:
    """A turn that answers q1 by asking q2 straight away teaches no prose.

    Its block is saved with a record but `generated_content == ""`. A disconnect (or adapter
    failure) at the BREAK yielded after that save reaches `retire_unused_block`. The record shows
    the turn was saved, so the block stays; an answer edit on q1 goes back to it instead of
    sending the new value to q2.
    """

    async def ask_q2_without_prose(call: int) -> AsyncIterator[object]:
        if call == 2:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="q2",
                    json_args=_spec("Next?", "Right", "Wrong"),
                )
            }
            return
        yield "Noted.\n"

    model = _Script(ask_q2_without_prose)
    question_block = _ask_question(lesson, model)

    stream = _turn(lesson, model, user_input="Left")
    seen_controls = False
    for event in stream:
        if event.type == GeneratedType.INTERACTION:
            seen_controls = True
        elif seen_controls and event.type == GeneratedType.BREAK:
            break  # the BREAK translated from TurnDone, yielded after `_persist`
    stream.close()

    _, saved = _blocks(lesson)
    assert rewind.read_turn_record(saved) is not None
    assert saved.generated_content == ""
    assert (saved.status, saved.deleted) == (1, 0)
    assert [p.tool_call_id for p in _stored(lesson).pending] == ["q2"]

    plan = _plan_answer_edit(lesson, question_block)
    assert plan is not None
    # The edit restores the turn that received q1's answer, so the new value answers q1.
    assert plan.checkpoint["pending"][0]["tool_call_id"] == "q1"
    assert plan.retired_block_bids == [saved.generated_block_bid]

"""Require an explicit feedback branch before supported answer prose is visible."""

import json
from collections.abc import AsyncIterator, Callable

import pytest
from flaskr.service.learn.agent.engine import (
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
)
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from .test_direction_feedback import (
    DISPLAY,
    RULE,
    SCRIPT,
    WRONG,
    _call,
    _collect,
    _direction,
    _text,
)


def _review(phase: str = "accepted", **updates: object) -> dict:
    return {
        "answer_id": "original",
        "phase": phase,
        "submission_quote": WRONG,
        "rule_quote": RULE if phase == "authored_help" else None,
        "reason": "The actual correction history permits this branch.",
        **updates,
    }


def _engine(stream: Callable[[list[ModelMessage], AgentInfo], AsyncIterator]) -> Engine:
    return Engine(
        FunctionModel(stream_function=stream),
        memory_recall=True,
        exercise_statistics=True,
        teaching_history_compaction=True,
        request_limit=2,
        feedback_contract=True,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("interact", {"type": "text", "prompt": "Try again", "placeholder": "Answer"}),
        ("finish", {"summary": "premature"}),
        ("remember", {"key": "unseen", "value": "must not write"}),
        ("recall", {}),
        ("read_exercise_history", {}),
        ("read_teaching", {"reference": "missing"}),
        ("calculate_exercise_statistics", {"questions": [{"question": "fake"}]}),
        ("", {}),
    ],
)
async def test_omitting_phase_cannot_release_worked_prose_or_side_effects(
    name: str, args: dict
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Unreviewed worked answer must never become teaching."
            if name:
                yield {
                    0: DeltaToolCall(
                        name=name, json_args=json.dumps(args), tool_call_id="bad"
                    )
                }
        else:
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == DISPLAY
    assert calls == 3  # One rejected response, one correction; no planning request.
    assert session.pending[0].tool_call_id == "correction"
    assert not session.finished
    assert session.memory == session.user_memory == {}
    raw = ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    assert "Unreviewed worked answer" not in raw
    assert "correct the whole" in raw or "feedback branch" in raw
    from flaskr.service.learn.agent.gateway_model import map_messages

    assert all(
        message.get("content") or message.get("tool_calls")
        for message in map_messages(session.messages)
        if message["role"] == "assistant"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["accepted", "clarification", "authored_help"])
@pytest.mark.parametrize("reload", [False, True])
async def test_declared_ordinary_branches_keep_authored_behavior_without_planning(
    phase: str, reload: bool
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        assert (
            "review"
            in next(
                t for t in info.function_tools if t.name == "interact"
            ).parameters_json_schema["properties"]
        )
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        else:
            yield "Authored ordinary feedback."
            yield _call(
                {
                    "type": "single" if phase == "accepted" else "text",
                    "prompt": "",
                    "options": [{"display": "Next", "value": "Next"}]
                    if phase == "accepted"
                    else [],
                    "placeholder": None if phase == "accepted" else "Answer",
                    "review": _review(phase),
                },
                "next",
            )

    engine = _engine(stream)
    engine.limits.request_limit = 1
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Authored ordinary feedback."
    assert calls == 2
    assert session.pending[0].tool_call_id == "next"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "review",
    [
        _review(answer_id="invented"),
        _review(submission_quote="authored sample mistake"),
        _review("authored_help", rule_quote="invented rule"),
        _review("authored_help", rule_quote=None),
        _review(reason=" "),
    ],
)
async def test_invalid_phase_provenance_retries_before_any_body(review: dict) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Invalid phase prose."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "review": review,
                },
                "bad",
            )
        else:
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == DISPLAY
    assert (
        "Invalid phase prose"
        not in ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    )


@pytest.mark.anyio
async def test_lookup_before_feedback_and_paginated_report_inherit_declared_phase() -> (
    None
):
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield {
                0: DeltaToolCall(name="recall", json_args="{}", tool_call_id="lookup")
            }
        elif calls in (3, 4):
            yield "Report part."
            args = {"review": _review()} if calls == 3 else {}
            yield {
                0: DeltaToolCall(
                    name="read_exercise_history",
                    json_args=json.dumps(args),
                    tool_call_id=f"page-{calls}",
                )
            }
        else:
            yield "Report end."
            yield _call(
                {
                    "type": "single",
                    "prompt": "",
                    "options": [{"display": "Next", "value": "Next"}],
                },
                "next",
            )

    engine = _engine(stream)
    engine.limits.request_limit = 4
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Report part.Report part.Report end."
    assert calls == 5
    assert session.pending[0].tool_call_id == "next"


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_unreviewed_provider_failure_keeps_original_answer_for_recovery(
    reload: bool,
) -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Unreviewed partial reasoning."
            message = "provider interrupted before declaring feedback"
            raise RuntimeError(message)
        else:
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )

    engine = _engine(stream)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    events = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    ]
    assert _text(events) == ""
    assert any(isinstance(e, ErrorEvent) for e in events)
    assert session.answers["original"] == "Learner wrote: " + WRONG
    assert ModelMessagesTypeAdapter.dump_json(session.messages) == before
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(engine.run_turn(session, ContinueTurn()))
    assert _text(events) == DISPLAY
    assert session.pending[0].tool_call_id == "correction"


@pytest.mark.anyio
async def test_unsupported_text_anchor_keeps_ordinary_stream_without_review() -> None:
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        else:
            yield "Ordinary unsupported feedback."
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Follow-up"}, "next"
            )

    engine = _engine(stream)
    session = await engine.new_session(
        "Teach an open conversation without a uniquely authored input."
    )
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == "Ordinary unsupported feedback."
    assert calls == 2

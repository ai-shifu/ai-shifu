"""Exercise real 2.0 writes before constructing anchored follow-up history."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import bridge, lesson_entry
from flaskr.service.learn.follow_up_context import load_follow_up_history
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.learn_funcs import reset_learn_record
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE
from flaskr.service.shifu.models import PublishedOutlineItem
from flaskr.service.user.repository import create_user_entity
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from flask import Flask
    from flaskr.service.metering.api import UsageContext
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.fixture
def agent_classroom(app: Flask, monkeypatch: pytest.MonkeyPatch) -> Callable:
    """Replace only external model/trace and thread transport; persist real host turns."""
    identity = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        create_user_entity(user_bid=identity, identify=identity, nickname="Learner")
        db.session.add(
            PublishedOutlineItem(
                shifu_bid=identity, outline_item_bid=identity, deleted=0
            )
        )
    calls = 0
    contexts: list[UsageContext] = []

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        assert contexts
        assert contexts[-1].progress_record_bid
        calls += 1
        yield f"Visible teaching {calls}.\n"
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"question-{calls}",
                json_args=json.dumps({"type": "text", "prompt": f"Question {calls}?"}),
            )
        }

    class OfflineGateway(FunctionModel):
        def set_usage_context(self, context: UsageContext) -> None:
            """Keep host binding observable while replacing external provider calls."""
            contexts.append(context)

    gateway = OfflineGateway(stream_function=model)
    monkeypatch.setattr(lesson_entry, "GatewayModel", lambda *_a, **_k: gateway)
    monkeypatch.setattr(
        lesson_entry,
        "_resolve",
        lambda *_a, **_k: (
            "Teach arithmetic and ask several questions. Do not finish before all questions.",
            "",
            LLMSettings(model="test-model", temperature=0.0),
        ),
    )
    monkeypatch.setattr(lesson_entry, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(
        lesson_entry, "create_trace_with_root_span", lambda **_k: (Mock(), Mock())
    )
    monkeypatch.setattr(lesson_entry, "finalize_langfuse_trace", lambda **_k: None)

    def drive(make_events: Callable, **_kwargs: object) -> Iterator:
        async def collect() -> list:
            return [event async for event in make_events()]

        return iter(asyncio.run(collect()))

    monkeypatch.setattr(bridge, "iter_turn", drive)

    def run(answer: str | None = None, **reload: str) -> LearnGeneratedElement:
        with app.app_context():
            events = list(
                lesson_entry.agent_lesson_events(
                    app,
                    user_bid=identity,
                    shifu_bid=identity,
                    outline_bid=identity,
                    user_input=answer,
                    **reload,
                )
            )
            contents = [
                event for event in events if event.type == GeneratedType.CONTENT
            ]
            assert contents, "The real engine must teach before its next question"
            block = LearnGeneratedBlock.query.filter_by(
                generated_block_bid=contents[-1].generated_block_bid,
            ).one()
            assert block.type == BLOCK_TYPE_MDCONTENT_VALUE
            assert contexts[-1].progress_record_bid == block.progress_record_bid
            assert contexts[-1].generated_block_bid == block.generated_block_bid
            assert "agent_turn" in block.block_content_conf
            with unit_of_work():
                anchor = LearnGeneratedElement(
                    element_bid=uuid.uuid4().hex,
                    generated_block_bid=block.generated_block_bid,
                    progress_record_bid=block.progress_record_bid,
                    user_bid=identity,
                    shifu_bid=identity,
                    outline_item_bid=identity,
                    event_type="element",
                    element_type="text",
                    content_text=str(contents[-1].content),
                    status=1,
                )
                db.session.add(anchor)
            db.session.refresh(anchor)
            db.session.expunge(anchor)
            return anchor

    return run


def _history(anchor: LearnGeneratedElement, limit: int = 10) -> list[dict[str, str]]:
    return load_follow_up_history(
        progress_record_bid=anchor.progress_record_bid,
        anchor_element_bid=anchor.element_bid,
        max_history_messages=limit,
    )


@pytest.mark.parametrize(
    "lifecycle", ["original", "regenerate", "replace-answer", "reset"]
)
def test_real_agent_answers_follow_current_anchor_lifecycle(
    app: Flask,
    agent_classroom: Callable,
    lifecycle: str,
) -> None:
    """Actual stored turn inputs survive regeneration, change with answers and isolate resets."""
    first = agent_classroom()
    agent_classroom("4")
    third = agent_classroom("6")
    with app.app_context():
        assert [m["content"] for m in _history(third) if m["role"] == "user"] == [
            "4",
            "6",
        ]
        if lifecycle == "regenerate":
            current = agent_classroom(
                reload_generated_block_bid=third.generated_block_bid
            )
            expected = ["4", "6"]
        elif lifecycle == "replace-answer":
            current = agent_classroom(
                "5", reload_generated_block_bid=first.generated_block_bid
            )
            expected = ["5"]
        elif lifecycle == "reset":
            reset_learn_record(
                app, third.shifu_bid, third.outline_item_bid, third.user_bid
            )
            current = agent_classroom()
            assert current.progress_record_bid != third.progress_record_bid
            expected = []
        else:
            current, expected = third, ["4", "6"]
        messages = _history(current)
        assert [m["content"] for m in messages if m["role"] == "user"] == expected
        assert messages[-1] == {"role": "assistant", "content": current.content_text}
        assert "checkpoint" not in json.dumps(messages)
        assert _history(current, 0) == [messages[-1]]
        if expected:
            assert _history(current, 1) == [
                {"role": "user", "content": expected[-1]},
                messages[-1],
            ]
        assert (
            LearnGeneratedBlock.query.filter_by(
                user_bid=third.user_bid,
                type=BLOCK_TYPE_MDCONTENT_VALUE,
            ).count()
            >= 3
        )


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not JSON",
        "[]",
        '{"agent_turn": {"version": 99, "checkpoint": {}, "values": ["private"]}}',
        '{"agent_turn": {"version": 1, "values": ["private"]}}',
        '{"agent_turn": {"version": 1, "checkpoint": {}, "values": "private"}}',
        '{"agent_turn": {"version": 1, "checkpoint": {}, "values": ["private", 1]}}',
    ],
)
def test_unknown_turn_records_cannot_supply_learner_history(raw: str) -> None:
    """Unrecognized configuration and malformed values never become learner text."""
    from types import SimpleNamespace

    from flaskr.service.learn.agent.rewind import read_turn_learner_values

    assert read_turn_learner_values(SimpleNamespace(block_content_conf=raw)) == []


def test_turn_input_projection_keeps_exact_values_and_no_checkpoint() -> None:
    """Only submitted text leaves the versioned codec; all private fields stay inside it."""
    from types import SimpleNamespace

    from flaskr.service.learn.agent.rewind import read_turn_learner_values, turn_record

    values = ["Exact multiline\n<tool> text", "é" * 2001, "  keep spaces  ", " \n"]
    record = turn_record(
        {"memory": {"private": "SECRET"}, "pending": ["PRIVATE TOOL"]}, values
    )
    assert (
        read_turn_learner_values(SimpleNamespace(block_content_conf=record))
        == values[:-1]
    )

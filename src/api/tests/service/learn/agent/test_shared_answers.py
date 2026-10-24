"""Refuse retired shared writes while preserving pending answers and source values."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import SimpleNamespace

    from flaskr.service.learn.agent.engine import Session
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import (
    Engine,
    MemoryUpdated,
    MessageTurn,
)
from flaskr.service.learn.agent.engine.interaction import InteractionSpec
from flaskr.service.learn.agent.engine.session import PendingInteraction
from flaskr.service.profile.models import VariableValue
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive
from tests.service.profile.test_shared_answers import context, shared, source_value

__all__ = ["context", "shared"]


@pytest.mark.parametrize("tool", ["remember", "interact"])
def test_tools_refuse_shared_aliases_even_with_explicit_learner_request(
    shared: SimpleNamespace, tool: str
) -> None:
    c = shared
    judge = AsyncMock(return_value=True)

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        if len(messages) > 2:
            yield "Use an ordinary local variable."
        else:
            args = (
                {
                    "key": c.share,
                    "value": "Updated",
                    "scope": "user",
                    "request": "Please remember Updated.",
                }
                if tool == "remember"
                else {"type": "text", "prompt": "Your goal?", "variable": c.share}
            )
            yield {
                0: DeltaToolCall(
                    name=tool, tool_call_id="retired", json_args=json.dumps(args)
                )
            }

    async def check() -> None:
        engine = Engine(
            FunctionModel(stream_function=model),
            memory_admission=True,
            memory_readonly_prefixes=("course:", "share:"),
            memory_request_check=judge,
        )
        session = await engine.new_session(c.script)
        events = [
            e
            async for e in engine.run_turn(
                session, MessageTurn(text="Please remember Updated.")
            )
        ]
        assert not any(isinstance(e, MemoryUpdated) for e in events)
        assert c.share not in session.all_memory()
        assert not session.pending

    asyncio.run(check())
    judge.assert_not_awaited()
    assert source_value(c) == "Source goal"


def test_saved_shared_question_keeps_answer_without_writing_either_course(
    shared: SimpleNamespace,
) -> None:
    c = shared

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield "Continue with the current course."

    engine = Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        memory_readonly_prefixes=("course:", "share:"),
    )

    async def prepare() -> Session:
        session = await engine.new_session(c.script)
        args = {"type": "text", "prompt": "Your goal?", "variable": c.share}
        session.messages = [
            ModelRequest(parts=[UserPromptPart("Legacy start")]),
            ModelResponse(
                parts=[ToolCallPart("interact", args, "old-shared-question")]
            ),
        ]
        session.pending = [
            PendingInteraction("old-shared-question", InteractionSpec(**args))
        ]
        return session

    stored = asyncio.run(prepare())
    session_store.save_agent_session(
        c.app, stored, user_bid=c.user, shifu_bid=c.target, outline_item_bid=c.outline
    )
    answer = "Full revised answer " + "é" * 3000
    list(
        run_agent.run_agent_lesson(
            c.app,
            engine=engine,
            user_bid=c.user,
            shifu_bid=c.target,
            outline_bid=c.outline,
            script=c.script,
            user_input=answer,
            iter_turn=_drive,
        )
    )
    result = session_store.load_agent_session(c.app, c.user, c.outline)
    assert answer in str(result.messages)
    assert c.share not in result.all_memory()
    assert source_value(c) == "Source goal"
    assert (
        VariableValue.query.filter_by(user_bid=c.user, shifu_bid=c.target).count() == 0
    )

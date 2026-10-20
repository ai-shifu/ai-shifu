"""Verify the canvas contract reaches real teaching requests in both modes."""

from collections.abc import AsyncIterator
from typing import Literal

import pytest
from flaskr.service.learn.agent.engine import Engine
from flaskr.service.learn.agent.engine.engine import Prompts
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("listen_mode", [False, True])
async def test_sandbox_request_preserves_cross_mode_canvas_contract(
    listen_mode: bool,
) -> None:
    seen: list[str] = []

    async def spy(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        seen.append(messages[0].instructions or "")
        yield "A brief explanation."

    engine = Engine(FunctionModel(stream_function=spy))
    session = await engine.new_session(
        "Show a short cover and explain it.", listen_mode=listen_mode
    )
    events = [event async for event in engine.run_turn(session)]

    assert not any(event.type == "error" for event in events)
    assert len(seen) == 1
    instructions = seen[0]
    visual_rules = Prompts.default().html_display.strip()
    assert instructions.count(visual_rules) == 1
    assert "The root is the canvas itself" in instructions
    assert "reserves the natural content height" in instructions
    assert "Keep the minimum on the root only" in instructions
    assert "Do not lock the root to an aspect ratio" in instructions
    assert "Compact reading content must remain compact" in instructions
    assert "min-height:100vh" in instructions
    assert "Do not give the root a fixed `height:100vh`" in instructions
    assert "non-negative offsets" in instructions
    assert ("complete low-density screen" in instructions) is listen_mode
    assert "at least a simple title or key-point card" not in instructions


@pytest.mark.parametrize("render", ["generic", "none"])
async def test_non_sandbox_requests_do_not_receive_host_sizing_contract(
    render: Literal["generic", "none"],
) -> None:
    seen: list[str] = []

    async def spy(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        seen.append(messages[0].instructions or "")
        yield "A brief explanation."

    engine = Engine(FunctionModel(stream_function=spy), render=render)
    session = await engine.new_session("Explain the topic.", listen_mode=True)
    events = [event async for event in engine.run_turn(session)]

    assert not any(event.type == "error" for event in events)
    assert len(seen) == 1
    assert "Reading mode relaxes the root" not in seen[0]
    assert ("plain renderer" in seen[0]) is (render == "generic")

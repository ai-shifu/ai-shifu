"""Use actual computed SDK output with the unchanged all-mode element formatter."""

from collections.abc import AsyncIterator

import pytest
from flask import Flask
from flaskr.service.learn.agent.engine import Engine, Session
from flaskr.service.learn.learn_dtos import ElementType
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tests.service.learn.agent import test_element_format as element_fixture
from tests.service.learn.agent import test_run_agent as host_fixture
from tests.service.learn.agent.engine.test_computed_example import _loop
from tests.service.learn.agent.engine.test_direction_feedback import _call
from tests.service.learn.agent.test_element_format import (
    _adapt_and_reload,
    _reference_shape,
    _shape,
)

calls = element_fixture.calls
format_environment = element_fixture.format_environment


@pytest.mark.parametrize("mode", ["read", "classroom", "listen"])
def test_computed_artifact_retains_existing_elements_and_stored_history(
    format_environment: Flask, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run native calculation through host classification, adapter, SQLite and reload."""
    requests = 0

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Supply no model-authored state table for the host to trust."""
        nonlocal requests
        requests += 1
        assert info.function_tools
        if requests == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
            return
        yield "General narration.\n\n"
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Answer",
                "computed_example": _loop(),
            },
            "numeric",
        )

    engine = Engine(
        FunctionModel(stream_function=stream), computed_examples=True, request_limit=1
    )
    import asyncio

    from flaskr.service.learn.agent import run_agent

    script = "Explain a counter.\n?[...Answer]\n"

    async def prepare() -> Session:
        """Prepare the actual first turn without any host or provider writes."""
        session = await engine.new_session(script, listen_mode=mode == "listen")
        _events = [event async for event in engine.run_turn(session)]
        return session

    session = asyncio.run(prepare())
    monkeypatch.setattr(host_fixture, "SCRIPT", script)
    monkeypatch.setattr(run_agent, "load_agent_session", lambda *_a, **_k: session)
    events = host_fixture._run(
        engine,
        app=format_environment,
        listen=mode == "listen",
        user_input="Show two iterations.",
    )
    streamed, history = _adapt_and_reload(format_environment, events)
    from flaskr.service.learn.agent.engine.computed_example import (
        ComputedExample,
        render_example,
    )

    expected_text = (
        "General narration.\n\n"
        + "\n\n"
        + render_example(ComputedExample.model_validate(_loop()))
    )
    assert requests == 2
    expected = _reference_shape(expected_text)
    assert _shape(streamed)[:-1] == expected
    assert _shape(history) == _shape(streamed)
    assert history[-1].element_type == ElementType.INTERACTION
    assert {element.element_type for element in history} >= {
        ElementType.CODE,
        ElementType.TABLES,
    }
    table = next(
        element for element in history if element.element_type == ElementType.TABLES
    )
    assert "| 5 | 101 | 102 | 1 | 3 |" in table.content
    for element in history:
        if element.element_type == ElementType.TEXT:
            assert bool(element.audio_url) is (mode == "listen")
        elif element.element_type in (ElementType.CODE, ElementType.TABLES):
            assert element.is_renderable
            assert not element.is_speakable

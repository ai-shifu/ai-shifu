"""Resume sessions saved while teaching history compaction and read_teaching existed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from flaskr.api.llm.markdownflow_model import map_messages, map_tools
from markdownflow.engine import (
    ContentDelta,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MessageTurn,
    Session,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "legacy_teaching_history_session.json"
)
_ORIGINAL = "Exact original teaching about sampling bias. " * 120


def _read_teaching_parts(messages: list[ModelMessage]) -> list[str]:
    return [
        type(part).__name__
        for message in messages
        for part in message.parts
        if isinstance(part, ToolCallPart | ToolReturnPart)
        and part.tool_name == "read_teaching"
    ]


@pytest.mark.anyio
async def test_saved_teaching_summaries_and_read_teaching_history_still_resume() -> (
    None
):
    """Read real output of the removed feature and keep teaching from it.

    The fixture was produced by the engine at the parent of the commit that removed
    teaching history compaction, with `teaching_history_compaction=True` and a stub
    summarizer. A long first teaching turn was excerpted two turns later, the model
    called `read_teaching` together with a deferred `interact`, and the session was
    saved while that question was pending. Run IDs, timestamps and the system
    instructions were fixed for an inspectable fixture.
    """
    payload = _FIXTURE.read_text()
    state = json.loads(payload)
    assert state["teaching_summaries"]
    session = Session.loads(payload)
    # The derived summary cache is dropped; the original history replays unchanged.
    assert "teaching_summaries" not in session.to_dict()
    assert session.to_dict()["messages"] == state["messages"]
    assert _read_teaching_parts(session.messages) == ["ToolCallPart", "ToolReturnPart"]
    assert [item.tool_call_id for item in session.pending] == ["legacy-ask"]
    seen: list[list[ModelMessage]] = []

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        seen.append(messages)
        tools = {tool.name for tool in info.function_tools}
        assert "read_teaching" not in tools
        assert {"interact", "finish"} <= tools
        # The complete original teaching is sent, never an excerpt marker.
        texts = [
            part.content
            for message in messages
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, TextPart)
        ]
        assert _ORIGINAL in texts
        assert not any("teaching_excerpt" in text for text in texts)
        assert "teaching_summary" not in (info.instructions or "")
        # The gateway payload still pairs the historical call with its result.
        payload = map_messages(messages)
        calls = [
            call["id"]
            for item in payload
            if item["role"] == "assistant"
            for call in item.get("tool_calls") or []
            if call["function"]["name"] == "read_teaching"
        ]
        results = [
            item["tool_call_id"]
            for item in payload
            if item["role"] == "tool" and item["tool_call_id"] == "legacy-read"
        ]
        assert calls == results == ["legacy-read"]
        assert "read_teaching" not in json.dumps(
            map_tools(ModelRequestParameters(function_tools=list(info.function_tools)))
        )
        if len(seen) == 1:
            yield "The earlier example was about sampling bias."
            return
        yield "Here is the next step."
        yield {
            0: DeltaToolCall(
                name="finish",
                json_args='{"summary":"Lesson complete."}',
                tool_call_id="legacy-finish",
            )
        }

    engine = Engine(FunctionModel(stream_function=stream))
    answered = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(id="legacy-ask", text="The first one")
        )
    ]
    assert not [event for event in answered if isinstance(event, ErrorEvent)]
    assert "sampling bias" in "".join(
        event.text for event in answered if isinstance(event, ContentDelta)
    )
    assert not session.pending
    assert [
        part.content
        for message in session.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "interact"
    ] == ["Learner wrote: The first one"]

    session = Session.loads(session.dumps())
    followed = [
        event async for event in engine.run_turn(session, MessageTurn(text="Go on."))
    ]
    assert not [event for event in followed if isinstance(event, ErrorEvent)]
    assert len(seen) == 2
    assert session.finished
    assert _read_teaching_parts(session.messages) == ["ToolCallPart", "ToolReturnPart"]
    assert "teaching_summaries" not in json.loads(session.dumps())

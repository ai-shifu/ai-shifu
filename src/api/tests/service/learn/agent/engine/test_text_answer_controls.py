"""Keep natural-language text questions usable across a saved-session round trip."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionRequest,
    InteractionResponseTurn,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent.legacy_protocol import (
    render_interaction,
    unrenderable_reason,
)
from markdown_flow import InteractionParser
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("blank", [[""], [" \t", "\n"]])
async def test_saved_natural_question_rejects_blank_values_before_accepting_text(
    blank: list[str],
) -> None:
    calls: list[str] = []
    answer = "  My assistant helps support staff.  "

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        returns = [
            part
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == "interact"
        ]
        calls.append("answer" if returns else "question")
        if returns:
            assert returns[-1].content == "Learner chose: " + answer
            yield "Thanks for describing your project."
        else:
            yield "Describe who your assistant helps."
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="project-question",
                    json_args=json.dumps(
                        {
                            "type": "text",
                            "prompt": "Who will use your assistant?",
                            "variable": "project",
                        }
                    ),
                )
            }

    engine = Engine(
        FunctionModel(stream_function=model), interaction_check=unrenderable_reason
    )
    session = await engine.new_session("Ask the learner to describe their project.")
    _ = [event async for event in engine.run_turn(session)]
    session = Session.loads(session.dumps())
    history = session.messages.copy()
    events = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=blank)
        )
    ]
    request = next(event for event in events if isinstance(event, InteractionRequest))
    assert any(isinstance(event, ErrorEvent) for event in events)
    assert request.asked_before
    assert request.id == "project-question"
    assert (
        InteractionParser().parse(render_interaction(request.spec))["question"].strip()
    )
    assert session.messages == history
    assert session.answers == {}
    assert session.memory == {}
    assert session.answer_hashes == {}
    assert calls == ["question"]
    session = Session.loads(session.dumps())
    events = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=[answer])
        )
    ]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert isinstance(events[-1], TurnDone)
    assert not session.pending
    assert session.memory == {"project": answer}
    assert calls == ["question", "answer"]

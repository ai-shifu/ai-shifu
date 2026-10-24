"""A completed lesson cannot accept further model-authored memory changes."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio


def _call(name: str, **args: str) -> DeltaToolCall:
    """Use stable call IDs so acknowledgements can be checked after a real tool run."""
    return DeltaToolCall(name=name, tool_call_id=name, json_args=json.dumps(args))


@pytest.mark.parametrize("scope", ["session", "user"])
@pytest.mark.parametrize("key", ["pace", "new_note"])
@pytest.mark.parametrize("ordering", ["same-response", "later-response"])
async def test_model_notes_after_finish_cannot_change_memory(
    scope: str, key: str, ordering: str
) -> None:
    """Reject both overwrites and new notes after finish, including batched tool calls."""
    calls = 0
    acknowledgements = {}

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Simulate a model ignoring finish and attempting one extra memory write."""
        nonlocal calls
        calls += 1
        for message in messages:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    if isinstance(part, ToolReturnPart):
                        acknowledgements[part.tool_name] = part.content
        note = _call("remember", key=key, value="late overwrite", scope=scope)
        if calls == 1:
            yield {
                0: _call("finish", summary="done"),
                **({1: note} if ordering == "same-response" else {}),
            }
        elif calls == 2 and ordering == "later-response":
            yield {0: note}
        else:
            yield ""

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Teach the last step.")
    session.memory = {"pace": "original"}
    session.user_memory = {"pace": "original"}
    events = [event async for event in engine.run_turn(session)]
    assert not [event for event in events if isinstance(event, ErrorEvent)]
    assert not [event for event in events if isinstance(event, MemoryUpdated)]
    assert session.memory == session.user_memory == {"pace": "original"}
    assert events[-1].reason == "finished"
    assert session.finished is True
    assert acknowledgements["remember"].startswith("The lesson is over:")


@pytest.mark.parametrize("scope", ["session", "user"])
async def test_note_before_finish_in_the_same_response_is_retained(scope: str) -> None:
    """The last legitimate note remains writable before the terminal call."""
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Write a valid note immediately before finishing the lesson."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                0: _call("remember", key="pace", value="slow", scope=scope),
                1: _call("finish", summary="done"),
            }
        else:
            yield ""

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Remember the pace, then finish.")
    events = [event async for event in engine.run_turn(session)]
    target = session.user_memory if scope == "user" else session.memory
    assert target == {"pace": "slow"}
    writes = [event for event in events if isinstance(event, MemoryUpdated)]
    assert [(event.scope, event.key, event.value) for event in writes] == [
        (scope, "pace", "slow")
    ]
    assert events[-1].reason == "finished"


async def test_last_pending_named_answer_is_retained_after_finish() -> None:
    """Finish does not discard an earlier deferred question's legitimate answer."""
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Ask the final named question before finish, then consume its answer."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                0: _call("interact", type="text", prompt="Your goal?", variable="goal"),
                1: _call("finish", summary="done"),
            }
        else:
            yield ""

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask for %{{goal}} as the final step.")
    first = [event async for event in engine.run_turn(session)]
    assert first[-1].reason == "interaction"
    session = Session.loads(session.dumps())
    second = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=["Build a project"])
        )
    ]
    writes = [event for event in second if isinstance(event, MemoryUpdated)]
    assert [(event.key, event.value, event.source) for event in writes] == [
        ("goal", "Build a project", "interaction")
    ]
    assert session.memory["goal"] == "Build a project"
    assert second[-1].reason == "finished"
    assert session.finished is True

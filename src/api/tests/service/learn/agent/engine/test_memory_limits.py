"""Bound model-authored notes without discarding existing memory or learner answers."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
    TurnDone,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio


async def _remember(
    scope: str, key: str, value: str, existing: dict[str, str] | None = None
) -> tuple[Session, list, list[str]]:
    """Run the real tool and inspect the model's acknowledgement and emitted writes."""
    returns = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        last = messages[-1]
        result = (
            next((p for p in last.parts if isinstance(p, ToolReturnPart)), None)
            if isinstance(last, ModelRequest)
            else None
        )
        if result is None:
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id="note",
                    json_args=json.dumps({"scope": scope, "key": key, "value": value}),
                )
            }
        else:
            returns.append(str(result.content))
            yield "Continue the lesson."

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Teach the next example.")
    target = session.user_memory if scope == "user" else session.memory
    target.update(existing or {})
    events = [event async for event in engine.run_turn(session)]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "end"
    return session, events, returns


@pytest.mark.parametrize("scope", ["session", "user"])
@pytest.mark.parametrize(
    ("key", "value"),
    [("", "note"), ("  \n", "note"), ("k" * 256, "note"), ("pace", "x" * 2001)],
    ids=["empty-key", "blank-key", "long-key", "long-value"],
)
async def test_rejected_note_neither_mutates_memory_nor_emits_an_update(
    scope: str, key: str, value: str
) -> None:
    """Oversized or unnamed notes cannot overwrite a valid learner fact."""
    session, events, returns = await _remember(scope, key, value, {"pace": "slow"})
    target = session.user_memory if scope == "user" else session.memory
    assert target == {"pace": "slow"}
    assert not any(isinstance(event, MemoryUpdated) for event in events)
    assert len(returns) == 1
    assert returns[0].startswith("Not remembered:")


@pytest.mark.parametrize("scope", ["session", "user"])
async def test_note_at_exact_length_limits_is_preserved_verbatim(scope: str) -> None:
    """Limits count Unicode characters and never silently truncate the learner's words."""
    key, value = "k" * 255, "é" * 2000
    session, events, returns = await _remember(scope, key, value)
    target = session.user_memory if scope == "user" else session.memory
    assert target == {key: value}
    writes = [event for event in events if isinstance(event, MemoryUpdated)]
    assert len(writes) == 1
    assert (writes[0].scope, writes[0].key, writes[0].value) == (scope, key, value)
    assert returns == [f"remembered {key} ({scope})"]


@pytest.mark.parametrize("scope", ["session", "user"])
@pytest.mark.parametrize("count", [100, 101])
async def test_full_or_legacy_oversized_memory_rejects_only_new_keys(
    scope: str, count: int
) -> None:
    """A loaded snapshot may exceed the cap; it stays intact while growth stops."""
    existing = {f"note_{i}": "old" for i in range(count)}
    session, events, returns = await _remember(scope, "new_note", "new", existing)
    target = session.user_memory if scope == "user" else session.memory
    assert target == existing
    assert not any(isinstance(event, MemoryUpdated) for event in events)
    assert returns[0].startswith("Not remembered:")
    restored = Session.from_dict(session.to_dict())
    assert (restored.user_memory if scope == "user" else restored.memory) == existing


@pytest.mark.parametrize("scope", ["session", "user"])
async def test_the_hundredth_note_can_be_added(scope: str) -> None:
    """Growth is allowed up to and including the cap."""
    existing = {f"note_{i}": "old" for i in range(99)}
    session, events, _returns = await _remember(scope, "new_note", "new", existing)
    target = session.user_memory if scope == "user" else session.memory
    assert target == {**existing, "new_note": "new"}
    assert len([event for event in events if isinstance(event, MemoryUpdated)]) == 1


@pytest.mark.parametrize("scope", ["session", "user"])
@pytest.mark.parametrize("count", [100, 101])
async def test_full_memory_can_update_an_existing_key(scope: str, count: int) -> None:
    """The cap must not leave an outdated preference permanently stuck."""
    existing = {f"note_{i}": "old" for i in range(count)}
    session, events, _returns = await _remember(scope, "note_0", "new", existing)
    target = session.user_memory if scope == "user" else session.memory
    assert target == {**existing, "note_0": "new"}
    assert len([event for event in events if isinstance(event, MemoryUpdated)]) == 1


async def test_named_learner_answer_is_not_subject_to_model_note_limits() -> None:
    """Long answers remain exact even when the session already contains 100 keys."""

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="answer",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "Your goal?", "variable": "goal"}
                    ),
                )
            }
        else:
            yield "Thank you."

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask for the learner's goal.")
    session.memory.update({f"note_{i}": "old" for i in range(100)})
    _first = [event async for event in engine.run_turn(session)]
    answer = "é" * 2001
    events = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=[answer])
        )
    ]
    assert session.memory["goal"] == answer
    assert len(session.memory) == 101
    writes = [event for event in events if isinstance(event, MemoryUpdated)]
    assert len(writes) == 1
    assert writes[0].source == "interaction"
    assert writes[0].value == answer

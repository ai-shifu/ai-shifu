"""Model notes cannot keep expanding the memory supplied to future lessons."""

import json
from collections.abc import AsyncIterator
from typing import Any

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
LIMIT = 32_768


def _size(memory: dict[str, Any]) -> int:
    """Measure the documented pretty-printed JSON character budget."""
    return len(json.dumps(memory, ensure_ascii=False, indent=2))


async def _notes(
    scope: str, existing: dict[str, Any], notes: list[tuple[str, str]]
) -> tuple[Session, list, list[str]]:
    """Run a batch of actual model tool calls and collect their acknowledgements."""
    returns = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Attempt each note once, then continue teaching after acceptance or refusal."""
        last = messages[-1]
        acknowledgements = (
            [part for part in last.parts if isinstance(part, ToolReturnPart)]
            if isinstance(last, ModelRequest)
            else []
        )
        if acknowledgements:
            returns.extend(str(part.content) for part in acknowledgements)
            yield "Continue the lesson."
        else:
            yield {
                index: DeltaToolCall(
                    name="remember",
                    tool_call_id=f"note-{index}",
                    json_args=json.dumps({"scope": scope, "key": key, "value": value}),
                )
                for index, (key, value) in enumerate(notes)
            }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Teach the next example.")
    target = session.user_memory if scope == "user" else session.memory
    target.update(existing)
    events = [event async for event in engine.run_turn(session)]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert events[-1].reason == "end"
    return session, events, returns


@pytest.mark.parametrize("scope", ["session", "user"])
@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.parametrize("overwrite", [False, True])
async def test_exact_json_budget_accepts_but_one_more_character_refuses(
    scope: str, extra: int, overwrite: bool
) -> None:
    """Count Unicode characters plus JSON keys and punctuation without trimming old answers."""
    existing = {"answer": "é" * (LIMIT - _size({"answer": "", "pace": "x"}))}
    if overwrite:
        existing["pace"] = ""
    session, events, returns = await _notes(
        scope, existing, [("pace", "x" * (1 + extra))]
    )
    target = session.user_memory if scope == "user" else session.memory
    writes = [event for event in events if isinstance(event, MemoryUpdated)]
    assert target == (existing if extra else {**existing, "pace": "x"})
    assert len(writes) == (0 if extra else 1)
    assert returns[0].startswith("Not remembered:" if extra else "remembered ")
    assert target["answer"] == existing["answer"]
    if not extra:
        assert _size(target) == LIMIT


@pytest.mark.parametrize("scope", ["session", "user"])
@pytest.mark.parametrize("value", ["xy", "xyz", "xyzz"])
async def test_legacy_oversized_memory_can_shrink_or_change_without_growth(
    scope: str, value: str
) -> None:
    """Large existing answers survive while only non-growing note updates are accepted."""
    existing = {"answer": ["é" * LIMIT, {"detail": "kept"}], "pace": "old"}
    session, events, returns = await _notes(scope, existing, [("pace", value)])
    target = session.user_memory if scope == "user" else session.memory
    accepted = len(value) <= 3
    assert target == ({**existing, "pace": value} if accepted else existing)
    assert len([event for event in events if isinstance(event, MemoryUpdated)]) == int(
        accepted
    )
    assert returns[0].startswith("remembered " if accepted else "Not remembered:")
    restored = Session.loads(session.dumps())
    assert (restored.user_memory if scope == "user" else restored.memory) == target


@pytest.mark.parametrize("scope", ["session", "user"])
async def test_individually_valid_batched_notes_cannot_accumulate_past_budget(
    scope: str,
) -> None:
    """Later calls in the same response see earlier writes and cannot bypass the total cap."""
    notes = [(f"note_{index}", "é" * 2000) for index in range(20)]
    session, events, returns = await _notes(scope, {}, notes)
    target = session.user_memory if scope == "user" else session.memory
    assert 0 < len(target) < len(notes)
    assert _size(target) <= LIMIT
    assert len([event for event in events if isinstance(event, MemoryUpdated)]) == len(
        target
    )
    assert sum(result.startswith("Not remembered:") for result in returns) == len(
        notes
    ) - len(target)
    assert all(value == "é" * 2000 for value in target.values())


@pytest.mark.parametrize("scope", ["session", "user"])
async def test_json_escaping_counts_toward_budget(scope: str) -> None:
    """Control characters expand in JSON, even though each note meets its value limit."""
    session, _events, returns = await _notes(
        scope, {}, [(f"note_{index}", "\x00" * 2000) for index in range(4)]
    )
    target = session.user_memory if scope == "user" else session.memory
    assert len(target) == 2
    assert _size(target) <= LIMIT
    assert sum(result.startswith("Not remembered:") for result in returns) == 2


async def test_budget_is_independent_between_scopes() -> None:
    """Full user memory must not consume a session note's allowance."""
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Write once to each scope, then finish the lesson."""
        nonlocal calls
        calls += 1
        if calls > 1:
            yield ""
            return
        yield {
            index: DeltaToolCall(
                name="remember",
                tool_call_id=scope,
                json_args=json.dumps({"scope": scope, "key": "pace", "value": "slow"}),
            )
            for index, scope in enumerate(("user", "session"))
        }
        yield {2: DeltaToolCall(name="finish", tool_call_id="finish", json_args="{}")}

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Teach the next example.")
    session.user_memory = {"answer": "x" * LIMIT}
    events = [event async for event in engine.run_turn(session)]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert session.finished is True
    assert session.memory == {"pace": "slow"}
    assert session.user_memory == {"answer": "x" * LIMIT}
    writes = [event for event in events if isinstance(event, MemoryUpdated)]
    assert [(event.scope, event.key) for event in writes] == [("session", "pace")]


async def test_named_answer_can_exceed_budget_and_remains_exact() -> None:
    """The aggregate model-note limit does not constrain the learner's actual answer."""

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Ask for a named answer, then continue after receiving it."""
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="goal",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "Your goal?", "variable": "goal"}
                    ),
                )
            }
        else:
            yield "Thank you."

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask for %{{goal}}.")
    _first = [event async for event in engine.run_turn(session)]
    answer = "é" * (LIMIT + 1)
    events = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=[answer])
        )
    ]
    assert session.memory["goal"] == answer
    writes = [event for event in events if isinstance(event, MemoryUpdated)]
    assert [(event.source, event.value) for event in writes] == [
        ("interaction", answer)
    ]

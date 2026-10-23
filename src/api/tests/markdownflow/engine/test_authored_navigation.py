"""Verify navigation policy delivery and deferred controls, not model grading."""

import json
from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import (
    ContentDelta,
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionRequest,
    InteractionResponseTurn,
    MessageTurn,
    Session,
)
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("prelude", [None, "incorrect", "clarification submission"])
async def test_authored_navigation_waits_for_click_after_answer_and_reload(
    reload: bool, prelude: str | None
) -> None:
    """Check policy delivery and pending controls, including non-selection messages."""
    calls = 0
    correcting = prelude is not None

    async def model(
        _messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Emit controlled teaching to isolate SDK turn and pause mechanics."""
        nonlocal calls
        calls += 1
        if calls == 1 or (calls == 2 and correcting):
            yield "First question." if calls == 1 else "Help for this question."
            spec = {"type": "text", "prompt": "First question", "placeholder": "Answer"}
        elif calls == (3 if correcting else 2):
            policy = info.instructions or ""
            assert "one-option navigation" in policy
            assert "A correct answer or a side question is not that selection" in policy
            assert "without asking to continue again" in policy
            assert "three separate learner-facing turns" in policy
            interaction_tool = next(
                t for t in info.function_tools if t.name == "interact"
            )
            assert (
                "Do not replace an unanswered navigation"
                in interaction_tool.description
            )
            yield "Correct; here is the required explanation."
            spec = {
                "type": "single",
                "prompt": "",
                "options": [{"display": "Next question", "value": "next"}],
            }
        else:
            assert calls == (4 if correcting else 3)
            yield "Second question."
            spec = {
                "type": "text",
                "prompt": "Second question",
                "placeholder": "Answer two",
            }
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(spec),
                tool_call_id=f"step-{calls}",
            )
        }

    engine = Engine(FunctionModel(stream_function=model), pauses_from_notation=True)
    script = "First question.\n?[...Answer]\nExplain the accepted answer.\n?[Next question//next]\nSecond question.\n?[...Answer two]"
    session = await engine.new_session(script)
    await _events(engine.run_turn(session))
    if correcting:
        await _events(
            engine.run_turn(
                session,
                InteractionResponseTurn(
                    id=session.pending[0].tool_call_id, text=prelude
                ),
            )
        )
    if reload:
        session = Session.loads(session.dumps())
    events = await _events(
        engine.run_turn(
            session,
            InteractionResponseTurn(id=session.pending[0].tool_call_id, text="correct"),
        )
    )
    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert "Second question" not in "".join(
        e.text for e in events if isinstance(e, ContentDelta)
    )
    interactions = [e for e in events if isinstance(e, InteractionRequest)]
    assert len(interactions) == 1
    assert session.pending[0].spec.type == "single"
    assert session.pending[0].spec.options[0].stored == "next"
    before = calls
    await _events(engine.run_turn(session, ContinueTurn()))
    assert calls == before
    if reload:
        session = Session.loads(session.dumps())
    pending = (session.pending[0].tool_call_id, session.pending[0].spec.model_dump())
    answers = dict(session.answers)
    side_question = await _events(
        engine.run_turn(session, MessageTurn(text="Why is that answer correct?"))
    )
    assert calls == before
    assert any(isinstance(event, ErrorEvent) for event in side_question)
    assert not any(isinstance(event, ContentDelta) for event in side_question)
    assert (
        session.pending[0].tool_call_id,
        session.pending[0].spec.model_dump(),
    ) == pending
    assert session.answers == answers
    events = await _events(
        engine.run_turn(
            session,
            InteractionResponseTurn(
                id=session.pending[0].tool_call_id, values=["next"]
            ),
        )
    )
    assert "Second question." in "".join(
        e.text for e in events if isinstance(e, ContentDelta)
    )
    assert session.pending[0].spec.type == "text"
    assert session.pending[0].spec.placeholder == "Answer two"


async def _events(events: AsyncIterator[object]) -> list[object]:
    """Collect one streamed SDK turn for assertions."""
    return [event async for event in events]

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
    MemoryUpdated,
    MessageTurn,
    Session,
)
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("prelude", [None, "incorrect", "clarification submission"])
@pytest.mark.parametrize(
    ("nav_prose", "nav_binding"),
    [
        ("Continue to practice.", ""),
        ("Ready to proceed?", None),
        ("Practice step", "Practice step"),
    ],
    ids=["navigation", "question-mark-navigation", "bound-navigation"],
)
@pytest.mark.parametrize(
    ("label", "value"),
    [("Next question", "next"), ("Begin practice", "begin_practice")],
)
async def test_authored_navigation_waits_for_click_after_answer_and_reload(
    reload: bool,
    prelude: str | None,
    nav_prose: str,
    nav_binding: str | None,
    label: str,
    value: str,
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
            if calls == 2:
                yield "Help for this question.\n\n"
            yield "First question?"
            spec = {
                "type": "text",
                "question": "First question?",
                "placeholder": "Answer",
            }
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
            yield "\n\n" + nav_prose
            spec = {
                "type": "single",
                "options": [{"display": label, "value": value}],
            }
            if nav_binding is not None:
                spec["question"] = nav_binding
        else:
            assert calls == (4 if correcting else 3)
            yield "Second question?"
            spec = {
                "type": "text",
                "question": "Second question?",
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
    binding = f"{{{{{nav_binding}}}}} " if nav_binding else ""
    script = f"First question?\n?[...Answer]\n{nav_prose}\n?[{binding}{label}//{value}]\nSecond question?\n?[...Answer two]\n?[{{{{practice_feedback}}}}...{value}]\n?[...{value}]"
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
    assert session.pending[0].spec.question == (nav_binding or "")
    assert session.pending[0].spec.options[0].stored == value
    before = calls
    await _events(engine.run_turn(session, ContinueTurn()))
    assert calls == before
    if reload:
        session = Session.loads(session.dumps())
    assert session.pending[0].spec.type == "single"
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
    memory = dict(session.memory)
    events = await _events(
        engine.run_turn(
            session,
            InteractionResponseTurn(id=session.pending[0].tool_call_id, values=[value]),
        )
    )
    assert "Second question?" in "".join(
        e.text for e in events if isinstance(e, ContentDelta)
    )
    assert session.pending[0].spec.type == "text"
    assert session.pending[0].spec.placeholder == "Answer two"
    assert session.memory == ({**memory, nav_binding: value} if nav_binding else memory)
    assert [
        (event.key, event.value) for event in events if isinstance(event, MemoryUpdated)
    ] == ([(nav_binding, value)] if nav_binding else [])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("preceding", "question"),
    [
        (None, "What color is the sky?"),
        ("{question}", "What color is the sky?"),
        ("**{question}**", "What color is the sky?"),
        ("[{question}](https://example.com)", "What color is the sky?"),
        ("{question}", "Choose the sky color."),
    ],
    ids=["bound", "plain", "bold", "link", "instruction"],
)
async def test_an_authored_single_choice_can_still_record_an_answer(
    preceding: str | None, question: str
) -> None:
    script = (
        f"?[{{{{{question}}}}} Blue]"
        if preceding is None
        else f"{preceding.format(question=question)}\n?[Blue]"
    )
    attempts = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            yield "Continue teaching."
            return
        yield question
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="color",
                json_args=json.dumps(
                    {
                        "type": "single",
                        "question": question,
                        "options": [{"display": "Blue"}],
                    }
                ),
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(script)
    first = await _events(engine.run_turn(session))
    (request,) = [event for event in first if isinstance(event, InteractionRequest)]
    assert request.spec.question == question
    second = await _events(
        engine.run_turn(session, InteractionResponseTurn(values=["Blue"]))
    )
    assert [
        (event.key, event.value) for event in second if isinstance(event, MemoryUpdated)
    ] == [(question, "Blue")]


async def _events(events: AsyncIterator[object]) -> list[object]:
    """Collect one streamed SDK turn for assertions."""
    return [event async for event in events]

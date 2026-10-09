"""A failed stream must retain the teaching the learner already received."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    ContentDelta,
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MessageTurn,
    Session,
    TurnDone,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, TextPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("resuming", [False, True])
@pytest.mark.parametrize("projected", [False, True])
async def test_failed_teaching_survives_reload_and_continues(
    resuming: bool, projected: bool
) -> None:
    """Keep partial teaching and paired answers without replacing original history."""
    attempts = 0
    received: list[list[ModelMessage]] = []
    partial = "The first step is to name your project. Then choose its audience."

    async def stream(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Fail once after emitting text, then inspect the retried request."""
        nonlocal attempts
        attempts += 1
        received.append(messages)
        if resuming and attempts == 1:
            yield "Which project?"
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args=json.dumps(
                        {
                            "type": "text",
                            "prompt": "Which project?",
                            "variable": "project",
                        }
                    ),
                    tool_call_id="project-question",
                )
            }
            return
        if attempts == (2 if resuming else 1):
            yield partial[:30]
            yield partial[30:]
            message = "injected stream failure"
            raise RuntimeError(message)
        yield "The next step is to choose one concrete outcome."

    engine = Engine(
        FunctionModel(stream_function=stream),
        render="none",
        turn_limit=1,
        memory_recall=projected,
        memory_context_limit=100 if projected else None,
        recall_history_compaction=projected,
        teaching_history_compaction=projected,
    )
    session = await engine.new_session("Teach the project steps. ?[%{{project}} ...]")
    if resuming:
        _ = [event async for event in engine.run_turn(session)]
    original = session.to_dict()["messages"]
    failed = [
        event
        async for event in engine.run_turn(
            session,
            InteractionResponseTurn(id="project-question", text="A lunch planner")
            if resuming
            else None,
        )
    ]
    assert (
        "".join(event.text for event in failed if isinstance(event, ContentDelta))
        == partial
    )
    assert any(isinstance(event, ErrorEvent) for event in failed)
    assert not any(isinstance(event, TurnDone) for event in failed)
    assert not session.finished
    assert session.interrupted

    session = Session.loads(session.dumps())
    assert session.to_dict()["messages"][: len(original)] == original
    assert partial in "".join(
        part.content
        for message in session.messages
        for part in message.parts
        if isinstance(part, TextPart)
    )
    assert not session.answers
    retried = [event async for event in engine.run_turn(session, ContinueTurn())]
    assert not any(isinstance(event, ErrorEvent) for event in retried)
    assert not session.interrupted
    assert "".join(
        event.text for event in retried if isinstance(event, ContentDelta)
    ) == ("The next step is to choose one concrete outcome.")
    assert partial in "".join(
        part.content
        for message in received[-1]
        for part in message.parts
        if isinstance(part, TextPart)
    )
    if resuming:
        returns = [
            part
            for message in received[-1]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
            and part.tool_call_id == "project-question"
        ]
        assert len(returns) == 1
        assert returns[0].content == "Learner wrote: A lunch planner"
        assert session.memory == {"project": "A lunch planner"}


@pytest.mark.parametrize("prior", ["new", "answer", "tool"])
async def test_repeating_interrupted_teaching_does_not_finish_the_lesson(
    prior: str,
) -> None:
    """A partial replay stays retryable across reloads until teaching makes progress."""
    calls = 0
    partial = (
        "First choose a single audience for your project. Describe their main task."
    )

    async def stream(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Repeat the failed text twice before delivering the next step."""
        nonlocal calls
        calls += 1
        if calls == 1 and prior != "new":
            yield "Opening question before the interrupted teaching."
            yield {
                0: DeltaToolCall(
                    name="interact" if prior == "answer" else "remember",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "Which project?"}
                        if prior == "answer"
                        else {"key": "project", "value": "planner"}
                    ),
                    tool_call_id="before-failure",
                )
            }
            return
        failed_at = 1 if prior == "new" else 2
        if calls <= failed_at + 2:
            yield partial
            if calls == failed_at:
                message = "injected failure"
                raise RuntimeError(message)
        else:
            yield "Now choose one outcome for that audience."

    engine = Engine(FunctionModel(stream_function=stream), render="none")
    session = await engine.new_session(
        "Teach audience selection, then outcome selection."
    )
    _ = [event async for event in engine.run_turn(session)]
    if prior == "answer":
        _ = [
            event
            async for event in engine.run_turn(
                session, InteractionResponseTurn(id="before-failure", text="A planner")
            )
        ]
    for _ in range(2):
        session = Session.loads(session.dumps())
        events = [event async for event in engine.run_turn(session, ContinueTurn())]
        assert not any(isinstance(event, ContentDelta) for event in events)
        assert [event.reason for event in events if isinstance(event, TurnDone)] == [
            "end"
        ]
        assert session.interrupted
        assert not session.finished
    events = [event async for event in engine.run_turn(session, ContinueTurn())]
    assert "".join(
        event.text for event in events if isinstance(event, ContentDelta)
    ) == ("Now choose one outcome for that audience.")
    assert not session.interrupted


@pytest.mark.parametrize("tool_state", ["partial", "completed", "finished"])
async def test_interrupted_tools_are_not_executed_again(tool_state: str) -> None:
    """Retain completed tool evidence and abandon a streamed but unexecuted call."""
    calls = 0
    partial = "The project serves learners who need a simple lunch planner."

    async def stream(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Fail during a call or after a completed tool's next model request."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield partial
            yield {
                0: DeltaToolCall(
                    name="finish" if tool_state == "finished" else "remember",
                    json_args=(
                        '{"key": "project", "value": "'
                        if tool_state == "partial"
                        else "{}"
                        if tool_state == "finished"
                        else json.dumps({"key": "project", "value": "lunch planner"})
                    ),
                    tool_call_id="interrupted-tool",
                )
            }
            if tool_state != "partial":
                return
        elif calls > 2 or tool_state == "partial":
            yield "The next step is to choose one outcome."
            return
        message = "injected failure during tool handling"
        raise RuntimeError(message)

    engine = Engine(FunctionModel(stream_function=stream), render="none")
    session = await engine.new_session("Teach the project steps.")
    failed = [event async for event in engine.run_turn(session)]
    session = Session.loads(session.dumps())
    assert partial in "".join(
        part.content
        for message in session.messages
        for part in message.parts
        if isinstance(part, TextPart)
    )
    assert session.memory == (
        {"project": "lunch planner"} if tool_state == "completed" else {}
    )
    assert not session.pending
    if tool_state == "finished":
        assert session.finished
        assert not session.interrupted
        assert [event.reason for event in failed if isinstance(event, TurnDone)] == [
            "finished"
        ]
        return
    assert any(isinstance(event, ErrorEvent) for event in failed)
    events = [event async for event in engine.run_turn(session, ContinueTurn())]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert "".join(
        event.text for event in events if isinstance(event, ContentDelta)
    ) == ("The next step is to choose one outcome.")
    assert session.memory == (
        {"project": "lunch planner"} if tool_state == "completed" else {}
    )
    returns = [
        part
        for message in session.messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_call_id == "interrupted-tool"
    ]
    assert len(returns) == 1
    assert returns[0].outcome == (
        "success" if tool_state == "completed" else "interrupted"
    )


async def test_failure_while_holding_a_repeat_keeps_the_previous_history() -> None:
    """Unshown repetition must not be mistaken for new partial teaching."""
    calls = 0
    partial = (
        "First choose a single audience for your project. Describe their main task."
    )

    async def stream(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        """Finish one turn, then fail while the engine holds a duplicate."""
        nonlocal calls
        calls += 1
        yield partial
        if calls > 1:
            message = "injected failure during held text"
            raise RuntimeError(message)

    engine = Engine(FunctionModel(stream_function=stream), render="none")
    session = await engine.new_session("Teach project planning.")
    _ = [event async for event in engine.run_turn(session)]
    original = session.to_dict()["messages"]
    failed = [event async for event in engine.run_turn(session, ContinueTurn())]
    assert any(isinstance(event, ErrorEvent) for event in failed)
    assert not any(isinstance(event, ContentDelta) for event in failed)
    assert session.to_dict()["messages"] == original
    assert not session.interrupted


@pytest.mark.parametrize("new_input", [False, True])
async def test_retry_retains_only_the_interrupted_turns_memory_request(
    new_input: bool,
) -> None:
    """An interrupted explicit request survives retry but cannot authorize a new input."""
    calls = 0
    checked: list[tuple[str, str, str]] = []
    request = "Please remember that I prefer short lessons."

    async def check(request_text: str, key: str, value: str) -> bool:
        """Accept only the exact learner request carried by the interrupted turn."""
        checked.append((request_text, key, value))
        return request_text == request

    async def stream(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Fail before writing memory, then attempt the pending request on retry."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield "First choose one audience for the project, then define their main task."
            message = "injected failure before remember"
            raise RuntimeError(message)
        if calls == 2:
            yield {
                0: DeltaToolCall(
                    name="remember",
                    json_args=json.dumps(
                        {"key": "pace", "value": "short", "request": request}
                    ),
                    tool_call_id="requested-memory",
                )
            }
            return
        yield "Next choose a measurable outcome."

    engine = Engine(
        FunctionModel(stream_function=stream),
        render="none",
        memory_admission=True,
        memory_request_check=check,
    )
    session = await engine.new_session("Teach project planning.")
    _ = [event async for event in engine.run_turn(session, MessageTurn(text=request))]
    session = Session.loads(session.dumps())
    assert session.request_inputs == [request]
    events = [
        event
        async for event in engine.run_turn(
            session,
            MessageTurn(text="Tell me the next step.") if new_input else ContinueTurn(),
        )
    ]
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert session.all_memory() == ({} if new_input else {"pace": "short"})
    assert checked == ([] if new_input else [(request, "pace", "short")])
    assert not session.request_inputs

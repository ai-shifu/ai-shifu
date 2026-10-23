"""Keep internal answer requirements out of public checking directions."""

from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
)
from markdownflow.engine.direction import DirectionFeedback
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .test_direction_feedback import (
    CRITERION,
    QUESTION,
    SCRIPT,
    WRONG,
    _call,
    _collect,
    _direction,
    _text,
)

PARTIAL = "Execution is automatic, without prior memory storage."
ACCEPTED = "Execution is automatic"


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_internal_diagnosis_cannot_disclose_missing_requirements(
    reload: bool,
) -> None:
    calls = 0
    plan = _direction()
    plan["accepted_quotes"] = [ACCEPTED]
    plan["focuses"][0]["submission_quote"] = "without prior memory storage"
    plan["focuses"][0]["observed_issue"] = CRITERION

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Answer",
                **({"direction": plan} if calls == 2 else {}),
            },
            "original" if calls == 1 else "correction",
        )

    engine = Engine(
        FunctionModel(stream_function=stream), request_limit=1, feedback_contract=True
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=PARTIAL))
    )
    shown = _text(events)
    assert CRITERION not in shown
    assert (
        shown == "> ✓ " + ACCEPTED + "\n\n> without prior memory storage\n\n" + QUESTION
    )
    original = next(
        part
        for message in session.messages
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_call_id == "correction"
    )
    assert (
        original.args_as_dict()["direction"]["focuses"][0]["observed_issue"]
        == CRITERION
    )
    assert session.pending[0].tool_call_id == "correction"
    assert calls == 2


@pytest.mark.parametrize("quotes", [[CRITERION], [" "], [ACCEPTED, ACCEPTED]])
def test_accepted_quotes_require_unique_actual_submission_evidence(
    quotes: list[str],
) -> None:
    plan = _direction()
    plan["accepted_quotes"] = quotes
    plan["focuses"][0]["submission_quote"] = None
    assert (
        DirectionFeedback.model_validate(plan).problem(SCRIPT, {"original": PARTIAL})
        is not None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("transport", ["text", "browser_values"])
async def test_same_excerpt_cannot_be_both_accepted_and_contradicted(
    reload: bool,
    transport: str,
) -> None:
    """Reject incompatible model annotations without grading the actual answer."""
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        plan = _direction()
        if calls == 2:
            plan["accepted_quotes"] = [WRONG]
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Answer",
                **({"direction": plan} if calls > 1 else {}),
            },
            "original" if calls == 1 else "conflict" if calls == 2 else "correction",
        )

    engine = Engine(
        FunctionModel(stream_function=stream), request_limit=2, feedback_contract=True
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    turn = (
        InteractionResponseTurn(values=[WRONG])
        if transport == "browser_values"
        else InteractionResponseTurn(text=WRONG)
    )
    events = await _collect(engine.run_turn(session, turn))
    assert "✓" not in _text(events)
    assert _text(events) == "> " + WRONG + "\n\n" + QUESTION
    assert session.pending[0].tool_call_id == "correction"
    assert calls == 3


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_new_direction_cannot_skip_an_authored_count_with_null(
    reload: bool,
) -> None:
    calls = 0
    plan = _direction()
    plan["aspect_limit"] = None

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Answer",
                **({"direction": plan} if calls == 2 else {}),
            },
            "original" if calls == 1 else "invalid-correction",
        )

    engine = Engine(
        FunctionModel(stream_function=stream), request_limit=1, feedback_contract=True
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = [
        e async for e in engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    ]
    assert not _text(events)
    assert any(isinstance(e, ErrorEvent) for e in events)
    assert not session.pending
    assert session.answers == {"original": "Learner wrote: " + WRONG}
    assert calls == 2

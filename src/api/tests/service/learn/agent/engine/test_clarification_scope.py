"""Check phase-scoped instructions without claiming factual model compliance."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import Engine, InteractionResponseTurn, Session
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelRequest
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .test_direction_feedback import _call, _collect


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("feedback_contract", [False, True])
async def test_clarification_keeps_authored_limits_without_correction_withholding(
    reload: bool, feedback_contract: bool
) -> None:
    """Deliver distinct phase guidance while retaining source, input and history."""
    preamble = "Answer knowledge questions briefly; do not advance the exercise.\n\n"
    section = (
        "## Question\nExplain a loop.\n?[...Explanation]\n\n"
        "### Acceptance\nA loop repeats while its condition holds.\n\n"
        "### Correction\nAsk one check; leave its reasoning to the learner.\n\n"
    )
    script = preamble + section + "?[Next]\n"
    question = "Could you briefly illustrate how a loop's counter changes?"
    calls = 0

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Explanation"}, "original"
            )
            return
        instructions = info.instructions or ""
        marker = '{"status":"authored_section"'
        reference = json.loads(instructions[instructions.index(marker) :])
        assert reference["text"] == preamble + section
        assert reference["ancestor_preambles"] == []
        notice = reference["notice"]
        assert "For checking-direction feedback only," in notice
        assert notice.index("For checking-direction feedback only,") < notice.index(
            "Leave permitted questions unanswered"
        )
        assert (
            "For clarification, answer the actual side question within authored "
            "brevity and disclosure rules" in notice
        )
        assert (
            "Do not apply correction-only withholding to permitted clarification"
            in notice
        )
        assert question in ModelMessagesTypeAdapter.dump_json(messages).decode()
        yield "A counter initialized to 2 can decrease once per iteration: 2, 1, 0."
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Explanation",
                **(
                    {
                        "review": {
                            "answer_id": "original",
                            "phase": "clarification",
                            "submission_quote": question,
                            "reason": "Briefly answer the side question and retain the exercise.",
                        }
                    }
                    if feedback_contract
                    else {}
                ),
            },
            "continued",
        )

    engine = Engine(
        FunctionModel(stream_function=stream),
        feedback_contract=feedback_contract,
        request_limit=1,
    )
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    memory = json.dumps([session.memory, session.user_memory], sort_keys=True)
    await _collect(engine.run_turn(session, InteractionResponseTurn(text=question)))
    assert calls == 2
    assert not session.finished
    assert session.script.script == script
    assert len(session.pending) == 1
    assert session.pending[0].spec.placeholder == "Explanation"
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert json.dumps([session.memory, session.user_memory], sort_keys=True) == memory
    assert not any(
        isinstance(message, ModelRequest)
        and "# Current authored feedback scope" in (message.instructions or "")
        for message in session.messages
    )

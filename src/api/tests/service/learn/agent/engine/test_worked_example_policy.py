"""Check policy delivery, not factual correctness of a controlled model response."""

from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    Engine,
    InteractionResponseTurn,
    Session,
)
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .test_direction_feedback import _call, _collect, _text


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("feedback_contract", [False, True])
async def test_example_check_reaches_clarification_without_rewriting_evidence(
    reload: bool, feedback_contract: bool
) -> None:
    """Deliver the same consistency boundary to initial and resumed SDK requests."""
    script = "Explain how a loop changes a counter.\n?[...Explanation]\n"
    question = "Could you show a small loop and trace its counter?"
    explanation = "Initialize the counter to 2 once, then decrement: 2, 1, 0."
    calls = 0

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Inspect real SDK instructions while returning a controlled response."""
        nonlocal calls
        calls += 1
        instructions = info.instructions or ""
        assert "# Worked example consistency" in instructions
        assert "instructions, not text to recite" in instructions
        assert "Give each full initial state" in instructions
        assert "Trace operations/jumps" in instructions
        assert "each loop iteration: reapply reads/resets" in instructions
        assert "only retained changes accumulate" in instructions
        assert "Check units, storage overlap" in instructions
        assert "requested behavior/termination" in instructions
        assert "Fix own errors before display, never source evidence" in instructions
        assert "uncertainty" in instructions
        assert "authored hint stage" in instructions
        assert "no extra verification calls/criteria" in instructions.lower()
        assert "Keep required tool and example calls" in instructions
        assert "Add no calls" not in instructions
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Explanation"},
                "original",
            )
            return
        assert question in ModelMessagesTypeAdapter.dump_json(messages).decode()
        yield explanation
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
                            "reason": "Answer the side question and retain the input.",
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
        request_limit=1,
        feedback_contract=feedback_contract,
    )
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    session.memory["prior_note"] = "Keep exactly."
    if reload:
        session = Session.loads(session.dumps())
    count = len(session.messages)
    original = ModelMessagesTypeAdapter.dump_json(session.messages)
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=question))
    )
    assert calls == 2
    assert _text(events) == explanation
    assert session.pending[0].tool_call_id == "continued"
    assert session.pending[0].spec.placeholder == "Explanation"
    assert not session.finished
    assert session.memory == {"prior_note": "Keep exactly."}
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == original

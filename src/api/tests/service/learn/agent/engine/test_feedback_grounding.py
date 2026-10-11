"""Check feedback source policy delivery, not real-model semantic compliance."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    ContentDelta,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
)
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("corrected", [False, True])
async def test_feedback_policy_keeps_author_examples_separate_from_submissions(
    reload: bool, corrected: bool
) -> None:
    """Verify original attempts and grounding guidance reach actual SDK requests."""
    calls = 0
    wrong = "A program can execute while being written, without prior storage."
    correct = (
        "Prepare program and data in memory, then fetch and execute automatically."
    )

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls > 1:
            policy = info.instructions or ""
            assert "Author-provided mistakes and sample diagnoses" in policy
            assert "actual submissions" in policy
            assert "a missing point is not proof" in policy
            assert "general example" in policy
            assert "If the original evidence is unavailable" in policy
            evidence = ModelMessagesTypeAdapter.dump_json(messages).decode()
            assert wrong in evidence
            assert (correct in evidence) == (calls == 3)
        yield "Question." if calls == 1 else "Feedback for the submitted attempt."
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(
                    {
                        "type": "text",
                        "prompt": "Explain execution",
                        "placeholder": "Answer",
                    }
                ),
                tool_call_id=f"attempt-{calls}",
            )
        }

    engine = Engine(FunctionModel(stream_function=model), pauses_from_notation=True)
    session = await engine.new_session(
        "Explain stored-program execution. Require preparation, memory and automatic execution. "
        "A possible mistake is confusing storage with saving a disk file. "
        "Give feedback, ask for a correction if needed, then explain the accepted answer.\n"
        "?[...Answer]"
    )
    await _events(engine.run_turn(session))
    for answer in [wrong, correct] if corrected else [wrong]:
        if reload:
            session = Session.loads(session.dumps())
        original = ModelMessagesTypeAdapter.dump_json(session.messages)
        count = len(session.messages)
        events = await _events(
            engine.run_turn(
                session,
                InteractionResponseTurn(
                    id=session.pending[0].tool_call_id, text=answer
                ),
            )
        )
        assert not any(isinstance(event, ErrorEvent) for event in events)
        assert any(isinstance(event, ContentDelta) for event in events)
        assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == original
        assert len(session.pending) == 1
    assert calls == (3 if corrected else 2)


async def _events(events: AsyncIterator[object]) -> list[object]:
    """Collect a streamed SDK turn while retaining every error event."""
    return [event async for event in events]

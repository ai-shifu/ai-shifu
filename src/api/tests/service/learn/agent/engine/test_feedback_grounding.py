"""Check feedback source policy delivery, not real-model semantic compliance."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    ContentDelta,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MessageTurn,
    Session,
)
from flaskr.service.learn.agent.engine.script import ScriptBundle
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
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
        """Inspect SDK evidence and return controlled content and an input control."""
        nonlocal calls
        calls += 1
        if calls > 1:
            policy = info.instructions or ""
            assert "Author-provided mistakes and sample diagnoses" in policy
            assert "actual submissions" in policy
            assert "a missing point is not proof" in policy
            assert "general example" in policy
            assert (
                "Quote the actual submitted mistake before naming a personal misconception"
                in policy
            )
            assert "cite the original submission" in next(
                t.description for t in info.function_tools if t.name == "interact"
            )
            assert "If the original evidence is unavailable" in policy
            assert "Do not infer a personal habit" in policy
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


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_final_review_receives_original_omissions_over_prior_generated_diagnosis(
    reload: bool,
) -> None:
    """Keep actual answers available when reviewing an earlier invented habit."""
    original = "Word length, speed, main memory capacity and disk capacity."
    session = Session(
        script=ScriptBundle(
            script="Review the learner's actual omissions and correction."
        ),
        messages=[
            ModelRequest(parts=[UserPromptPart("List the performance indicators.")]),
            ModelResponse(parts=[TextPart("Which indicators do you know?")]),
            ModelRequest(parts=[UserPromptPart(original)]),
            ModelResponse(
                parts=[TextPart("You only remember frequency, memory and disk.")]
            ),
            ModelRequest(
                parts=[
                    UserPromptPart(
                        "Add data path width, peripherals and system software."
                    )
                ]
            ),
            ModelResponse(
                parts=[TextPart("The corrected answer covers the required indicators.")]
            ),
        ],
    )
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Check final-review guidance without pretending to judge the model's prose."""
        policy = info.instructions or ""
        assert "Do not infer a personal habit" in policy
        assert "In final reports and study advice" in policy
        assert "Judge omissions by submitted meaning" in policy
        assert (
            "Quote the actual submitted mistake before naming a personal misconception"
            in policy
        )
        assert "not proof of independent reasoning or effort" in policy
        assert "not your earlier feedback" in policy
        assert original in ModelMessagesTypeAdapter.dump_json(messages).decode()
        yield "Your first answer omitted data path width, peripherals and system software."
        yield {
            0: DeltaToolCall(
                name="finish", json_args='{"summary":"Reviewed omissions."}'
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    events = await _events(
        engine.run_turn(session, MessageTurn(text="Review my learning."))
    )
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert session.finished
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before


async def _events(events: AsyncIterator[object]) -> list[object]:
    """Collect a streamed SDK turn while retaining every error event."""
    return [event async for event in events]


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_feedback_omissions_use_meaning_instead_of_missing_category_labels(
    reload: bool,
) -> None:
    """Deliver original covered concepts and the authored equivalent-coverage rule."""
    original = (
        "Cache reduces memory waiting; DMA overlaps I/O and CPU work to reduce idle time. "
        "Superscalar executes several instructions in a cycle."
    )
    session = Session(
        script=ScriptBundle(
            script=(
                "Require RISC, hardware threading, superscalar execution and balanced throughput. "
                "For balanced throughput, concrete memory-side and I/O-side methods with their "
                "bottleneck effects suffice; the category title is not required. "
                "Describe only genuinely missing concepts in feedback and review."
            )
        ),
        messages=[
            ModelRequest(
                parts=[
                    UserPromptPart(
                        "Explain processor performance techniques. For balanced throughput, "
                        "memory-side and I/O-side examples with their effects suffice; "
                        "the category title is not required."
                    )
                ]
            ),
            ModelResponse(parts=[TextPart("Give techniques and their effects.")]),
            ModelRequest(parts=[UserPromptPart(original)]),
            ModelResponse(
                parts=[TextPart("You omitted balanced throughput and superscalar.")]
            ),
        ],
    )
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Inspect instructions and retained evidence, without judging real-model prose."""
        policy = info.instructions or ""
        assert "Judge omissions by submitted meaning" in policy
        assert "missing category title does not establish missing knowledge" in policy
        assert "do not ask again for a point already supplied" in next(
            t.description for t in info.function_tools if t.name == "interact"
        )
        evidence = ModelMessagesTypeAdapter.dump_json(messages).decode()
        assert original in evidence
        assert "the category title is not required" in evidence
        yield "Your answer is missing RISC and hardware threading."
        yield {
            0: DeltaToolCall(
                name="finish", json_args='{"summary":"Reviewed actual omissions."}'
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    events = await _events(
        engine.run_turn(session, MessageTurn(text="Review my original answer."))
    )
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert session.finished
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before

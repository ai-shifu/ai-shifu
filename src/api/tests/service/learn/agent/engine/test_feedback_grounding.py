"""Check feedback source policy delivery, not real-model semantic compliance."""

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
            assert "Could the learner copy this hint as a passing answer?" in policy
            assert "A prior side-question explanation" in policy
            assert "# Correction pacing" in policy
            assert "do not reveal the complete answer" in policy
            assert "the current hint stage and aspect limit" in next(
                t.description for t in info.function_tools if t.name == "interact"
            )
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


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("retry_saved_answer", [False, True])
async def test_resumed_answer_receives_current_criterion_review(
    reload: bool, retry_saved_answer: bool
) -> None:
    """Scope the review to resumed SDK calls without changing original evidence."""
    calls = 0
    original = "Cache reduces memory waits; DMA reduces I/O waits; superscalar issues together."

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Inspect real request instructions and emit controlled deferred calls."""
        nonlocal calls
        calls += 1
        policy = info.instructions or ""
        if calls == 1:
            assert "# Review this returned interaction" not in policy
            yield "Describe the required techniques and effects."
            spec = {"type": "text", "prompt": "Techniques", "placeholder": "Answer"}
        elif calls == 2:
            assert policy.endswith(
                "Do not expose this review procedure to the learner."
            )
            assert "Match every required point" in policy
            assert "already covered, contradicted, or not supplied" in policy
            assert "A missing label cannot undo a successful meaning match" in policy
            assert "Select hints only from genuinely unmatched requirements" in policy
            assert "A question followed by its own worked reasoning" in policy
            assert "An ordered checklist of the answer" in policy
            assert "An internal list of all gaps is not the current hint" in policy
            assert "across both content and interaction fields" in policy
            assert (
                "A clarification or navigation response is not an answer attempt"
                in policy
            )
            assert original in ModelMessagesTypeAdapter.dump_json(messages).decode()
            yield "RISC and hardware threading were not supplied. Please address RISC first."
            spec = {"type": "text", "prompt": "Techniques", "placeholder": "Correction"}
        else:
            assert calls == 3
            # A later free-form review is not a newly resumed interaction.
            assert "# Review this returned interaction" not in policy
            yield "General explanation."
            spec = {"type": "text", "prompt": "Follow-up", "placeholder": "Answer"}
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(spec),
                tool_call_id=f"review-{calls}",
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(
        "Require RISC, hardware threading, superscalar and memory/I/O bottleneck relief. "
        "Concrete methods with effects suffice; the category title is optional."
    )
    await _events(engine.run_turn(session))
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    if retry_saved_answer:
        # The answer was accepted before a provider request failed. Resume the
        # saved deferred call without asking the learner to submit again.
        session.answers[session.pending[0].tool_call_id] = original
        session.pending = []
    if reload:
        session = Session.loads(session.dumps())
    turn = (
        ContinueTurn()
        if retry_saved_answer
        else InteractionResponseTurn(id=session.pending[0].tool_call_id, text=original)
    )
    events = await _events(engine.run_turn(session, turn))
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert not session.finished
    assert session.pending[0].spec.type == "text"
    # The same engine must not leak a previous run's review into another session.
    another = await engine.new_session("Explain generally, then ask a follow-up.")
    await _events(engine.run_turn(another, MessageTurn(text="Explain generally.")))
    assert calls == 3


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_unshown_interaction_review_does_not_claim_a_learner_answer(
    reload: bool,
) -> None:
    """Keep synthetic host refusals distinct from submitted learner evidence."""
    calls = 0

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Inspect resumed host context and emit a renderable replacement."""
        nonlocal calls
        calls += 1
        if calls == 2:
            policy = info.instructions or ""
            assert "When the host says the question was never shown" in policy
            assert "do not grade or attribute a response to the learner" in policy
            assert "with the learner's actual response" not in policy
            assert (
                "nothing was answered"
                in ModelMessagesTypeAdapter.dump_json(messages).decode()
            )
        spec = {
            "type": "text",
            "prompt": "Unshowable" if calls == 1 else "Renderable question",
            "placeholder": "Answer",
        }
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(spec),
                tool_call_id=f"unshown-{calls}",
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("Ask the question.")
    await _events(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    engine.interaction_check = lambda spec: (
        "Cannot render" if spec.prompt == "Unshowable" else None
    )
    events = await _events(engine.run_turn(session, ContinueTurn()))
    assert not any(isinstance(event, ErrorEvent) for event in events)
    assert session.pending[0].spec.prompt == "Renderable question"
    assert session.answers == {}
    assert not session.finished


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

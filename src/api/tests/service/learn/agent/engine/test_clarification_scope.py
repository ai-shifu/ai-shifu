"""Check phase-scoped instructions without claiming factual model compliance."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import Engine, InteractionResponseTurn, Session
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    RetryPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .test_direction_feedback import _call, _collect, _text


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("feedback_contract", [False, True])
@pytest.mark.parametrize("examples_allowed", [False, True])
async def test_clarification_keeps_authored_limits_without_correction_withholding(
    reload: bool, feedback_contract: bool, examples_allowed: bool
) -> None:
    """Deliver distinct phase guidance while retaining source, input and history."""
    preamble = "Answer knowledge questions briefly; do not advance the exercise.\n\n"
    if not examples_allowed:
        preamble += "Do not give worked examples; provide a short conceptual hint.\n\n"
    section = (
        "## Question\nExplain a loop.\n?[...Explanation]\n\n"
        "### Acceptance\nA loop repeats while its condition holds.\n\n"
        "### Correction\nAsk one check; leave its reasoning to the learner.\n\n"
    )
    script = preamble + section + "?[Next]\n"
    question = "Could you briefly illustrate how a loop's counter changes?"
    calls = 0

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Inspect real SDK phase guidance and return a controlled clarification."""
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
        correction = "For checking-direction and authored-help correction feedback,"
        assert correction in notice
        assert notice.index(correction) < notice.index(
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
        yield (
            "A counter initialized to 2 can decrease once per iteration: 2, 1, 0."
            if examples_allowed
            else "A loop repeats while its condition holds."
        )
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


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("aspect_limit", [None, 2])
async def test_authored_help_retains_correction_scope_and_teacher_multiplicity(
    reload: bool, aspect_limit: int | None
) -> None:
    """Keep correction authority outside the one-aspect direction branch too."""
    rule = (
        "For an incorrect answer, ask two guiding questions without revealing reasoning."
        if aspect_limit == 2
        else "For an incorrect answer, ask guiding questions without revealing reasoning."
    )
    script = rule + "\n\n## Question\nExplain a loop.\n?[...Explanation]\n"
    answer = "A loop always runs once."
    args = {"type": "text", "prompt": "", "placeholder": "Explanation"}
    review = {
        "answer_id": "original",
        "phase": "authored_help",
        "submission_quote": answer,
        "rule_quote": rule,
        "reason": "Use the teacher's permitted guiding questions and withhold reasoning.",
    }
    calls = 0

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Inspect the actual authored-help request before returning native feedback."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(args, "original")
            return
        instructions = info.instructions or ""
        marker = '{"status":"authored_section"'
        reference = json.loads(instructions[instructions.index(marker) :])
        assert reference["text"] == script
        notice = reference["notice"]
        assert "For checking-direction and authored-help correction feedback," in notice
        assert "Preserve authored multiplicity" in notice
        assert "A conditional example applies only when its condition matches" in notice
        assert "do not enumerate other gaps or supply later reasoning" in notice
        assert "within authored brevity and disclosure rules" in notice
        yield "What determines repetition? When does the loop stop?"
        yield _call({**args, "review": review}, "continued")

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=1
    )
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=answer))
    )
    assert calls == 2
    assert _text(events) == "What determines repetition? When does the loop stop?"
    assert session.pending[0].tool_call_id == "continued"
    assert not session.finished
    assert not session.all_memory()
    assert session.script.script == script
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_clarification_retry_keeps_authored_limits_and_native_boundary(
    reload: bool,
) -> None:
    """Keep phase authority after undeclared prose and a control-only retry."""
    script = "Answer knowledge questions briefly.\nExplain a loop.\n?[...Explanation]\n"
    question = "Could you briefly show two loop iterations and their state changes?"
    explanation = "Iteration 1: counter 2 to 1; iteration 2: counter 1 to 0."
    args = {"type": "text", "prompt": "", "placeholder": "Explanation"}
    review = {
        "answer_id": "original",
        "phase": "clarification",
        "submission_quote": question,
        "reason": "Answer the requested knowledge walkthrough concisely and retain the exercise.",
    }
    calls = 0

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Exercise the native retry chain while inspecting its request-local guidance."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(args, "original")
        elif calls == 2:
            yield "Undisplayed walkthrough draft."
            yield _call(args, "undeclared")
        elif calls == 3:
            yield _call({**args, "review": review}, "control-only")
        else:
            assert calls == 4
            retry = [
                p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)
            ][-1]
            assert "Regenerate the complete authored feedback" in str(retry.content)
            assert "within authored brevity and disclosure rules" in (
                info.instructions or ""
            )
            assert (
                "Do not apply correction-only withholding to permitted clarification"
                in (info.instructions or "")
            )
            assert question in ModelMessagesTypeAdapter.dump_json(messages).decode()
            assert (
                "Undisplayed walkthrough draft"
                not in ModelMessagesTypeAdapter.dump_json(messages).decode()
            )
            yield explanation
            yield _call({**args, "review": review}, "complete")

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=3
    )
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=question))
    )
    assert calls == 4
    assert _text(events) == explanation
    assert not session.finished
    assert not session.all_memory()
    assert session.pending[0].tool_call_id == "complete"
    assert session.pending[0].spec.placeholder == "Explanation"
    assert session.script.script == script
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert "Undisplayed walkthrough draft" not in session.dumps()

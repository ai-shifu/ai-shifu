"""Exercise structured direction provenance, display gating and deferred controls.

Controlled SDK responses test the contract, not real-model single-focus quality.
"""

import copy
import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import (
    ContentDelta,
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
)
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, TextPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

RULE = "First give one checking direction, one aspect per round."
CRITERION = "Require prior memory storage."
SCRIPT = (
    "# Lesson\n" + RULE + "\n\n## Execution\n"
    "Explain stored-program execution.\n?[...Answer]\n\n"
    "### Acceptance\n" + CRITERION + "\n"
    "Then accept a complete correction, explain and wait for Next.\n?[Next]\n"
    "## Another question\nExplain an instruction.\n?[...Instruction]\n"
)
WRONG = "A program executes without prior memory storage."
ISSUE = "Your answer denies prior storage."
QUESTION = "Where does the processor obtain its first instruction?"
DISPLAY = "> " + WRONG + "\n\n" + ISSUE + "\n\n" + QUESTION


def _direction() -> dict:
    return {
        "answer_id": "original",
        "rule_quote": RULE,
        "aspect_limit": 1,
        "focuses": [
            {
                "criterion_quote": CRITERION,
                "submission_quote": WRONG,
                "observed_issue": ISSUE,
                "guiding_question": QUESTION,
            }
        ],
    }


def _call(args: dict, call_id: str) -> dict[int, DeltaToolCall]:
    return {
        0: DeltaToolCall(
            name="interact", json_args=json.dumps(args), tool_call_id=call_id
        )
    }


def _text(events: list) -> str:
    return "".join(e.text for e in events if isinstance(e, ContentDelta))


async def _collect(events: AsyncIterator) -> list:
    result = [e async for e in events]
    assert not [e for e in result if isinstance(e, ErrorEvent)]
    return result


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("listen", [False, True])
@pytest.mark.parametrize("saved_answer", [False, True])
@pytest.mark.parametrize("transport", ["text", "browser_values"])
@pytest.mark.parametrize("normalized_control", [False, True])
async def test_structured_direction_uses_one_request_and_preserves_navigation(
    reload: bool,
    listen: bool,
    saved_answer: bool,
    transport: str,
    normalized_control: bool,
) -> None:
    """Keep original source/answers and complete correction acceptance across reload."""
    from flaskr.service.learn.agent.run_agent import _turn_input

    calls = 0

    async def model(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Inspect the SDK contract and return controlled deferred interactions."""
        nonlocal calls
        calls += 1
        assert "direction" in next(
            tool.parameters_json_schema["properties"]
            for tool in info.function_tools
            if tool.name == "interact"
        )
        if calls == 1:
            yield "Explain stored-program execution."
            yield _call(
                {
                    "type": "single" if normalized_control else "text",
                    "prompt": "Explain",
                    "placeholder": "Answer",
                    **(
                        {"options": [{"display": "...Answer"}]}
                        if normalized_control
                        else {}
                    ),
                },
                "original",
            )
        elif calls == 2:
            assert WRONG in ModelMessagesTypeAdapter.dump_json(messages).decode()
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                    "variable": "invented",
                },
                "correction",
            )
        elif calls == 3:
            assert DISPLAY in "".join(
                p.content for m in messages for p in m.parts if isinstance(p, TextPart)
            )
            yield "Accepted complete correction."
            yield _call(
                {"type": "single", "prompt": "", "options": [{"display": "Next"}]},
                "next",
            )
        else:
            assert calls == 4
            yield "Another question."
            yield _call(
                {"type": "text", "prompt": "Instruction", "placeholder": "Instruction"},
                "another",
            )

    engine = Engine(
        FunctionModel(stream_function=model), request_limit=1, memory_admission=True
    )
    session = await engine.new_session(SCRIPT, listen_mode=listen)
    await _collect(engine.run_turn(session))
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    if saved_answer:
        session.answers["original"] = (
            "Learner chose: " if transport == "browser_values" else "Learner wrote: "
        ) + WRONG
        session.pending = []
        session.request_inputs = [WRONG]
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(
            session,
            ContinueTurn()
            if saved_answer
            else _turn_input(session, [WRONG])
            if transport == "browser_values"
            else InteractionResponseTurn(text=WRONG),
        )
    )
    assert _text(events) == DISPLAY
    for event in events:
        if isinstance(event, ContentDelta):
            assert event.prepared_content == DISPLAY
            assert set(event.model_dump()) == {"type", "text"}
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert session.script.script == SCRIPT
    assert len(session.pending) == 1
    assert session.pending[0].spec.prompt == ""
    assert session.pending[0].spec.placeholder == "Answer"
    assert session.pending[0].spec.variable is None
    assert session.memory == session.user_memory == {}
    assert not session.finished
    session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(
            session,
            InteractionResponseTurn(
                text="Prepare program and data in memory, then fetch and execute automatically."
            ),
        )
    )
    assert _text(events) == "Accepted complete correction."
    assert session.pending[0].tool_call_id == "next"
    assert "Another question" not in _text(events)
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(values=["Next"]))
    )
    assert _text(events) == "Another question."
    assert calls == 4


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad",
    [
        "two_focuses",
        "rule",
        "criterion",
        "submission",
        "answer_id",
        "extra_prompt",
        "free_prose",
        "second_interaction",
        "other_section",
        "answer_wrapper",
        "markup",
        "chosen_wrapper",
        "finish_first",
        "finish_last",
        "remember_first",
        "remember_last",
    ],
)
async def test_invalid_direction_is_retried_before_display_and_not_saved_as_teaching(
    bad: str,
) -> None:
    """Reject the whole invalid response rather than clipping it into a passing hint."""
    calls = 0
    leak = "Storage? And how is the next action chosen?"

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Return controlled arguments to exercise provenance and display boundaries."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield "Question."
            yield _call(
                {"type": "text", "prompt": "Explain", "placeholder": "Answer"},
                "original",
            )
            return
        args = {
            "type": "text",
            "prompt": "",
            "placeholder": "Answer",
            "direction": _direction(),
        }
        if calls == 2:
            if bad == "two_focuses":
                args["direction"]["focuses"] *= 2
            elif bad in {"rule", "answer_id"}:
                args["direction"]["rule_quote" if bad == "rule" else "answer_id"] = (
                    "not original"
                )
            elif bad in {"criterion", "submission"}:
                args["direction"]["focuses"][0][bad + "_quote"] = "not original"
            elif bad == "other_section":
                args["direction"]["focuses"][0]["criterion_quote"] = (
                    "Explain an instruction."
                )
            elif bad == "chosen_wrapper":
                args["direction"]["focuses"][0]["submission_quote"] = "Learner chose: "
            elif bad == "answer_wrapper":
                args["direction"]["focuses"][0]["submission_quote"] = "Learner wrote: "
            elif bad == "markup":
                args["direction"]["focuses"][0]["guiding_question"] = (
                    '<interact type="text" />'
                )
            elif bad == "extra_prompt":
                args["prompt"] = "How is the next action chosen?"
            elif bad == "free_prose":
                yield leak[:10]
                yield leak[10:]
            call = _call(args, "invalid")
            if bad == "second_interaction":
                call[1] = DeltaToolCall(
                    name="interact",
                    json_args='{"type":"text","prompt":"extra"}',
                    tool_call_id="extra",
                )
            if bad.startswith(("finish_", "remember_")):
                name = bad.split("_", 1)[0]
                sibling = DeltaToolCall(
                    name=name,
                    json_args=json.dumps(
                        {"summary": "done"}
                        if name == "finish"
                        else {"key": "unsafe_note", "value": "unaccepted direction"}
                    ),
                    tool_call_id="sibling",
                )
                call = (
                    {0: sibling, 1: call[0]}
                    if bad.endswith("first")
                    else {0: call[0], 1: sibling}
                )
            yield call
        else:
            assert calls == 3
            yield _call(args, "valid")

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == DISPLAY
    assert session.pending[0].tool_call_id == "valid"
    assert len(session.pending) == 1
    assert not session.finished
    assert session.memory == session.user_memory == {}
    teaching = "".join(
        p.content for m in session.messages for p in m.parts if isinstance(p, TextPart)
    )
    assert leak not in teaching
    assert calls == 3


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [2, None])
async def test_direction_preserves_multiple_or_unspecified_authored_counts(
    limit: int | None,
) -> None:
    """Allow authored multiplicity without creating a global single-question rule."""
    rule = (
        "Give two checking directions together."
        if limit
        else "Give checking directions."
    )
    plan = copy.deepcopy(_direction())
    plan["rule_quote"] = rule
    plan["aspect_limit"] = limit
    plan["focuses"] *= 2
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Return controlled arguments to exercise provenance and display boundaries."""
        nonlocal calls
        calls += 1
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Answer",
                **({"direction": plan} if calls == 2 else {}),
            },
            "original" if calls == 1 else "multiple",
        )

    engine = Engine(FunctionModel(stream_function=model), request_limit=1)
    session = await engine.new_session(SCRIPT.replace(RULE, rule))
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events).count(QUESTION) == 2
    assert calls == 2


@pytest.mark.anyio
async def test_direction_pause_is_saved_before_visible_feedback_can_be_interrupted() -> (
    None
):
    """A disconnect after the hint cannot lose the already prepared correction input."""
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Return controlled arguments to exercise provenance and display boundaries."""
        nonlocal calls
        calls += 1
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Answer",
                **({"direction": _direction()} if calls == 2 else {}),
            },
            "original" if calls == 1 else "correction",
        )

    engine = Engine(FunctionModel(stream_function=model), request_limit=1)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    stream = engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    async for event in stream:
        if isinstance(event, ContentDelta):
            break
    await stream.aclose()
    restored = Session.loads(session.dumps())
    assert restored.pending[0].tool_call_id == "correction"
    assert not restored.answers
    assert not restored.interrupted
    assert calls == 2


@pytest.mark.anyio
async def test_anchored_failure_before_tool_keeps_unseen_answer_for_reload() -> None:
    """Retry an unseen buffered response from its original answer without lost teaching."""
    calls = 0

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Fail before selecting a direction, then accept the same restored answer."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
        elif calls == 2:
            yield "Unfinished candidate feedback."
            message = "provider interrupted before tool arguments"
            raise RuntimeError(message)
        else:
            assert calls == 3
            evidence = ModelMessagesTypeAdapter.dump_json(messages).decode()
            assert WRONG in evidence
            assert "Unfinished candidate feedback" not in evidence
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "direction": _direction(),
                },
                "correction",
            )

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    original = ModelMessagesTypeAdapter.dump_json(session.messages)
    events = [
        event
        async for event in engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    ]
    assert any(isinstance(event, ErrorEvent) for event in events)
    assert not _text(events)
    assert session.answers == {"original": "Learner wrote: " + WRONG}
    assert not session.interrupted
    assert ModelMessagesTypeAdapter.dump_json(session.messages) == original
    session = Session.loads(session.dumps())
    events = await _collect(engine.run_turn(session, ContinueTurn()))
    assert _text(events) == DISPLAY
    assert not session.answers
    assert session.pending[0].tool_call_id == "correction"


@pytest.mark.anyio
async def test_omitted_requirement_has_no_invented_submission_quote() -> None:
    """An omission may bind the actual answer without inventing words the learner said."""
    calls = 0
    direction = _direction()
    direction["focuses"][0]["submission_quote"] = None
    direction["focuses"][0]["observed_issue"] = "Your answer omits prior storage."

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Return an omission with an exact author criterion and no claimed quotation."""
        nonlocal calls
        calls += 1
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Answer",
                **({"direction": direction} if calls == 2 else {}),
            },
            "original" if calls == 1 else "correction",
        )

    engine = Engine(FunctionModel(stream_function=model), request_limit=1)
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(
            session, InteractionResponseTurn(text="Instructions run automatically.")
        )
    )
    assert _text(events) == "Your answer omits prior storage.\n\n" + QUESTION
    assert calls == 2


def test_direction_requires_an_explicit_authored_limit_or_null() -> None:
    from flaskr.service.learn.agent.engine.direction import DirectionFeedback
    from pydantic import ValidationError

    plan = _direction()
    plan.pop("aspect_limit")
    with pytest.raises(ValidationError, match="aspect_limit"):
        DirectionFeedback.model_validate(plan)
    plan["aspect_limit"] = None
    assert DirectionFeedback.model_validate(plan).aspect_limit is None

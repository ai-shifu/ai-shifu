"""Profile evidence uses the same canonical keys as accepted engine answers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flaskr.api.markdownflow import ScriptBundle, Session
from flaskr.service.profile.api import SYS_USER_NICKNAME
from flaskr.service.profile_research.engine_runtime import (
    profile_answer_evidence,
    run_profile_turn,
)
from markdownflow.engine.questions import format_question
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from tests.service.profile_research.test_single_session_engine import (
    Stream,
    _finish,
    _question,
    _returns,
    _session,
)

if TYPE_CHECKING:
    from flaskr.service.profile_research.session import _ProfileResearchSession
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


def _answer_named_question(question: str) -> _ProfileResearchSession:
    marker = format_question(question)
    assert marker is not None
    session = _session("?[" + marker + " ...Your answer?]")

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        if _returns(messages, "finish"):
            yield "Done."
        elif _returns(messages):
            yield _finish()
        else:
            yield {0: _question("answer", "\u0085 " + question + " \u001f")}

    model = FunctionModel(stream_function=script)
    run_profile_turn(session, {}, model)
    assert session.engine_session["pending"][0]["spec"]["question"] == question
    # Exercise native cache serialization before the answer is accepted.
    session = type(session).from_cache_payload(session.to_cache_payload())
    result = run_profile_turn(session, {question: ["Accepted answer"]}, model)
    assert result.input_accepted
    assert session.memory[question] == "Accepted answer"
    return session


def test_padded_nickname_binding_stays_out_of_profile_evidence() -> None:
    session = _answer_named_question(SYS_USER_NICKNAME)
    assert profile_answer_evidence(session) == []


@pytest.mark.parametrize(
    "question", ["Your  learning goal?", "Which [path] | level//hint...?", "a}"]
)
def test_evidence_keeps_the_canonical_opaque_key(question: str) -> None:
    session = _answer_named_question(question)
    assert profile_answer_evidence(session) == [
        {
            "prompt": "Your answer?",
            "question": question,
            "answer": "Learner wrote: Accepted answer",
        }
    ]


def _history_with_variable(question: object) -> _ProfileResearchSession:
    session = _session("Ask a question.")
    native = Session(
        id=session.session_id,
        user_id=session.user_bid,
        script=ScriptBundle(script=session.document),
        messages=[
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="interact",
                        tool_call_id="answer",
                        args={"type": "text", "prompt": "Goal?", "question": question},
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="interact",
                        tool_call_id="answer",
                        content="Learner wrote: Learn",
                    )
                ]
            ),
        ],
    )
    session.engine_session = native.to_dict()
    return session


@pytest.mark.parametrize("question", [None, "", " \t\n", "\u0085\u001f\u3000"])
def test_old_blank_optional_bindings_remain_unnamed_evidence(
    question: str | None,
) -> None:
    session = _history_with_variable(question)
    assert profile_answer_evidence(session) == [
        {"prompt": "Goal?", "question": None, "answer": "Learner wrote: Learn"}
    ]


@pytest.mark.parametrize("question", ["bad\x00key", "x}}y", "a\nb", 7, ["goal"]])
def test_invalid_saved_bindings_cannot_become_profile_evidence(
    question: object,
) -> None:
    assert profile_answer_evidence(_history_with_variable(question)) == []


def test_legacy_saved_tool_field_is_read_as_a_question_memory_key() -> None:
    session = _history_with_variable("Your learning goal?")
    calls = session.engine_session["messages"]
    # Older native histories stored this field before question terminology.
    for message in calls:
        for part in message["parts"]:
            if part.get("tool_name") == "interact" and "args" in part:
                args = part["args"]
                if isinstance(args, dict) and "question" in args:
                    args["variable"] = args.pop("question")
    assert profile_answer_evidence(session) == [
        {
            "prompt": "Goal?",
            "question": "Your learning goal?",
            "answer": "Learner wrote: Learn",
        }
    ]


def test_standalone_unclosed_braces_cannot_hide_a_native_profile_question() -> None:
    from flaskr.service.profile_research.document import (
        validate_profile_research_document,
    )

    question = "What would you like to learn?"
    source = "{{ unfinished ordinary text\n?[%{{" + question + "}}...Your answer?]"
    metadata = validate_profile_research_document(source)
    assert metadata["questions"] == [question]
    assert metadata["interaction_block_count"] == 1
    assert metadata["content_block_count"] == 1
    session = _session(source)

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        if _returns(messages, "finish"):
            yield "Done."
        elif _returns(messages):
            yield _finish()
        else:
            yield {0: _question("answer", question)}

    model = FunctionModel(stream_function=script)
    run_profile_turn(session, {}, model)
    assert session.engine_session["pending"][0]["spec"]["question"] == question
    result = run_profile_turn(session, {question: ["Build one project."]}, model)
    assert result.input_accepted
    assert session.memory[question] == "Build one project."


@pytest.mark.parametrize("count", [2, 98, 99])
def test_native_question_spans_determine_profile_block_counts_and_limits(
    count: int,
) -> None:
    from flaskr.service.profile_research.document import (
        validate_profile_research_document,
    )
    from flaskr.service.profile_research.session import ProfileResearchValidationError

    source = "{{ unfinished ordinary text\n" + "\n".join(
        "?[%{{Question " + str(index) + "?}}...Your answer]" for index in range(count)
    )
    if count == 99:
        with pytest.raises(ProfileResearchValidationError, match="too many blocks"):
            validate_profile_research_document(source)
    else:
        metadata = validate_profile_research_document(source)
        assert metadata["block_count"] == count + 1
        assert metadata["interaction_block_count"] == count
        assert metadata["content_block_count"] == 1


@pytest.mark.parametrize("raw", ["", "   ", "What\nnow?", "bad\x00key", "bad\u0085key"])
def test_profile_rejects_invalid_authored_question_bindings(raw: str) -> None:
    from flaskr.service.profile_research.document import (
        validate_profile_research_document,
    )
    from flaskr.service.profile_research.session import ProfileResearchValidationError

    with pytest.raises(
        ProfileResearchValidationError, match="question text is invalid"
    ):
        validate_profile_research_document("?[%{{" + raw + "}} Yes|No]")

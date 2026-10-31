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
from markdownflow.syntax.variable_names import format_variable_assignment
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


def _answer_named_question(variable: str) -> _ProfileResearchSession:
    marker = format_variable_assignment(variable)
    assert marker is not None
    session = _session("?[" + marker + " ...Your answer?]")

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        if _returns(messages, "finish"):
            yield "Done."
        elif _returns(messages):
            yield _finish()
        else:
            yield {0: _question("answer", "\u0085 " + variable + " \u001f")}

    model = FunctionModel(stream_function=script)
    run_profile_turn(session, {}, model)
    assert session.engine_session["pending"][0]["spec"]["variable"] == variable
    # Exercise native cache serialization before the answer is accepted.
    session = type(session).from_cache_payload(session.to_cache_payload())
    result = run_profile_turn(session, {variable: ["Accepted answer"]}, model)
    assert result.input_accepted
    assert session.variables[variable] == "Accepted answer"
    return session


def test_padded_nickname_binding_stays_out_of_profile_evidence() -> None:
    session = _answer_named_question(SYS_USER_NICKNAME)
    assert profile_answer_evidence(session) == []


@pytest.mark.parametrize(
    "variable", ["Your  learning goal?", "Which [path] | level//hint...?", "a}"]
)
def test_evidence_keeps_the_canonical_opaque_key(variable: str) -> None:
    session = _answer_named_question(variable)
    assert profile_answer_evidence(session) == [
        {
            "prompt": "Your answer?",
            "variable": variable,
            "answer": "Learner wrote: Accepted answer",
        }
    ]


def _history_with_variable(variable: object) -> _ProfileResearchSession:
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
                        args={"type": "text", "prompt": "Goal?", "variable": variable},
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


@pytest.mark.parametrize("variable", [None, "", " \t\n", "\u0085\u001f\u3000"])
def test_old_blank_optional_bindings_remain_unnamed_evidence(
    variable: str | None,
) -> None:
    session = _history_with_variable(variable)
    assert profile_answer_evidence(session) == [
        {"prompt": "Goal?", "variable": None, "answer": "Learner wrote: Learn"}
    ]


@pytest.mark.parametrize("variable", ["bad\x00key", "x}}y", "a\nb", 7, ["goal"]])
def test_invalid_saved_bindings_cannot_become_profile_evidence(
    variable: object,
) -> None:
    assert profile_answer_evidence(_history_with_variable(variable)) == []

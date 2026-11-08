"""Exercise Profile answer evidence with the current model tool contract."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.profile.api import SYS_USER_NICKNAME
from flaskr.service.profile_research.engine_runtime import (
    profile_answer_evidence,
    run_profile_turn,
)
from flaskr.service.profile_research.runtime import _collected_nickname
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.service.profile_research.test_single_session_engine import (
    _finish,
    _returns,
    _session,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

    from tests.service.profile_research.test_single_session_engine import Stream


@pytest.mark.parametrize("batched", [False, True])
def test_question_only_tool_records_canonical_answers_and_keeps_nickname_private(
    batched: bool,
) -> None:
    question = "What would you like to learn?"
    nickname_question = SYS_USER_NICKNAME
    session = _session(
        f"?[{{{{ {question} }}}}...Share your goal]\n\n"
        f"?[{{{{{SYS_USER_NICKNAME}}}}}...Enter your nickname]"
    )

    def ask(
        call_id: str, wording: str, placeholder: str, *, index: int = 0
    ) -> dict[int, DeltaToolCall]:
        return {
            index: DeltaToolCall(
                name="interact",
                tool_call_id=call_id,
                json_args=json.dumps(
                    {"type": "text", "question": wording, "placeholder": placeholder}
                ),
            )
        }

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        answers = _returns(messages)
        if _returns(messages, "finish"):
            yield ""
        elif len(answers) == 2:
            yield _finish()
        elif answers:
            assert not batched, "Do not call the model between queued sibling questions"
            yield nickname_question
            yield ask("nickname", nickname_question, "Enter your nickname")
        else:
            yield f"{question}\n\n{nickname_question}" if batched else question
            calls = ask("goal", question, "Share your goal")
            if batched:
                calls.update(
                    ask("nickname", nickname_question, "Enter your nickname", index=1)
                )
            yield calls

    model = FunctionModel(stream_function=script)
    first = run_profile_turn(session, {}, model)
    assert first.chunks[-1].interaction_id == "goal"
    assert "".join(chunk.content for chunk in first.chunks[:-1]) == (
        f"{question}\n\n{nickname_question}" if batched else question
    )
    session = type(session).from_cache_payload(session.to_cache_payload())
    second = run_profile_turn(session, {question: ["Algebra"]}, model)
    assert second.input_accepted
    assert second.chunks[-1].interaction_id == "nickname"
    assert "".join(chunk.content for chunk in second.chunks[:-1]) == (
        "" if batched else nickname_question
    )
    session = type(session).from_cache_payload(session.to_cache_payload())
    final = run_profile_turn(session, {nickname_question: ["Learner"]}, model)
    assert final.input_accepted
    assert session.variables == {question: "Algebra", nickname_question: "Learner"}
    assert _collected_nickname(session) == "Learner"
    assert profile_answer_evidence(session) == [
        {
            "prompt": question,
            "variable": question,
            "answer": "Learner wrote: Algebra",
            "question_context": {
                "is_learner_fact": False,
                "placeholder": "Share your goal",
            },
        }
    ]

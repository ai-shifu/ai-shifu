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
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.service.profile_research.test_single_session_engine import (
    _finish,
    _returns,
    _session,
)
from tests.service.profile_research.test_v2_runtime import _run, _runtime, _start

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

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        answers = _returns(messages)
        if _returns(messages, "finish"):
            yield ""
        elif len(answers) == 2:
            yield _finish()
        elif answers:
            assert not batched, "Do not call the model between queued sibling questions"
            yield nickname_question
            yield _text_input("nickname", nickname_question, "Enter your nickname")
        else:
            yield f"{question}\n\n{nickname_question}" if batched else question
            calls = _text_input("goal", question, "Share your goal")
            if batched:
                calls.update(
                    _text_input(
                        "nickname", nickname_question, "Enter your nickname", index=1
                    )
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


def _text_input(
    call_id: str, question: str, placeholder: str, *, index: int = 0, **fields: object
) -> dict[int, DeltaToolCall]:
    return {
        index: DeltaToolCall(
            name="interact",
            tool_call_id=call_id,
            json_args=json.dumps(
                {
                    "type": "text",
                    "question": question,
                    "placeholder": placeholder,
                    **fields,
                }
            ),
        )
    }


def test_profile_keeps_its_authored_control_instead_of_a_generated_lookalike() -> None:
    session = _session("What would you like to learn?\n?[...Answer]")
    attempt = 0

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            question = "What is your favorite game?"
            yield question
            yield _text_input("generated", question, "Answer", generated_control=True)
            return
        assert attempt == 2
        assert any(
            isinstance(part, RetryPromptPart)
            and part.tool_name == "interact"
            and "authored questionnaire" in str(part.content)
            for part in messages[-1].parts
        )
        question = "What would you like to learn?"
        yield question
        yield _text_input("authored", question, "Answer")

    turn = run_profile_turn(session, {}, FunctionModel(stream_function=script))
    assert turn.chunks[-1].interaction_id == "authored"
    assert "".join(chunk.content for chunk in turn.chunks[:-1]) == (
        "What would you like to learn?"
    )


def test_localized_profile_keeps_distinct_bound_questions_with_shared_input_shape() -> (
    None
):
    session = _session("?[{{goal}}...Your answer]\n\n?[{{background}}...Your answer]")
    session.output_language = "fr-FR"
    placeholder = "Votre réponse"

    async def script(messages: list[ModelMessage], info: AgentInfo) -> Stream:
        assert "Do not translate a question written in a leading {{...}} binding" in (
            info.instructions or ""
        )
        if _returns(messages, "finish"):
            yield ""
            return
        answers = _returns(messages)
        if len(answers) == 2:
            yield _finish()
            return
        question = "background" if answers else "goal"
        yield question
        yield _text_input(f"ask-{question}", question, placeholder)

    model = FunctionModel(stream_function=script)
    first = run_profile_turn(session, {}, model)
    second = run_profile_turn(session, {"goal": ["Apprendre la géométrie"]}, model)
    final = run_profile_turn(session, {"background": ["Enseignement"]}, model)

    for turn, question in [(first, "goal"), (second, "background")]:
        question_chunk, input_chunk = turn.chunks
        assert question_chunk.content == question
        assert input_chunk.interaction_id == f"ask-{question}"
        assert input_chunk.interaction.endswith(f"...{placeholder}]")
    assert final.finished
    assert session.variables == {
        "goal": "Apprendre la géométrie",
        "background": "Enseignement",
    }


def test_pending_structured_correction_reloads_guidance_before_its_input() -> None:
    original = "What skill would you like to develop?"
    guiding = "Which part of that skill would you practice first?"
    rule = "First give one checking direction, one aspect per round."
    criterion = "Require a specific skill."
    placeholder = "Share your answer"
    answer = "Everything."
    document = f"{rule}\n\n## Learning goal\n{criterion}\n?[{{{{{original}}}}}...{placeholder}]"
    calls = 0

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal calls
        calls += 1
        if not _returns(messages):
            yield original
            yield _text_input("original", original, placeholder)
        else:
            yield _text_input(
                "correction",
                guiding,
                placeholder,
                feedback={
                    "answer_id": "original",
                    "rule_quote": rule,
                    "aspect_limit": 1,
                    "accepted_quotes": [],
                    "focuses": [
                        {
                            "criterion_quote": criterion,
                            "submission_quote": answer,
                            "observed_issue": "The answer does not name a specific skill.",
                            "guiding_question": guiding,
                        }
                    ],
                },
            )

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, document)
    _run(runtime, view)
    initial = _run(
        runtime,
        view,
        values={original: [answer]},
        expected_interaction_id="original",
        request_id="submit",
    )
    reloaded = _run(runtime, view, request_id="reload")
    exact_replay = _run(runtime, view, request_id="reload", index=2)

    assert any(
        event["event_type"] == "content" and guiding in event["content"]
        for event in initial
    )
    (initial_input,) = [
        event for event in initial if event["event_type"] == "interaction"
    ]
    (interaction,) = [
        event for event in reloaded if event["event_type"] == "interaction"
    ]
    assert any(
        event["event_type"] == "content" and event["content"] == guiding
        for event in reloaded[: reloaded.index(interaction)]
    )
    assert interaction["interaction_id"] == "correction"
    assert interaction["content"] == initial_input["content"]
    assert exact_replay == reloaded
    assert calls == 2

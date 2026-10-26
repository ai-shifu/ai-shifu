"""Profile questionnaires use the native full-script session and answer lifecycle."""

from __future__ import annotations

import copy
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from flask import Flask
from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.service.profile.api import SYS_USER_NICKNAME
from flaskr.service.profile_research.engine_runtime import (
    ProfileTurnResult,
    profile_answer_evidence,
    run_profile_turn,
)
from flaskr.service.profile_research.runtime import ProfileResearchRuntime
from flaskr.service.profile_research.session import (
    PROFILE_ONBOARDING_PURPOSE,
    ProfileResearchError,
    _ProfileResearchSession,
    _ProfileResearchSessionStore,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

Stream = AsyncIterator[str | dict[int, DeltaToolCall]]


def _session(document: str) -> _ProfileResearchSession:
    return _ProfileResearchSession(
        session_id="single-native-session",
        user_bid="profile-learner",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        document=document,
        model="test-model",
        temperature=0.3,
        output_language="en-US",
        config_revision=10,
    )


def _question(
    call_id: str,
    question: str | None,
    *,
    kind: str = "text",
    prompt: str = "Your answer?",
    options: list[dict[str, str]] | None = None,
) -> DeltaToolCall:
    args: dict[str, Any] = {"type": kind, "prompt": prompt}
    if question is not None:
        args["question"] = question
    if options:
        args["options"] = options
    return DeltaToolCall(
        name="interact", tool_call_id=call_id, json_args=json.dumps(args)
    )


def _finish() -> dict[int, DeltaToolCall]:
    return {
        0: DeltaToolCall(
            name="finish", tool_call_id="finish", json_args='{"summary":"Done"}'
        )
    }


def _returns(
    messages: list[ModelMessage], tool: str = "interact"
) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == tool
    ]


def _content(result: ProfileTurnResult) -> str:
    return "".join(chunk.content for chunk in result.chunks)


def test_complete_source_and_history_survive_sequential_questions_and_finish() -> None:
    document = (
        "Introduce the questionnaire.\n---\n"
        "?[%{{role}}Teacher//teacher|Engineer//engineer]\n---\n"
        "If role is teacher, ask which learners they teach.\n"
        "?[%{{learners}}...Who do you teach?]"
    )
    session = _session(document)
    calls: list[list[ModelMessage]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        calls.append(messages)
        if _returns(messages, "finish"):
            yield "Thank you."
        elif len(_returns(messages)) == 2:
            yield "All done."
            yield _finish()
        elif _returns(messages):
            assert _returns(messages)[0].content == "Learner chose: teacher"
            yield {0: _question("learners", "learners", prompt="Who do you teach?")}
        else:
            initial = "\n".join(
                str(part.content)
                for message in messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, UserPromptPart)
            )
            assert "If role is teacher" in initial
            assert "Who do you teach?" in initial
            assert "profile_research_prior_evidence" not in initial
            yield "Welcome."
            yield {
                0: _question(
                    "role",
                    "role",
                    kind="single",
                    prompt="Your role?",
                    options=[
                        {"display": "Teacher", "value": "teacher"},
                        {"display": "Engineer", "value": "engineer"},
                    ],
                )
            }

    model = FunctionModel(stream_function=script)
    first = run_profile_turn(session, {}, model)
    assert first.reason == "interaction"
    assert first.chunks[-1].interaction_id == "role"
    assert not first.finished
    assert session.engine_session["script"]["script"] == document
    assert session.engine_session["id"] == session.session_id
    assert profile_answer_evidence(session) == []
    second = run_profile_turn(session, {"role": ["Teacher"]}, model)
    assert second.input_accepted
    assert second.chunks[-1].interaction_id == "learners"
    session = _ProfileResearchSession.from_cache_payload(session.to_cache_payload())
    last = run_profile_turn(session, {"learners": ["Adults"]}, model)
    assert last.finished
    assert last.input_accepted
    assert last.reason == "finished"
    assert session.memory == {"role": "teacher", "learners": "Adults"}
    assert profile_answer_evidence(session) == [
        {
            "prompt": "Your role?",
            "question": "role",
            "answer": "Learner chose: teacher",
            "question_context": {
                "is_learner_fact": False,
                "options": [
                    {"display": "Teacher", "value": "teacher"},
                    {"display": "Engineer", "value": "engineer"},
                ],
            },
        },
        {
            "prompt": "Who do you teach?",
            "question": "learners",
            "answer": "Learner wrote: Adults",
        },
    ]
    assert session.engine_session["id"] == "single-native-session"
    assert len(calls[-1]) > len(calls[0])


def test_multiple_pending_keep_native_answers_and_exclude_confirm_and_nickname() -> (
    None
):
    session = _session(
        "?[%{{goal}}...Goal?]\n?[%{{sys_user_nickname}}...Name?]\n"
        "?[Continue]\n?[%{{pace}}...Pace?]"
    )
    calls = 0

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal calls
        calls += 1
        if _returns(messages, "finish"):
            yield "Thank you."
        elif _returns(messages):
            assert len(_returns(messages)) == 4
            yield "Thanks."
            yield _finish()
        else:
            yield "Tell us about yourself."
            yield {
                0: _question("goal", "goal", prompt="Goal?"),
                1: _question("name", SYS_USER_NICKNAME, prompt="Name?"),
                2: _question("confirm", None, kind="confirm", prompt="Continue"),
                3: _question("pace", "pace", prompt="Pace?"),
            }

    model = FunctionModel(stream_function=script)
    first = run_profile_turn(session, {}, model)
    assert [chunk.interaction_id for chunk in first.chunks if chunk.interaction] == [
        "goal"
    ]
    assert len(session.engine_session["pending"]) == 4
    after_first = run_profile_turn(session, {"goal": ["Learn Python"]}, model)
    assert after_first.input_accepted
    assert after_first.chunks[-1].interaction_id == "name"
    assert calls == 1
    assert session.engine_session["answers"] == {"goal": "Learner wrote: Learn Python"}
    assert profile_answer_evidence(session) == [
        {"prompt": "Goal?", "question": "goal", "answer": "Learner wrote: Learn Python"}
    ]
    session = _ProfileResearchSession.from_cache_payload(session.to_cache_payload())
    run_profile_turn(session, {SYS_USER_NICKNAME: ["Pat"]}, model)
    confirm = run_profile_turn(session, {"arbitrary": ["continue"]}, model)
    assert confirm.input_accepted
    assert confirm.chunks[-1].interaction_id == "pace"
    assert calls == 1
    assert len(profile_answer_evidence(session)) == 1
    final = run_profile_turn(session, {"pace": ["Slow"]}, model)
    assert final.finished
    assert [item["question"] for item in profile_answer_evidence(session)] == [
        "goal",
        "pace",
    ]
    assert session.engine_session["answers"] == {}


def test_named_binding_rejects_wrong_key_and_ignores_extraneous_values() -> None:
    session = _session("?[%{{role}}Teacher//teacher|Engineer//engineer]")
    calls = 0

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal calls
        calls += 1
        if _returns(messages, "finish"):
            yield "Thanks."
        elif _returns(messages):
            assert _returns(messages)[0].content == "Learner chose: teacher"
            yield "Done."
            yield _finish()
        else:
            yield {
                0: _question(
                    "role",
                    "role",
                    kind="single",
                    options=[
                        {"display": "Teacher", "value": "teacher"},
                        {"display": "Engineer", "value": "engineer"},
                    ],
                )
            }

    model = FunctionModel(stream_function=script)
    run_profile_turn(session, {}, model)
    original = copy.deepcopy(session.engine_session)
    rejected = run_profile_turn(session, {"unrelated": ["teacher"]}, model)
    assert not rejected.input_accepted
    assert rejected.chunks[-1].interaction_id == "role"
    assert calls == 1
    assert session.engine_session == original
    assert session.memory == {}
    assert profile_answer_evidence(session) == []
    run_profile_turn(session, {}, model)
    assert calls == 1
    accepted = run_profile_turn(
        session, {"role": ["Teacher"], "unrelated": ["Engineer"]}, model
    )
    assert accepted.input_accepted
    assert accepted.finished
    assert session.memory == {"role": "teacher"}
    assert "Engineer" not in profile_answer_evidence(session)[0]["answer"]


@pytest.mark.parametrize("kind", ["single_or_text", "multi_or_text"])
def test_mixed_answers_preserve_option_and_free_text(kind: str) -> None:
    separator = "|" if kind == "single_or_text" else "||"
    session = _session("?[%{{background}}Teacher//teacher" + separator + "...Other]")

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        if _returns(messages, "finish"):
            yield "Thanks."
        elif _returns(messages):
            assert _returns(messages)[0].content == (
                "Learner chose: teacher; and wrote: I mentor adults"
            )
            yield "Done."
            yield _finish()
        else:
            yield {
                0: _question(
                    "background",
                    "background",
                    kind=kind,
                    options=[{"display": "Teacher", "value": "teacher"}],
                )
            }

    model = FunctionModel(stream_function=script)
    run_profile_turn(session, {}, model)
    result = run_profile_turn(
        session, {"background": ["Teacher", "I mentor adults"]}, model
    )
    assert result.input_accepted
    assert result.finished
    assert session.memory["background"] == "teacher; I mentor adults"
    assert "I mentor adults" in profile_answer_evidence(session)[0]["answer"]


def test_end_requires_native_continue_and_does_not_create_another_session() -> None:
    session = _session("Introduce this short questionnaire, then close it.")
    calls = 0

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield "Introduction."
        elif _returns(messages, "finish"):
            yield "Thank you."
        else:
            yield "Completed."
            yield _finish()

    model = FunctionModel(stream_function=script)
    first = run_profile_turn(session, {}, model)
    assert first.reason == "end"
    assert not first.finished
    first_messages = copy.deepcopy(session.engine_session["messages"])
    second = run_profile_turn(session, {}, model)
    assert second.finished
    assert second.reason == "finished"
    assert session.engine_session["id"] == session.session_id
    assert session.engine_session["messages"][: len(first_messages)] == first_messages


def test_rejected_model_attempt_cannot_publish_text_or_pollute_native_history() -> None:
    session = _session("?[%{{goal}}...Goal?]")
    calls = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield "REJECTED DRAFT."
            yield {
                0: _question(
                    "bad",
                    "goal",
                    kind="single",
                    options=[{"display": "Bad\nbutton"}],
                )
            }
        else:
            yield "Accepted preface."
            yield {0: _question("goal", "goal", prompt="Goal?")}

    result = run_profile_turn(session, {}, FunctionModel(stream_function=script))
    assert "REJECTED" not in _content(result)
    assert "Accepted preface." in _content(result)
    assert "REJECTED" not in json.dumps(session.engine_session["messages"])
    assert result.chunks[-1].interaction_id == "goal"


def test_unrenderable_cached_question_fails_without_running_or_mutating_state() -> None:
    session = _session("?[%{{role}}Teacher//teacher|Engineer//engineer]")
    calls = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal calls
        calls += 1
        yield {
            0: _question(
                "role",
                "role",
                kind="single",
                options=[
                    {"display": "Teacher", "value": "teacher"},
                    {"display": "Engineer", "value": "engineer"},
                ],
            )
        }

    model = FunctionModel(stream_function=script)
    run_profile_turn(session, {}, model)
    session.engine_session["pending"][0]["spec"]["options"][0]["display"] = (
        "Bad\nbutton"
    )
    original = copy.deepcopy(session.to_cache_payload())
    with pytest.raises(ProfileResearchError, match="cannot resume"):
        run_profile_turn(session, {"role": ["teacher"]}, model)
    assert calls == 1
    assert session.to_cache_payload() == original


def test_changed_static_option_is_retried_without_publishing_the_rejected_response() -> (
    None
):
    session = _session("?[%{{role}}Teacher//teacher|Engineer//engineer]")
    calls = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield "REJECTED CHANGED OPTIONS."
            options = [
                {"display": "Teacher", "value": "parent"},
                {"display": "Engineer", "value": "engineer"},
            ]
        else:
            yield "Accepted question."
            options = [
                {"display": "Enseignant", "value": "teacher"},
                {"display": "Ingénieur", "value": "engineer"},
            ]
        yield {0: _question(f"role-{calls}", "role", kind="single", options=options)}

    result = run_profile_turn(session, {}, FunctionModel(stream_function=script))
    assert calls == 2
    assert "REJECTED" not in _content(result)
    assert "Accepted question." in _content(result)
    assert "parent" not in result.chunks[-1].interaction
    assert "Enseignant//teacher" in result.chunks[-1].interaction
    assert "REJECTED" not in json.dumps(session.engine_session["messages"])
    assert session.memory == {}


def test_natural_questionnaire_uses_native_controls_without_a_static_question_set() -> (
    None
):
    session = _session("?[%{{goal}}Writing//writing|Speaking//speaking]")

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        if _returns(messages, "finish"):
            yield "Thanks."
        elif _returns(messages):
            yield "Done."
            yield _finish()
        else:
            yield {
                0: _question(
                    "natural-goal",
                    "goal",
                    kind="single",
                    options=[
                        {"display": "Writing", "value": "writing"},
                        {"display": "Speaking", "value": "speaking"},
                    ],
                )
            }

    model = FunctionModel(stream_function=script)
    first = run_profile_turn(session, {}, model)
    assert first.chunks[-1].interaction_id == "natural-goal"
    final = run_profile_turn(session, {"goal": ["writing"]}, model)
    assert final.finished
    assert session.memory == {"goal": "writing"}


def test_static_option_braces_stay_literal_despite_memory_values() -> None:
    session = _session("?[%{{role}}Primary//{{primary}}|Other//other]")
    session.memory["primary"] = "teacher"

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        if _returns(messages, "finish"):
            yield "Thanks."
        elif _returns(messages):
            yield "Done."
            yield _finish()
        else:
            yield {
                0: _question(
                    "role",
                    "role",
                    kind="single",
                    options=[
                        {"display": "Primary", "value": "{{primary}}"},
                        {"display": "Other", "value": "other"},
                    ],
                )
            }

    model = FunctionModel(stream_function=script)
    run_profile_turn(session, {}, model)
    session.memory["primary"] = "untrusted-host-value"
    result = run_profile_turn(session, {"role": ["{{primary}}"]}, model)
    assert result.input_accepted
    assert session.memory["role"] == "{{primary}}"
    assert session.memory["primary"] == "teacher"


def test_rich_output_keeps_structured_elements_and_no_private_summary_is_requested() -> (
    None
):
    session = _session("Present an introduction and ask ?[%{{goal}}...Goal?]")

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        yield "Introduction.\n\n<div>Rich illustration</div>\n\nNext."
        yield {0: _question("goal", "goal", prompt="Goal?")}

    result = run_profile_turn(session, {}, FunctionModel(stream_function=script))
    assert "html" in {chunk.type for chunk in result.chunks}
    assert "Introduction." in _content(result)
    assert "Rich illustration" in _content(result)
    assert "Next." in _content(result)
    assert session.engine_session["script"]["script"] == session.document
    assert "profile_research_summary" not in json.dumps(
        session.engine_session["script"]
    )


def test_fatal_model_retries_leave_the_full_native_session_unmodified() -> None:
    session = _session("?[%{{role}}Teacher//teacher|Engineer//engineer]")
    original = copy.deepcopy(session.to_cache_payload())

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        yield "REJECTED CONTENT.\n\n```html\n<div>Rejected</div>\n```\n\nTail."
        yield {
            0: _question(
                "wrong",
                "role",
                kind="single",
                options=[{"display": "Extra", "value": "extra"}],
            )
        }

    with pytest.raises(ProfileResearchError, match="failed to execute"):
        run_profile_turn(session, {}, FunctionModel(stream_function=script))
    assert session.to_cache_payload() == original


def test_natural_questionnaire_confirm_waits_for_an_actual_learner_response() -> None:
    session = _session(
        "Welcome the learner and pause until they confirm readiness, then finish."
    )
    calls = 0

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal calls
        calls += 1
        if _returns(messages, "finish"):
            yield "Thanks."
        elif _returns(messages):
            assert _returns(messages)[0].content.startswith("Learner pressed continue.")
            yield "Ready."
            yield _finish()
        else:
            yield "Welcome. Confirm when you are ready."
            yield {0: _question("ready", None, kind="confirm", prompt="Continue")}

    model = FunctionModel(stream_function=script)
    first = run_profile_turn(session, {}, model)
    assert first.reason == "interaction"
    assert not first.finished
    assert first.chunks[-1].interaction_id == "ready"
    assert calls == 1
    rerendered = run_profile_turn(session, {}, model)
    assert rerendered.chunks[-1].interaction_id == "ready"
    assert calls == 1
    last = run_profile_turn(session, {"arbitrary": ["continue"]}, model)
    assert last.input_accepted
    assert last.finished
    assert profile_answer_evidence(session) == []


def test_private_summary_receives_selected_machine_value_and_question_option_meanings() -> (
    None
):
    summary_messages: list[list[dict[str, str]]] = []

    class SummaryProvider:
        def complete(self, messages: list[dict[str, str]], **_kwargs: object) -> str:
            summary_messages.append(messages)
            return "从事工程工作。"

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        if _returns(messages, "finish"):
            yield "谢谢。"
        elif _returns(messages):
            assert _returns(messages)[0].content == "Learner chose: role_1"
            yield "问卷完成。"
            yield _finish()
        else:
            yield {
                0: _question(
                    "role",
                    "role",
                    kind="single",
                    prompt="你的身份？",
                    options=[
                        {"display": "工程师", "value": "role_1"},
                        {"display": "教师", "value": "role_2"},
                    ],
                )
            }

    app = Flask("profile-option-meanings")
    app.config.update(LLM_MODEL_1_ID="gpt-test", DEFAULT_LLM_TEMPERATURE=0.3)
    model = FunctionModel(stream_function=script)
    runtime = ProfileResearchRuntime(
        app,
        store=_ProfileResearchSessionStore(app, cache=InMemoryCacheProvider()),
        model_factory=lambda *_args: model,
        provider_factory=lambda *_args: SummaryProvider(),
    )
    view = runtime.start_session(
        user_bid="learner",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        document="?[%{{role}}工程师//role_1|教师//role_2]",
        config_revision=1,
        output_language="zh-CN",
    )
    first = list(
        runtime.stream_session(
            user_bid="learner",
            session_id=view["session_id"],
            user_input=None,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_turn_index=0,
            request_id="render",
        )
    )
    assert any("工程师//role_1" in str(event["content"]) for event in first)
    final = list(
        runtime.stream_session(
            user_bid="learner",
            session_id=view["session_id"],
            user_input={"role": ["工程师"]},
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_turn_index=1,
            expected_interaction_id="role",
            request_id="answer",
        )
    )
    assert final[-1]["content"]["profile_draft"] == "从事工程工作。"
    evidence = json.loads(summary_messages[0][-1]["content"])["accepted_answers"]
    assert evidence == [
        {
            "prompt": "你的身份？",
            "question": "role",
            "answer": "Learner chose: role_1",
            "question_context": {
                "is_learner_fact": False,
                "options": [
                    {"display": "工程师", "value": "role_1"},
                    {"display": "教师", "value": "role_2"},
                ],
            },
        }
    ]


@pytest.mark.parametrize("snapshot", [None, {"primary": "teacher"}])
@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("followup", [False, True])
def test_saved_expanded_profile_controls_resume_without_rewriting_answers(
    snapshot: dict | None, count: int, followup: bool
) -> None:
    from flaskr.api.markdownflow import (
        InteractionSpec,
        Option,
        PendingInteraction,
        ScriptBundle,
        Session,
    )
    from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart

    document = "\n---\n".join(
        "?[%{{role" + str(index) + "}}Primary//{{primary}}|Other//other]"
        for index in range(count)
    )
    session = _session(document)
    session.memory["primary"] = "changed-host-value"
    specs = [
        InteractionSpec(
            type="single",
            prompt="Role?",
            question=f"role{index}",
            options=[
                Option(display="Primary", value="teacher"),
                Option(display="Other", value="other"),
            ],
        )
        for index in range(count)
    ]
    calls = ModelResponse(
        parts=[
            ToolCallPart("interact", spec.model_dump(), f"old-{index}")
            for index, spec in enumerate(specs)
        ]
    )
    old_prompt = (
        '<memory>\n{"primary": "teacher"}\n</memory>\n\n<script>\n'
        + document.replace("{{primary}}", "teacher")
        + "\n</script>"
    )
    working = Session(
        id=session.session_id,
        user_id=session.user_bid,
        script=ScriptBundle(script=document),
        memory={"primary": "teacher"},
        initial_memory=snapshot,
        messages=[ModelRequest(parts=[UserPromptPart(old_prompt)]), calls],
        pending=[
            PendingInteraction(tool_call_id=f"old-{index}", spec=spec)
            for index, spec in enumerate(specs)
        ],
    )
    session.engine_session = working.to_dict()
    historical_call = session.engine_session["messages"][1]
    model_calls = 0
    retried = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        nonlocal model_calls
        model_calls += 1
        if _returns(messages, "finish"):
            yield "Thanks."
        else:
            assert len(_returns(messages)) == count
            assert all(
                part.content == "Learner chose: teacher" for part in _returns(messages)
            )
            assert document in messages[0].parts[0].content
            if followup:
                retries = [
                    p for p in messages[-1].parts if isinstance(p, RetryPromptPart)
                ]
                retried.extend(retries)
                yield {
                    0: _question(
                        "new-role",
                        "role0",
                        kind="single",
                        options=[
                            {
                                "display": "Primary",
                                "value": "{{primary}}" if retries else "teacher",
                            },
                            {"display": "Other", "value": "other"},
                        ],
                    )
                }
            else:
                yield _finish()

    model = FunctionModel(stream_function=script)
    preview = run_profile_turn(session, {}, model)
    assert preview.chunks[-1].interaction_id == "old-0"
    assert "teacher" in preview.chunks[-1].interaction
    assert model_calls == 0
    for index in range(count):
        result = run_profile_turn(session, {f"role{index}": ["teacher"]}, model)
        assert result.input_accepted
        # Rehydrate the real persisted native snapshot before answering a sibling.
        session.engine_session = json.loads(json.dumps(session.engine_session))
    assert result.finished is not followup
    assert bool(retried) is followup
    if followup:
        assert (
            session.engine_session["pending"][0]["spec"]["options"][0]["value"]
            == "{{primary}}"
        )
    assert session.engine_session["messages"][1] == historical_call
    assert all(session.memory[f"role{index}"] == "teacher" for index in range(count))
    assert document in session.engine_session["messages"][0]["parts"][0]["content"]


def test_new_profile_controls_cannot_use_historical_expanded_values() -> None:
    from pydantic_ai.messages import RetryPromptPart

    session = _session("?[%{{role}}Primary//{{primary}}|Other//other]")
    session.memory["primary"] = "teacher"
    rejected = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> Stream:
        retries = [p for p in messages[-1].parts if isinstance(p, RetryPromptPart)]
        if retries:
            rejected.extend(retries)
        yield {
            0: _question(
                "new-role",
                "role",
                kind="single",
                options=[
                    {
                        "display": "Primary",
                        "value": "{{primary}}" if retries else "teacher",
                    },
                    {"display": "Other", "value": "other"},
                ],
            )
        }

    result = run_profile_turn(session, {}, FunctionModel(stream_function=script))
    assert rejected
    assert not result.input_accepted
    assert (
        session.engine_session["pending"][0]["spec"]["options"][0]["value"]
        == "{{primary}}"
    )

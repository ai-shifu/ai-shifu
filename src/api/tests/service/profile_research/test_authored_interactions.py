"""Keep static authored controls authoritative and content blocks free of interactions."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

import pytest
from pydantic_ai.messages import ModelRequest, RetryPromptPart
from pydantic_ai.models.function import DeltaToolCall

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _finish,
    _finished,
    _interact,
    _run,
    _runtime,
    _start,
    _terminal,
    _tool_returns,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


def _authored_role_spec() -> dict[str, Any]:
    return {
        "type": "single",
        "prompt": "Choose your role",
        "variable": "role",
        "options": [
            {"display": "Teacher", "value": "teacher"},
            {"display": "Engineer", "value": "engineer"},
        ],
    }


def _alter_spec(defect: str) -> dict[str, Any]:
    spec = deepcopy(_authored_role_spec())
    if defect == "machine_value":
        spec["options"][0]["value"] = "wrong-role"
    elif defect == "missing_option":
        spec["options"].pop()
    elif defect == "extra_option":
        spec["options"].append({"display": "Other", "value": "wrong-role"})
    elif defect == "option_order":
        spec["options"].reverse()
    elif defect == "selection_type":
        spec["type"] = "multi"
    elif defect == "variable":
        spec["variable"] = "wrong_variable"
    elif defect == "missing_variable":
        del spec["variable"]
    return spec


@pytest.mark.parametrize(
    "defect",
    [
        "machine_value",
        "missing_option",
        "extra_option",
        "option_order",
        "selection_type",
        "variable",
        "missing_variable",
    ],
)
def test_drifted_authored_control_is_retried_before_display_or_memory_write(
    defect: str,
) -> None:
    model_calls = 0
    retry_messages: list[RetryPromptPart] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal model_calls
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            model_calls += 1
            retry_messages.extend(
                part
                for message in messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, RetryPromptPart)
            )
            spec = _alter_spec(defect) if model_calls == 1 else _authored_role_spec()
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="drifted" if model_calls == 1 else "corrected",
                    json_args=json.dumps(spec),
                )
            }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{role}} Teacher//teacher | Engineer//engineer]")
    rendered = _run(runtime, view)
    controls = [event for event in rendered if event["event_type"] == "interaction"]

    assert model_calls == 2
    assert retry_messages
    assert len(controls) == 1
    assert controls[0]["interaction_id"] == "corrected"
    assert "wrong-role" not in controls[0]["content"]
    assert "wrong_variable" not in controls[0]["content"]
    before_answer = runtime.store.load(view["session_id"])
    assert before_answer.variables == {}
    assert before_answer.accepted_answers == []
    assert [
        pending["tool_call_id"] for pending in before_answer.engine_session["pending"]
    ] == ["corrected"]

    answered = _run(
        runtime,
        view,
        values={"role": ["teacher"]},
        request_id="answer",
        expected_interaction_id="corrected",
    )

    assert _terminal(answered)["next_block_index"] == 1
    assert runtime.store.load(view["session_id"]).variables == {"role": "teacher"}


def test_localized_displays_preserve_authored_machine_values() -> None:
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {
                0: _interact(
                    variable="role",
                    kind="single",
                    prompt="请选择你的角色",
                    options=[
                        {"display": "老师", "value": "teacher"},
                        {"display": "工程师", "value": "engineer"},
                    ],
                )
            }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{role}} Teacher//teacher | Engineer//engineer]")
    rendered = _run(runtime, view)
    control = next(event for event in rendered if event["event_type"] == "interaction")
    assert "老师//teacher" in control["content"]
    assert "工程师//engineer" in control["content"]
    _run(
        runtime,
        view,
        values={"role": ["teacher"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    assert runtime.store.load(view["session_id"]).variables == {"role": "teacher"}


def test_content_block_rejects_dynamic_controls_and_advances_after_plain_content() -> (
    None
):
    model_calls = 0
    retries: list[RetryPromptPart] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal model_calls
        model_calls += 1
        if model_calls == 1:
            yield {
                0: _interact(
                    variable=None,
                    kind="single",
                    prompt="What working style helps you learn?",
                    options=[
                        {"display": "Quiet study", "value": "quiet"},
                        {"display": "Discuss together", "value": "collaborative"},
                    ],
                )
            }
        else:
            retries.extend(
                part
                for message in messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, RetryPromptPart)
            )
            yield "Consider which working style suits your learning."

    _app, runtime, _factories = _runtime(script)
    view = _start(
        runtime, "Ask about the learner's working style.\n\n---\n\n?[Continue]"
    )
    rendered = _run(runtime, view)
    assert model_calls == 2
    assert retries
    assert not any(event["event_type"] == "interaction" for event in rendered)
    assert _terminal(rendered)["next_block_index"] == 1
    assert _terminal(rendered)["awaiting_input"] is False
    stored = runtime.store.load(view["session_id"])
    assert stored.variables == {}
    assert stored.accepted_answers == []
    assert stored.engine_session["pending"] == []

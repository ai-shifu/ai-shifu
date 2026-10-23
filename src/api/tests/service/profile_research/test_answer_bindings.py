"""Named bindings isolate submitted values; unnamed questions aggregate legacy keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _finish,
    _finished,
    _interact,
    _run,
    _runtime,
    _start,
    _SummaryProvider,
    _terminal,
    _tool_returns,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.mark.parametrize(
    ("kind", "variable", "values"),
    [
        ("text", "role", ["I teach adults"]),
        ("single_or_text", "role", ["teacher", "I teach adults"]),
        ("text", "sys_user_nickname", ["River"]),
    ],
)
def test_named_binding_rejects_other_keys_then_accepts_only_its_own_values(
    kind: str, variable: str, values: list[str]
) -> None:
    calls: list[list[ModelMessage]] = []
    returns: list[str] = []
    summary = _SummaryProvider()

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls.append(messages)
        if _finished(messages):
            yield " "
        elif answers := _tool_returns(messages):
            returns.append(str(answers[0].content))
            yield _finish()
        else:
            yield {
                0: _interact(
                    variable=variable,
                    kind=kind,
                    prompt="Your answer?",
                    options=[{"display": "Teacher", "value": "teacher"}]
                    if kind != "text"
                    else None,
                )
            }

    _app, runtime, _factories = _runtime(script)
    runtime._provider_factory = lambda *_args: summary
    view = _start(runtime, f"Collect %{{{{{variable}}}}} and finish.")
    _run(runtime, view)
    original = runtime.store.load(view["session_id"]).engine_session
    count = len(calls)
    rejected = _run(
        runtime,
        view,
        values={"unrelated": values},
        request_id="wrong",
        expected_interaction_id="question",
    )
    assert _terminal(rejected)["input_accepted"] is False
    assert _terminal(rejected)["awaiting_input"] is True
    saved = runtime.store.load(view["session_id"])
    assert saved.variables == {}
    for field in ("pending", "answers", "memory"):
        assert saved.engine_session[field] == original[field]
    assert len(calls) == count
    assert (
        _run(
            runtime,
            view,
            index=1,
            values={"unrelated": values},
            request_id="wrong",
            expected_interaction_id="question",
        )
        == rejected
    )
    final = _run(
        runtime,
        view,
        values={variable: values, "unrelated": ["Injected account owner"]},
        request_id="right",
        expected_interaction_id="question",
    )
    assert _terminal(final)["input_accepted"] is True
    assert all(value in returns[0] for value in values)
    assert "Injected account owner" not in returns[0]
    assert "Injected account owner" not in str(summary.messages)
    if variable == "sys_user_nickname":
        assert _terminal(final)["nickname"] == "River"
        assert _terminal(final)["profile_draft"] == ""
        assert summary.messages == []
    else:
        assert all(value in str(summary.messages) for value in values)


@pytest.mark.parametrize("kind", ["text", "single_or_text"])
def test_unnamed_question_preserves_answers_from_arbitrary_keys(kind: str) -> None:
    returns: list[str] = []
    summary = _SummaryProvider()

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif answers := _tool_returns(messages):
            returns.append(str(answers[0].content))
            yield _finish()
        else:
            yield {
                0: _interact(
                    variable=None,
                    kind=kind,
                    prompt="Your answer?",
                    options=[{"display": "Teacher", "value": "teacher"}]
                    if kind != "text"
                    else None,
                )
            }

    _app, runtime, _factories = _runtime(script)
    runtime._provider_factory = lambda *_args: summary
    view = _start(runtime, "Ask about learning needs and finish.")
    _run(runtime, view)
    selected = "teacher" if kind != "text" else "I teach adults"
    _run(
        runtime,
        view,
        values={"custom-choice": [selected], "custom-text": ["After work"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    assert selected in returns[0]
    assert "After work" in returns[0]
    assert selected in str(summary.messages)
    assert "After work" in str(summary.messages)

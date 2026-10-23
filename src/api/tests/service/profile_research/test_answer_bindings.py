"""Preserve named input bindings and legacy unnamed-answer aggregation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _evidence,
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

_OPTIONS = [
    {"display": "Teacher", "value": "teacher"},
    {"display": "Engineer", "value": "engineer"},
]


def _source(kind: str, variable: str | None) -> str:
    binding = f"%{{{{{variable}}}}} " if variable else ""
    if kind == "text":
        return f"?[{binding}...Your answer]"
    separator = " || " if kind == "multi_or_text" else " | "
    choices = f"Teacher//teacher{separator}Engineer//engineer"
    hint = f"{separator}...Your answer" if kind.endswith("_or_text") else ""
    return f"?[{binding}{choices}{hint}]"


@pytest.mark.parametrize(
    ("kind", "variable", "value"),
    [
        ("text", "role", "I teach adults"),
        ("single_or_text", "role", "teacher"),
        ("text", "sys_user_nickname", "River"),
    ],
)
def test_named_question_rejects_values_supplied_only_under_an_unrelated_key(
    kind: str, variable: str, value: str
) -> None:
    model_calls: list[list[ModelMessage]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        model_calls.append(messages)
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {
                0: _interact(
                    variable=variable,
                    kind=kind,
                    prompt="Your answer",
                    options=_OPTIONS if kind != "text" else None,
                )
            }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, _source(kind, variable))
    _run(runtime, view)
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    call_count = len(model_calls)
    rejected = _run(
        runtime,
        view,
        values={"unrelated": [value]},
        request_id="wrong-key",
        expected_interaction_id="question",
    )

    assert _terminal(rejected)["advanced"] is False
    assert _terminal(rejected)["next_block_index"] == 0
    assert _terminal(rejected)["awaiting_input"] is True
    question = next(event for event in rejected if event["event_type"] == "interaction")
    assert question["interaction_id"] == "question"
    unchanged = runtime.store.load(view["session_id"]).to_cache_payload()
    for field in ("variables", "accepted_answers", "context", "block_index"):
        assert unchanged[field] == original[field]
    for field in ("pending", "answers", "memory", "profile_research_answered_count"):
        assert unchanged["engine_session"].get(field) == original["engine_session"].get(
            field
        )
    assert len(model_calls) == call_count
    assert (
        _run(
            runtime,
            view,
            values={"unrelated": [value]},
            request_id="wrong-key",
            expected_interaction_id="question",
        )
        == rejected
    )
    assert len(model_calls) == call_count


@pytest.mark.parametrize(
    ("kind", "variable", "values", "expected_memory", "expected_raw"),
    [
        ("text", "role", ["I teach adults"], "I teach adults", ["I teach adults"]),
        (
            "single_or_text",
            "role",
            ["teacher", "I teach adults"],
            "teacher; I teach adults",
            ["teacher", "I teach adults"],
        ),
        ("text", "sys_user_nickname", ["River"], "River", []),
    ],
)
def test_named_answer_ignores_extra_keys_in_model_memory_and_summary_evidence(
    kind: str,
    variable: str,
    values: list[str],
    expected_memory: str,
    expected_raw: list[str],
) -> None:
    unrelated = "Unrelated account administrator"
    tool_results: list[str] = []
    summaries: list[dict[str, Any]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif factories[-1] == 1:
            summaries.append(_evidence(messages))
            yield "Uses the learner's own answer."
        elif answers := _tool_returns(messages):
            tool_results.append(str(answers[0].content))
            yield _finish()
        else:
            yield {
                0: _interact(
                    variable=variable,
                    kind=kind,
                    prompt="Your answer",
                    options=_OPTIONS if kind != "text" else None,
                )
            }

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, _source(kind, variable))
    _run(runtime, view)
    answer = _run(
        runtime,
        view,
        values={variable: values, "unrelated": [unrelated]},
        request_id="answer",
        expected_interaction_id="question",
    )

    assert _terminal(answer)["next_block_index"] == 1
    assert len(tool_results) == 1
    assert all(value in tool_results[0] for value in values)
    assert unrelated not in tool_results[0]
    stored = runtime.store.load(view["session_id"])
    assert stored.variables == {variable: expected_memory}
    assert stored.accepted_answers == expected_raw
    _run(runtime, view, index=1, request_id="summary")
    assert summaries[0]["accepted_answers"] == {variable: expected_memory}
    assert summaries[0]["accepted_interaction_answers"] == expected_raw
    assert unrelated not in str(summaries[0])


@pytest.mark.parametrize("kind", ["text", "single_or_text"])
def test_unnamed_question_still_aggregates_answers_from_arbitrary_input_keys(
    kind: str,
) -> None:
    typed = "I study after work"
    selected = [] if kind == "text" else ["teacher"]
    submitted = {"custom-selection": selected, "custom-text": [typed]}
    expected_raw = [*selected, typed]
    if kind == "text":
        submitted = {"custom-text": [typed], "another-field": ["With real projects"]}
        expected_raw = [f"{typed}, With real projects"]
    tool_results: list[str] = []
    summaries: list[dict[str, Any]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif factories[-1] == 1:
            summaries.append(_evidence(messages))
            yield "Studies after work."
        elif answers := _tool_returns(messages):
            tool_results.append(str(answers[0].content))
            yield _finish()
        else:
            yield {
                0: _interact(
                    variable=None,
                    kind=kind,
                    prompt="Your answer",
                    options=_OPTIONS if kind != "text" else None,
                )
            }

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, _source(kind, None))
    _run(runtime, view)
    answer = _run(
        runtime,
        view,
        values=submitted,
        request_id="answer",
        expected_interaction_id="question",
    )

    assert _terminal(answer)["next_block_index"] == 1
    assert all(value in tool_results[0] for value in expected_raw)
    stored = runtime.store.load(view["session_id"])
    assert stored.variables == {}
    assert stored.accepted_answers == expected_raw
    _run(runtime, view, index=1, request_id="summary")
    assert summaries[0]["accepted_answers"] == {}
    assert summaries[0]["accepted_interaction_answers"] == expected_raw

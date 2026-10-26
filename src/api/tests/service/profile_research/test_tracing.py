"""Profile traces follow the persisted public result and private transformation steps."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from flaskr.service.profile_research import runtime as runtime_module
from flaskr.service.profile_research.runtime import PROFILE_ONBOARDING_PREVIEW_PURPOSE

from tests.service.profile_research.test_runtime import (
    _assistant_runtime,
    _import_answers,
)
from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _finish,
    _finished,
    _interact,
    _run,
    _runtime,
    _start,
    _tool_returns,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


class _Observation:
    def __init__(self, name: str, input_value: object) -> None:
        self.name = name
        self.input = input_value
        self.output: object = None

    def update(self, **kwargs: object) -> None:
        if "output" in kwargs:
            self.output = kwargs["output"]

    def end(self, **kwargs: object) -> None:
        self.update(**kwargs)


class _Trace:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.current = object()
        self.context: dict[str, Any] = {}
        self.native_events: list[object] = []
        self.output: list[str] = []
        self.children: list[_Observation] = []
        self.calls: list[tuple[str, object]] = []

    def set_context(self, **kwargs: object) -> None:
        self.context = kwargs

    def start_turn(self, **kwargs: object) -> object:
        self.calls.append(("start", kwargs))
        return self.current

    def event(self, event: object) -> None:
        self.native_events.append(event)

    def append_output(self, value: str) -> None:
        self.output.append(value)

    def child(self, name: str, **kwargs: object) -> _Observation:
        observation = _Observation(name, kwargs.get("input"))
        self.children.append(observation)
        return observation

    def complete_turn(self, outcome: str) -> None:
        self.calls.append(("complete", outcome))

    def finish(
        self, outcome: str | None = None, *, transport_closed: bool = False
    ) -> None:
        self.calls.append(("finish", {"outcome": outcome, "closed": transport_closed}))


@pytest.fixture
def traces(monkeypatch: pytest.MonkeyPatch) -> list[_Trace]:
    created: list[_Trace] = []

    def factory(**kwargs: object) -> _Trace:
        trace = _Trace(**kwargs)
        created.append(trace)
        return trace

    monkeypatch.setattr(runtime_module, "MarkdownFlowTrace", factory)
    return created


async def _questionnaire(
    messages: list[ModelMessage], _info: AgentInfo
) -> StreamChunks:
    if _finished(messages):
        yield " "
    elif _tool_returns(messages):
        yield _finish()
    else:
        yield "Welcome.\n"
        yield {0: _interact(call_id="goal", variable="goal", prompt="Your goal?")}


def test_profile_trace_records_context_controls_and_skips_exact_replay(
    traces: list[_Trace],
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    document = "Collect %{{goal}}, then finish."
    view = _start(runtime, document)
    events = _run(runtime, view)
    assert len(traces) == 1
    trace = traces[0]
    assert trace.kwargs["name"] == "profile"
    assert trace.kwargs["input"] == {"action": "start"}
    assert trace.kwargs["session_id"] == view["session_id"]
    assert trace.context["script"] == document
    assert "Welcome." in "".join(trace.output)
    assert "Your goal?" in "".join(trace.output)
    assert any(
        getattr(event, "type", "") == "tool.call" for event in trace.native_events
    )
    assert ("complete", "waiting") in trace.calls
    assert _run(runtime, view, index=0) == events
    assert len(traces) == 1


def test_private_summary_is_a_child_and_success_precedes_terminal_close(
    traces: list[_Trace],
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    view = _start(runtime, "Collect %{{goal}}, then finish.")
    _run(runtime, view)
    stream = runtime.stream_session(
        user_bid="v2-learner",
        session_id=view["session_id"],
        user_input={"goal": ["Practical skills"]},
        expected_purpose=view["purpose"],
        expected_turn_index=1,
        request_id="answer",
        expected_interaction_id="goal",
    )
    for event in stream:
        if event.get("is_terminal"):
            break
    stream.close()
    trace = traces[-1]
    assert trace.kwargs["input"] == {"goal": ["Practical skills"]}
    summary = next(child for child in trace.children if child.name == "profile.summary")
    assert "Practical skills" in str(summary.input)
    assert summary.output == "Private learner profile."
    assert "Private learner profile." not in "".join(trace.output)
    completed = trace.calls.index(("complete", "finished"))
    closed = next(
        i
        for i, (kind, value) in enumerate(trace.calls)
        if kind == "finish" and value["closed"]
    )
    assert completed < closed
    assert runtime.store.load(view["session_id"]).done


def test_failed_profile_save_has_no_public_output_or_success(
    traces: list[_Trace], monkeypatch: pytest.MonkeyPatch
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    view = _start(runtime, "Collect %{{goal}}, then finish.")

    def fail_save(_session: object) -> None:
        message = "storage unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(runtime.store, "save", fail_save)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        _run(runtime, view)
    assert traces[0].output == []
    assert not any(kind == "complete" for kind, _value in traces[0].calls)
    assert ("finish", {"outcome": "error", "closed": False}) in traces[0].calls


def test_preview_and_cumulative_output_have_stable_scene_and_no_duplicate_text(
    traces: list[_Trace],
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    view = _start(runtime, "Collect %{{goal}}.")
    session = runtime.store.load(view["session_id"])
    session.purpose = PROFILE_ONBOARDING_PREVIEW_PURPOSE
    trace = runtime._trace(session, input_value={"action": "start"})
    runtime._append_visible_output(
        trace,
        [
            {"type": "content", "content": "Hello", "generated_block_bid": "one"},
            {"type": "content", "content": "Hello world", "generated_block_bid": "one"},
            {
                "type": "interaction",
                "content": "Continue?",
                "generated_block_bid": "question",
            },
            {"type": "done", "content": {"profile_draft": "Private draft"}},
        ],
    )
    assert traces[0].kwargs["name"] == "profile-preview"
    assert "".join(traces[0].output) == "Hello worldContinue?"


def test_assistant_import_and_summary_share_one_request_without_private_root_output(
    traces: list[_Trace],
) -> None:
    app, runtime, view, _providers = _assistant_runtime(
        answers="I teach adults.", nickname="Rain", draft="Private imported profile."
    )
    with app.app_context():
        events = _import_answers(runtime, view)
    assert len(traces) == 1
    trace = traces[0]
    assert trace.kwargs["metadata"]["operation"] == "delegate"
    assert isinstance(trace.kwargs["input"], str)
    assert {child.name for child in trace.children} == {
        "profile.import",
        "profile.summary",
    }
    assert "Private imported profile." not in "".join(trace.output)
    assert json.loads("".join(trace.output)) == {"done": True, "operation": "delegate"}
    assert ("complete", "finished") in trace.calls
    assert events[-1]["content"]["done"]

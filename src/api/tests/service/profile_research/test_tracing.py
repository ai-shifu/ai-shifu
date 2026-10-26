"""Profile traces follow persisted public results with telemetry kept in its adapter."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.api import langfuse_markdownflow as tracing_module
from flaskr.service.profile_research.langfuse_tracing import ProfileTrace
from flaskr.service.profile_research.runtime import PROFILE_ONBOARDING_PREVIEW_PURPOSE

from tests import test_langfuse_v4_semantics as sdk_tests
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
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

captured_spans = sdk_tests.captured_spans


@pytest.fixture
def observations(
    captured_spans: object, monkeypatch: pytest.MonkeyPatch
) -> InMemorySpanExporter:
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(tracing_module, "get_langfuse_client", lambda: client)
    return exporter


def _roots(
    exporter: InMemorySpanExporter, scene: str = "profile"
) -> list[ReadableSpan]:
    return [span for span in exporter.get_finished_spans() if span.name == scene]


def _value(span: ReadableSpan, key: str) -> object:
    value = span.attributes.get(f"langfuse.observation.{key}")
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


async def _questionnaire(
    messages: list[ModelMessage], _info: AgentInfo
) -> StreamChunks:
    if _finished(messages):
        yield " "
    elif _tool_returns(messages):
        yield _finish()
    else:
        yield "Welcome.\n"
        yield {0: _interact(call_id="goal", question="goal", prompt="Your goal?")}


def test_profile_trace_records_context_controls_and_skips_exact_replay(
    observations: InMemorySpanExporter,
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    document = "Collect ?[%{{goal}} ...Your goal?], then finish."
    view = _start(runtime, document)
    events = _run(runtime, view)
    roots = _roots(observations)
    assert len(roots) == 1
    root = roots[0]
    assert _value(root, "input") == {"action": "start"}
    assert root.attributes["session.id"] == view["session_id"]
    spans = observations.get_finished_spans()
    context = next(span for span in spans if span.name == "prompts")
    assert _value(context, "input")["script"] == document
    assert "Welcome." in _value(root, "output")
    assert "Your goal?" in _value(root, "output")
    assert any(
        span.attributes.get("langfuse.observation.type") == "tool" for span in spans
    )
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == "waiting"
    assert _run(runtime, view, index=0) == events
    assert len(_roots(observations)) == 1


def test_private_summary_is_a_child_and_success_precedes_terminal_close(
    observations: InMemorySpanExporter,
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    view = _start(runtime, "Collect ?[%{{goal}} ...Your goal?], then finish.")
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
    root = _roots(observations)[-1]
    assert _value(root, "input") == {"goal": ["Practical skills"]}
    summary = next(
        span
        for span in observations.get_finished_spans()
        if span.name == "profile.summary"
    )
    assert "Practical skills" in str(_value(summary, "input"))
    assert _value(summary, "output") == "Private learner profile."
    assert summary.parent.span_id == root.context.span_id
    assert "Private learner profile." not in _value(root, "output")
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"] == "finished"
    )
    assert root.attributes["langfuse.observation.metadata.transport_closed"] is True
    assert runtime.store.load(view["session_id"]).done


def test_failed_profile_save_has_no_public_output_or_success(
    observations: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    view = _start(runtime, "Collect ?[%{{goal}} ...Your goal?], then finish.")

    def fail_save(_session: object) -> None:
        message = "storage unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(runtime.store, "save", fail_save)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        _run(runtime, view)
    root = _roots(observations)[0]
    assert not _value(root, "output")
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == "error"


def test_preview_and_cumulative_output_have_stable_scene_and_no_duplicate_text(
    observations: InMemorySpanExporter,
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    view = _start(runtime, "Collect ?[%{{goal}} ...Your goal?].")
    session = runtime.store.load(view["session_id"])
    session.purpose = PROFILE_ONBOARDING_PREVIEW_PURPOSE
    session.awaiting_input = True
    with ProfileTrace(session) as trace:
        trace.publish(
            session,
            [
                {"type": "content", "content": "Hello", "generated_block_bid": "one"},
                {
                    "type": "content",
                    "content": "Hello world",
                    "generated_block_bid": "one",
                },
                {
                    "type": "interaction",
                    "content": "Continue?",
                    "generated_block_bid": "question",
                },
                {"type": "done", "content": {"profile_draft": "Private draft"}},
            ],
        )
    assert (
        _value(_roots(observations, "profile-preview")[0], "output")
        == "Hello worldContinue?"
    )


def test_assistant_import_and_summary_share_one_request_without_private_root_output(
    observations: InMemorySpanExporter,
) -> None:
    app, runtime, view, _providers = _assistant_runtime(
        answers="I teach adults.", nickname="Rain", draft="Private imported profile."
    )
    with app.app_context():
        events = _import_answers(runtime, view)
    roots = _roots(observations)
    assert len(roots) == 1
    root = roots[0]
    assert root.attributes["langfuse.observation.metadata.operation"] == "delegate"
    assert _value(root, "input") == "My assistant's answer"
    private = [
        span
        for span in observations.get_finished_spans()
        if span.name in {"answer_extraction", "profile.summary"}
    ]
    assert {span.name for span in private} == {
        "answer_extraction",
        "profile.summary",
    }
    assert all(span.parent.span_id == root.context.span_id for span in private)
    assert _value(root, "output") == {"done": True, "operation": "delegate"}
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"] == "finished"
    )
    assert events[-1]["content"]["done"]


def test_standalone_private_summary_keeps_evidence_in_its_child(
    observations: InMemorySpanExporter,
) -> None:
    _app, runtime, _factories = _runtime(_questionnaire)
    view = _start(runtime, "Collect ?[%{{goal}} ...Your goal?].")
    session = runtime.store.load(view["session_id"])
    messages = [{"role": "user", "content": "Private accepted learner evidence."}]
    with ProfileTrace.summary(session, messages) as summary:
        summary.update(output="Private generated profile.")
    root = _roots(observations)[0]
    assert _value(root, "input") == {"action": "summary"}
    assert not _value(root, "output")
    child = next(
        span
        for span in observations.get_finished_spans()
        if span.name == "profile.summary"
    )
    assert _value(child, "input") == messages
    assert _value(child, "output") == "Private generated profile."

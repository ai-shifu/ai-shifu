"""Verify request tracing against SDK spans without exporting learner data."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.api import langfuse_markdownflow as tracing
from langfuse import Langfuse
from langfuse._client.resource_manager import LangfuseResourceManager
from langfuse._client.span_exporter import LangfuseTransformingSpanExporter
from markdownflow import (
    ErrorEvent,
    InteractionRequest,
    InteractionSpec,
    MemoryUpdated,
    ToolCall,
    ToolResult,
    TurnDone,
)
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def observations(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InMemorySpanExporter]:
    """Capture real SDK observations in memory while disabling its remote exporter."""
    monkeypatch.setattr(
        LangfuseTransformingSpanExporter,
        "export",
        lambda _self, _spans: SpanExportResult.SUCCESS,
        raising=False,
    )
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    client = Langfuse(
        public_key="pk-lf-markdownflow-coordinator-tests",
        secret_key="sk-lf-markdownflow-coordinator-tests",
        host="http://langfuse.invalid",
        tracer_provider=provider,
        tracing_enabled=True,
    )
    monkeypatch.setattr(tracing, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(tracing, "get_request_id", lambda: "request-1")
    monkeypatch.setattr(tracing, "get_request_trace_id", lambda: "a" * 32)
    try:
        yield exporter
    finally:
        client.shutdown()
        provider.shutdown()
        LangfuseResourceManager._instances.clear()


def _trace(**kwargs: object) -> tracing.MarkdownFlowTrace:
    return tracing.MarkdownFlowTrace(
        name="learn/Course/Chapter/Lesson",
        user_id="learner-1",
        input=kwargs.pop("input", {"goal": ["Learn to build"]}),
        metadata={"scene": "learn", "shifu_bid": "course-1"},
        **kwargs,
    )


def _spans(exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    return {span.name: span for span in exporter.get_finished_spans()}


def _value(span: ReadableSpan, key: str) -> object:
    value = span.attributes[f"langfuse.observation.{key}"]
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def test_request_tree_preserves_answer_context_and_typed_operations(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    trace.set_context(
        session_id="native-session-1",
        script="The effective session script.",
        teaching_brief="Ask one concrete question.",
        metadata={"content_revision": 7},
    )
    turn = trace.start_turn(metadata={"turn_index": 3})
    generation = turn.generation(
        name="teach",
        input=[{"role": "user", "content": "Learn to build"}],
        model="test-model",
    )
    generation.end(output="Choose a project.", usage_details={"input": 12, "output": 4})
    trace.event(ToolCall(id="recall-1", name="recall", args={"query": "goals"}))
    trace.event(ToolResult(id="recall-1", name="recall", content={"found": True}))
    trace.append_output("Choose a project.\n")
    trace.append_output("[Build a dashboard]")
    trace.complete_turn("interaction")
    trace.finish()

    spans = _spans(observations)
    root = spans["learn/Course/Chapter/Lesson"]
    assert _value(root, "input") == {"goal": ["Learn to build"]}
    assert _value(root, "output") == "Choose a project.\n[Build a dashboard]"
    assert _value(spans["context"], "input") == {
        "script": "The effective session script.",
        "teaching_brief": "Ask one concrete question.",
    }
    assert spans["context"].parent.span_id == root.context.span_id
    assert spans["turn"].parent.span_id == root.context.span_id
    assert spans["turn"].attributes["langfuse.observation.type"] == "agent"
    for name, kind in (("teach", "generation"), ("recall", "tool")):
        assert spans[name].parent.span_id == spans["turn"].context.span_id
        assert spans[name].attributes["langfuse.observation.type"] == kind
    assert _value(spans["recall"], "output") == {"found": True}
    assert spans["teach"].attributes["langfuse.observation.model.name"] == "test-model"
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"]
        == "interaction"
    )
    assert all(
        span.context.trace_id == root.context.trace_id for span in spans.values()
    )
    for span in spans.values():
        assert span.attributes["session.id"] == "native-session-1"
        assert span.attributes["user.id"] == "learner-1"
        assert span.attributes["langfuse.trace.metadata.scene"] == "learn"
        assert "langfuse.trace.metadata.script" not in span.attributes
        assert "langfuse.trace.metadata.teaching_brief" not in span.attributes


def test_late_session_binding_reaches_root_existing_turn_and_future_children(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace(input={"action": "start"})
    turn = trace.start_turn()
    trace.set_context(session_id="restored-session", script="Original saved script.")
    trace.set_input({"action": "continue"})
    turn.generation(name="teach").end(output="Continue from the saved script.")
    trace.complete_turn("finished")
    trace.finish()

    spans = _spans(observations)
    assert _value(spans["learn/Course/Chapter/Lesson"], "input") == {
        "action": "continue"
    }
    assert all(
        span.attributes["session.id"] == "restored-session" for span in spans.values()
    )


def test_late_session_binding_reaches_a_turn_without_a_generation(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace(input={"action": "continue"})
    trace.start_turn()
    trace.set_context(session_id="restored-session", script="Saved session script.")
    trace.complete_turn("interaction")
    trace.finish()

    spans = _spans(observations)
    assert "teach" not in spans
    for name in ("learn/Course/Chapter/Lesson", "turn", "context"):
        assert spans[name].attributes["session.id"] == "restored-session"


def test_memory_updates_close_only_the_corresponding_model_tool_call(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    trace.start_turn()
    for call_id, key in (("note-goal", "goal"), ("note-pace", "pace")):
        trace.event(
            ToolCall(
                id=call_id,
                name="remember",
                args={"key": key, "value": "model note"},
            )
        )

    trace.event(
        MemoryUpdated(key="goal", value="accepted answer", source="interaction")
    )
    assert not [
        span for span in observations.get_finished_spans() if span.name == "remember"
    ]

    trace.event(MemoryUpdated(key="goal", value="accepted goal", source="tool"))
    notes = [
        span for span in observations.get_finished_spans() if span.name == "remember"
    ]
    assert len(notes) == 1
    assert (
        notes[0].attributes["langfuse.observation.metadata.tool_call_id"] == "note-goal"
    )
    assert _value(notes[0], "output") == {
        "key": "goal",
        "value": "accepted goal",
        "status": "staged",
    }

    trace.event(MemoryUpdated(key="pace", value="accepted pace", source="tool"))
    trace.event(TurnDone(reason="interaction"))
    trace.complete_turn("interaction")
    trace.finish()
    notes = [
        span for span in observations.get_finished_spans() if span.name == "remember"
    ]
    assert len(notes) == 2
    assert {
        span.attributes["langfuse.observation.metadata.tool_call_id"] for span in notes
    } == {"note-goal", "note-pace"}
    assert all(
        span.attributes["langfuse.observation.metadata.outcome"] == "staged"
        for span in notes
    )


@pytest.mark.parametrize("reason", ["interaction", "finished"])
def test_unreported_memory_result_does_not_claim_success(
    observations: InMemorySpanExporter, reason: str
) -> None:
    trace = _trace()
    trace.start_turn()
    trace.event(
        ToolCall(
            id="refused-note", name="remember", args={"key": "goal", "value": "note"}
        )
    )
    trace.event(
        MemoryUpdated(key="goal", value="accepted answer", source="interaction")
    )
    trace.event(TurnDone(reason=reason))
    trace.complete_turn(reason)
    trace.finish()

    note = _spans(observations)["remember"]
    assert _value(note, "output") == {"status": "result_unavailable"}
    assert (
        note.attributes["langfuse.observation.metadata.outcome"] == "result_unavailable"
    )


@pytest.mark.parametrize("reason", ["interaction", "finished"])
def test_tools_without_results_are_closed_at_the_host_turn_boundary(
    observations: InMemorySpanExporter, reason: str
) -> None:
    trace = _trace()
    trace.start_turn()
    trace.event(
        ToolCall(
            id="remember-1", name="remember", args={"key": "goal", "value": "build"}
        )
    )
    trace.event(MemoryUpdated(key="goal", value="build", scope="user"))
    trace.event(ToolCall(id="finish-1", name="finish", args={"summary": "Done"}))
    trace.event(ToolCall(id="interact-1", name="interact", args={"prompt": "Next?"}))
    trace.event(TurnDone(reason=reason))
    trace.complete_turn(reason)
    trace.finish()

    spans = _spans(observations)
    for name in ("remember", "finish", "interact"):
        assert spans[name].end_time is not None
        assert spans[name].attributes["langfuse.observation.type"] == "tool"
    expected = "waiting" if reason == "interaction" else "finished"
    assert _value(spans["interact"], "output") == {"status": expected}
    assert _value(spans["memory"], "output") == {"value": "build", "status": "staged"}


@pytest.mark.parametrize("outcome", ["discarded", "error"])
def test_unresolved_tool_waits_for_the_authoritative_host_outcome(
    observations: InMemorySpanExporter, outcome: str
) -> None:
    trace = _trace()
    trace.start_turn()
    trace.event(ToolCall(id="recall-1", name="recall", args={"query": "goal"}))
    trace.event(ToolResult(id="recall-1", name="recall", content={"goal": "build"}))
    trace.event(
        ToolCall(id="note-1", name="remember", args={"key": "pace", "value": "slow"})
    )
    trace.event(MemoryUpdated(key="pace", value="slow", source="tool"))
    trace.event(ToolCall(id="question-1", name="interact", args={"prompt": "Next?"}))
    trace.event(
        InteractionRequest(
            id="question-1", spec=InteractionSpec(type="confirm", prompt="Next?")
        )
    )
    trace.event(ToolCall(id="finish-1", name="finish", args={"summary": "Done"}))
    trace.event(TurnDone(reason="finished"))

    # A native terminal event precedes the host's persistence decision. It cannot
    # turn a rejected or failed save into a successful tool observation.
    assert "finish" not in _spans(observations)
    trace.complete_turn(outcome)
    trace.finish()

    spans = _spans(observations)
    assert _value(spans["finish"], "output") == {"status": outcome}
    assert (
        spans["finish"].attributes["langfuse.observation.metadata.outcome"] == outcome
    )
    assert _value(spans["recall"], "output") == {"goal": "build"}
    assert (
        spans["recall"].attributes["langfuse.observation.metadata.outcome"]
        == "completed"
    )
    assert _value(spans["interact"], "output")["prompt"] == "Next?"
    assert (
        spans["interact"].attributes["langfuse.observation.metadata.outcome"]
        == "waiting"
    )
    assert _value(spans["remember"], "output") == {
        "key": "pace",
        "value": "slow",
        "status": "staged",
    }
    assert (
        spans["remember"].attributes["langfuse.observation.metadata.outcome"]
        == "staged"
    )


def test_interaction_tool_captures_the_question_without_polluting_root_output(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    trace.start_turn()
    trace.event(
        ToolCall(
            id="question-1",
            name="interact",
            args={"type": "text", "prompt": "What is your goal?"},
        )
    )
    trace.event(
        InteractionRequest(
            id="question-1",
            spec=InteractionSpec(type="text", prompt="What is your goal?"),
        )
    )
    trace.append_output("What is your goal?\n[Text input]")
    trace.complete_turn("interaction")
    trace.finish()

    spans = _spans(observations)
    assert _value(spans["interact"], "output")["prompt"] == "What is your goal?"
    assert (
        spans["interact"].attributes["langfuse.observation.metadata.outcome"]
        == "waiting"
    )
    assert (
        _value(spans["learn/Course/Chapter/Lesson"], "output")
        == "What is your goal?\n[Text input]"
    )


def test_retryable_rejection_followed_by_waiting_is_not_a_request_failure(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    trace.start_turn()
    trace.event(ErrorEvent(message="Please answer the question.", retryable=True))
    trace.event(TurnDone(reason="interaction"))
    trace.complete_turn("interaction")
    trace.finish(transport_closed=True)

    spans = _spans(observations)
    root = spans["learn/Course/Chapter/Lesson"]
    assert spans["error"].attributes["langfuse.observation.level"] == "WARNING"
    assert root.attributes["langfuse.observation.level"] == "DEFAULT"
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"]
        == "interaction"
    )
    assert root.attributes["langfuse.observation.metadata.end_reason"] == "completed"


@pytest.mark.parametrize("outcome", ["interaction", "finished", "completed"])
def test_transport_closing_after_committed_terminal_keeps_success(
    observations: InMemorySpanExporter, outcome: str
) -> None:
    trace = _trace()
    trace.start_turn()
    trace.append_output("The final displayed response.")
    trace.complete_turn(outcome)
    trace.finish(transport_closed=True)
    trace.finish("error")

    spans = observations.get_finished_spans()
    root = _spans(observations)["learn/Course/Chapter/Lesson"]
    assert len(spans) == 2
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == outcome
    assert root.attributes["langfuse.observation.metadata.end_reason"] == "completed"
    assert root.attributes["langfuse.observation.metadata.transport_closed"] is True
    assert _value(root, "output") == "The final displayed response."


def test_midstream_disconnect_keeps_partial_output_and_closes_open_tools(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    trace.start_turn()
    trace.event(ToolCall(id="slow-recall", name="recall", args={"query": "context"}))
    trace.append_output("Partial displayed response")
    trace.finish(transport_closed=True)

    spans = _spans(observations)
    root = spans["learn/Course/Chapter/Lesson"]
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"]
        == "disconnected"
    )
    assert root.attributes["langfuse.observation.metadata.end_reason"] == "disconnected"
    assert _value(root, "output") == "Partial displayed response"
    assert _value(spans["turn"], "output") == "Partial displayed response"
    assert _value(spans["recall"], "output") == {"status": "disconnected"}


def test_auto_continuation_has_separate_turns_and_one_aggregated_root(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    trace.start_turn(metadata={"turn_index": 1})
    trace.append_output("First part.\n")
    trace.complete_turn("end")
    trace.start_turn(metadata={"turn_index": 2})
    trace.append_output("Second part.")
    trace.complete_turn("finished")
    trace.finish()

    spans = observations.get_finished_spans()
    turns = [span for span in spans if span.name == "turn"]
    assert len(turns) == 2
    assert [_value(span, "output") for span in turns] == [
        "First part.\n",
        "Second part.",
    ]
    assert (
        _value(_spans(observations)["learn/Course/Chapter/Lesson"], "output")
        == "First part.\nSecond part."
    )


def test_model_parent_proxy_reuses_models_without_reparenting_existing_generations(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    model_parent = trace.model_parent
    trace.start_turn(metadata={"turn_index": 1})
    first_generation = model_parent.generation(
        name="teach", input="First model request", model="test-model"
    )
    model_parent.generation(name="summary", input="First auxiliary request").end(
        output="First auxiliary response"
    )
    trace.append_output("First part.\n")
    trace.complete_turn("end")
    trace.start_turn(metadata={"turn_index": 2})
    assert trace.model_parent is model_parent
    model_parent.generation(name="teach", input="Second model request").end(
        output="Second response"
    )
    model_parent.generation(name="summary", input="Second auxiliary request").end(
        output="Second auxiliary response"
    )
    # Finishing an older generation after an automatic continuation must update
    # its original observation, rather than follow the model-parent proxy.
    first_generation.end(
        output="First response", usage_details={"input": 2, "output": 3}
    )
    trace.append_output("Second part.")
    trace.complete_turn("finished")
    trace.finish()

    spans = observations.get_finished_spans()
    roots = [span for span in spans if span.name == "learn/Course/Chapter/Lesson"]
    turns = [span for span in spans if span.name == "turn"]
    generations = [
        span
        for span in spans
        if span.attributes.get("langfuse.observation.type") == "generation"
    ]
    assert len(roots) == 1
    assert len(turns) == 2
    assert len(generations) == 4
    parents = {
        span.attributes[
            "langfuse.observation.metadata.turn_index"
        ]: span.context.span_id
        for span in turns
    }
    for generation in generations:
        turn_index = 1 if str(_value(generation, "input")).startswith("First") else 2
        assert generation.parent.span_id == parents[turn_index]
    first = next(
        span for span in generations if _value(span, "input") == "First model request"
    )
    assert _value(first, "output") == "First response"
    assert roots[0].context.trace_id == first.context.trace_id


def test_request_scope_returns_itself_and_finishes_a_normal_request(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    with trace as active:
        assert active is trace
        active.start_turn()
        active.append_output("Normal response")

    spans = _spans(observations)
    root = spans["learn/Course/Chapter/Lesson"]
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"] == "completed"
    )
    assert _value(root, "output") == "Normal response"
    assert spans["turn"].end_time is not None


@pytest.mark.parametrize("outcome", ["waiting", "completed"])
def test_request_scope_preserves_committed_terminal_when_consumer_closes(
    observations: InMemorySpanExporter, outcome: str
) -> None:
    trace = _trace()

    def request() -> None:
        with trace:
            trace.start_turn()
            trace.append_output("Committed public response")
            trace.complete_turn(outcome)
            raise GeneratorExit

    with pytest.raises(GeneratorExit):
        request()

    root = _spans(observations)["learn/Course/Chapter/Lesson"]
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == outcome
    assert root.attributes["langfuse.observation.metadata.end_reason"] == "completed"
    assert root.attributes["langfuse.observation.metadata.transport_closed"] is True
    assert _value(root, "output") == "Committed public response"


def test_request_scope_records_an_active_disconnect_without_suppressing_it(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()

    def request() -> None:
        with trace:
            trace.start_turn()
            trace.event(
                ToolCall(id="recall-active", name="recall", args={"query": "goal"})
            )
            trace.append_output("Partial response")
            raise GeneratorExit

    with pytest.raises(GeneratorExit):
        request()

    spans = _spans(observations)
    root = spans["learn/Course/Chapter/Lesson"]
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"]
        == "disconnected"
    )
    assert _value(root, "output") == "Partial response"
    assert _value(spans["recall"], "output") == {"status": "disconnected"}


def test_request_scope_keeps_a_saved_discarded_outcome_and_domain_exception(
    observations: InMemorySpanExporter,
) -> None:
    class DiscardedTurnError(RuntimeError):
        """The host rejected this turn before publication."""

    error = DiscardedTurnError("The session was reset")
    trace = _trace()

    def request() -> None:
        with trace:
            trace.start_turn()
            trace.complete_turn("discarded")
            raise error

    with pytest.raises(DiscardedTurnError) as caught:
        request()

    assert caught.value is error
    root = _spans(observations)["learn/Course/Chapter/Lesson"]
    assert (
        root.attributes["langfuse.observation.metadata.runtime_outcome"] == "discarded"
    )
    assert _spans(observations)["turn"].end_time is not None


def test_request_scope_closes_observations_and_propagates_runtime_exceptions(
    observations: InMemorySpanExporter,
) -> None:
    error = RuntimeError("Business persistence failed")
    trace = _trace()

    def request() -> None:
        with trace:
            trace.start_turn()
            trace.event(
                ToolCall(id="finish-1", name="finish", args={"summary": "Done"})
            )
            trace.append_output("Partial response")
            raise error

    with pytest.raises(RuntimeError) as caught:
        request()

    assert caught.value is error
    spans = _spans(observations)
    root = spans["learn/Course/Chapter/Lesson"]
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == "error"
    assert root.attributes["langfuse.observation.level"] == "ERROR"
    assert _value(spans["finish"], "output") == {"status": "error"}
    assert spans["turn"].end_time is not None


def test_context_is_recorded_once_per_effective_session_snapshot(
    observations: InMemorySpanExporter,
) -> None:
    trace = _trace()
    trace.set_context(session_id="native-session", script="Original.")
    trace.set_context(session_id="native-session", script="Original.")
    trace.set_context(session_id="native-session", script="Edited debug draft.")
    trace.finish()
    contexts = [
        span for span in observations.get_finished_spans() if span.name == "context"
    ]
    assert [_value(span, "input")["script"] for span in contexts] == [
        "Original.",
        "Edited debug draft.",
    ]


@pytest.mark.parametrize(
    "operation", ["create", "update", "end", "generation", "observation"]
)
def test_sdk_failures_do_not_escape_into_the_host(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    failure = RuntimeError("Telemetry is unavailable")
    trace_handle = Mock()
    root_handle = Mock()
    turn_handle = Mock()
    root_handle.observation.return_value = turn_handle
    if operation == "create":
        monkeypatch.setattr(
            tracing, "create_trace_with_root_span", Mock(side_effect=failure)
        )
    else:
        monkeypatch.setattr(
            tracing,
            "create_trace_with_root_span",
            Mock(return_value=(trace_handle, root_handle)),
        )
        getattr(trace_handle, operation).side_effect = failure
        getattr(root_handle, operation).side_effect = failure
        getattr(turn_handle, operation).side_effect = failure
    trace = _trace()
    trace.set_context(session_id="session", script="Effective script")
    turn = trace.start_turn()
    generation = turn.generation(name="teach")
    generation.update(output="Response")
    generation.end(output="Response")
    trace.event(ToolCall(id="recall", name="recall", args={}))
    trace.event(ToolResult(id="recall", name="recall", content="Found"))
    trace.append_output("Response")
    trace.complete_turn("finished")
    trace.finish()
    trace.finish()


def test_safe_observation_ends_only_once_when_the_sdk_raises() -> None:
    sdk = Mock()
    sdk.end.side_effect = RuntimeError("Exporter is unavailable")
    handle = tracing.SafeObservation(sdk)
    handle.end(output="Result")
    handle.end(output="Result")
    sdk.end.assert_called_once_with(output="Result")

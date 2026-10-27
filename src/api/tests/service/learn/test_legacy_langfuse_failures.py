"""Keep pre-session learning failures observable without changing error handling."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.api import langfuse as langfuse_module
from flaskr.api.langfuse import coerce_langfuse_trace_id, get_session_trace_id
from flaskr.service.learn import context_v2 as context_module
from flaskr.service.learn import runscript_v2 as run
from flaskr.service.learn.context_v2 import RunScriptContextV2
from flaskr.service.shifu.shifu_history_manager import HistoryItem

from tests import test_langfuse_v4_semantics as sdk_tests

captured_spans = sdk_tests.captured_spans


@pytest.fixture
def execution(monkeypatch: pytest.MonkeyPatch, captured_spans: object) -> object:
    """Run the real context and outer error handler without external services."""
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(context_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(context_module, "get_request_id", lambda: "failed-request")
    monkeypatch.setattr(langfuse_module, "get_request_id", lambda: "failed-request")
    app = Flask(__name__)
    course = SimpleNamespace(bid="course", price=0)
    outline = SimpleNamespace(
        bid="lesson", shifu_bid="course", title="Lesson", __json__=dict
    )
    struct = HistoryItem(bid="lesson", id=1, type="outline", children=[])
    user = SimpleNamespace(user_id="learner")
    context = RunScriptContextV2(
        app=app,
        shifu_info=course,
        struct=struct,
        outline_item_info=outline,
        user_info=user,
        is_paid=True,
        preview_mode=False,
    )
    error = LookupError("progress storage failed")
    monkeypatch.setattr(context, "_get_current_attend", Mock(side_effect=error))

    class Context:
        def __new__(cls, **_kwargs: object) -> RunScriptContextV2:
            return context

    monkeypatch.setattr(run, "RunScriptContextV2", Context)
    monkeypatch.setattr(run, "_ensure_healthy_db_connection", Mock())
    monkeypatch.setattr(run, "load_user_aggregate", lambda _: user)
    monkeypatch.setattr(run, "get_shifu_dto", lambda *_: course)
    monkeypatch.setattr(run, "get_outline_item_dto", lambda *_: outline)
    monkeypatch.setattr(run, "get_shifu_struct", lambda *_: struct)
    session, remove, commit = Mock(), Mock(), Mock()
    monkeypatch.setattr(run, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(run, "_remove_db_session_safely", remove)
    monkeypatch.setattr(run, "_commit_pending_step", commit)
    return SimpleNamespace(
        app=app,
        context=context,
        exporter=exporter,
        error=error,
        session=session,
        remove=remove,
        commit=commit,
    )


def _run(execution: object) -> None:
    """Drive the outer stream through its progress lookup and cleanup."""
    list(
        run.run_script_inner(
            execution.app,
            user_bid="learner",
            shifu_bid="course",
            outline_bid="lesson",
            user_input="Current answer",
            input_type="text",
            manage_app_context=False,
        )
    )


def test_progress_failure_exports_one_request_error_and_preserves_original_exception(
    execution: object,
) -> None:
    """Export an error root even when no progress session could be selected."""
    with pytest.raises(LookupError) as caught:
        _run(execution)
    assert caught.value is execution.error
    execution.context._finalize_langfuse_trace(error=execution.error)
    spans = execution.exporter.get_finished_spans()
    assert len(spans) == 1
    root = spans[0]
    assert root.context.trace_id == int(coerce_langfuse_trace_id("failed-request"), 16)
    assert root.attributes["langfuse.observation.input"] == "Current answer"
    assert root.attributes["langfuse.trace.metadata.request_id"] == "failed-request"
    assert root.attributes["langfuse.observation.level"] == "ERROR"
    assert root.attributes["langfuse.observation.status_message"] == "LookupError"
    assert root.attributes["langfuse.observation.metadata.runtime_outcome"] == "error"
    assert "session.id" not in root.attributes
    execution.session.rollback.assert_called_once()
    execution.remove.assert_called_once()
    execution.commit.assert_not_called()


def test_bound_session_error_ends_its_session_root_without_creating_fallback(
    execution: object,
) -> None:
    """Keep a failed resolved session in its deterministic trace."""
    context = execution.context
    context._current_attend = SimpleNamespace(progress_record_bid="progress")
    context._bind_trace_session()
    context._finalize_langfuse_trace(error=execution.error)
    context._finalize_langfuse_trace(error=execution.error)
    spans = execution.exporter.get_finished_spans()
    assert len(spans) == 1
    root = spans[0]
    assert root.context.trace_id == int(
        get_session_trace_id("progress", user_id="learner"), 16
    )
    assert root.attributes["session.id"] == "progress"
    assert root.attributes["langfuse.observation.level"] == "ERROR"


def test_failed_session_rollover_retains_old_root_and_falls_back_under_new_session(
    execution: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replacement SDK failure must never update or end the old root again."""
    context = execution.context
    real_create = context_module.create_trace_with_root_span
    telemetry_error = RuntimeError("replacement trace unavailable")

    def create_root(**kwargs: object) -> object:
        if create.call_count == 2:
            raise telemetry_error
        return real_create(**kwargs)

    create = Mock(side_effect=create_root)
    monkeypatch.setattr(context_module, "create_trace_with_root_span", create)
    context._current_attend = SimpleNamespace(progress_record_bid="first-progress")
    context._bind_trace_session()
    first_root = context._trace_root_span
    first_update = Mock(wraps=context._trace.update)
    first_end = Mock(wraps=first_root.end)
    monkeypatch.setattr(context._trace, "update", first_update)
    monkeypatch.setattr(first_root, "end", first_end)
    context.append_langfuse_output("First session output")
    context._current_attend = SimpleNamespace(progress_record_bid="next-progress")

    with pytest.raises(RuntimeError) as caught:
        context._bind_trace_session()
    assert caught.value is telemetry_error
    assert context._trace_root_span is None
    context._finalize_langfuse_trace(error=caught.value)
    context._finalize_langfuse_trace(error=caught.value)

    assert create.call_count == 3
    first_update.assert_called_once()
    first_end.assert_called_once()
    roots = execution.exporter.get_finished_spans()
    assert len(roots) == 2
    first, replacement = roots
    assert first.context.trace_id == int(
        get_session_trace_id("first-progress", user_id="learner"), 16
    )
    assert first.attributes["session.id"] == "first-progress"
    assert first.attributes["langfuse.observation.output"] == "First session output"
    assert "langfuse.observation.metadata.runtime_outcome" not in first.attributes
    assert first.attributes.get("langfuse.observation.level") != "ERROR"
    assert replacement.context.trace_id == int(
        get_session_trace_id("next-progress", user_id="learner"), 16
    )
    assert replacement.attributes["session.id"] == "next-progress"
    assert replacement.attributes["langfuse.observation.level"] == "ERROR"
    assert (
        replacement.attributes["langfuse.observation.status_message"] == "RuntimeError"
    )
    assert "langfuse.observation.output" not in replacement.attributes


def test_progress_failure_retains_captured_request_identity_during_late_cleanup(
    execution: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use the request captured at entry even if ambient request state changes."""
    monkeypatch.setattr(langfuse_module, "get_request_id", lambda: "another-request")
    monkeypatch.setattr(context_module, "get_request_id", lambda: "another-request")
    with pytest.raises(LookupError) as caught:
        _run(execution)
    assert caught.value is execution.error
    root = execution.exporter.get_finished_spans()[0]
    assert root.context.trace_id == int(coerce_langfuse_trace_id("failed-request"), 16)
    assert root.attributes["langfuse.trace.metadata.request_id"] == "failed-request"


@pytest.mark.parametrize("operation", ["create", "update", "end"])
def test_fallback_sdk_failure_preserves_business_error_and_database_cleanup(
    execution: object, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """Optional telemetry must not replace the progress failure or skip cleanup."""
    telemetry_error = RuntimeError("telemetry unavailable")
    trace, root = Mock(), Mock()
    create = Mock(return_value=(trace, root))
    if operation == "create":
        create.side_effect = telemetry_error
    elif operation == "update":
        trace.update.side_effect = telemetry_error
    else:
        root.end.side_effect = telemetry_error
    monkeypatch.setattr(context_module, "create_trace_with_root_span", create)
    with pytest.raises(LookupError) as caught:
        _run(execution)
    assert caught.value is execution.error
    execution.context._finalize_langfuse_trace(error=execution.error)
    create.assert_called_once()
    if operation == "update":
        trace.update.assert_called_once()
    elif operation == "end":
        root.end.assert_called_once()
    execution.session.rollback.assert_called_once()
    execution.remove.assert_called_once()
    execution.commit.assert_not_called()

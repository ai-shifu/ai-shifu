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
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO
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


def _run(execution: object) -> list[object]:
    """Drive the outer stream through its progress lookup and cleanup."""
    return list(
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


def _resume_learning(
    execution: object,
    monkeypatch: pytest.MonkeyPatch,
    *,
    rollover: bool,
    business_error: Exception | None = None,
) -> object:
    """Drive run_inner and its real streaming provider without database writes."""
    context = execution.context
    first_update, first_end = None, None
    if rollover:
        context._current_attend = SimpleNamespace(progress_record_bid="first-progress")
        context._bind_trace_session()
        first_update = Mock(wraps=context._trace.update)
        first_end = Mock(wraps=context._trace_root_span.end)
        monkeypatch.setattr(context._trace, "update", first_update)
        monkeypatch.setattr(context._trace_root_span, "end", first_end)
        context.append_langfuse_output("First session output")
    progress = SimpleNamespace(
        progress_record_bid="next-progress", block_position=0, status=1
    )
    monkeypatch.setattr(context, "_get_current_attend", Mock(return_value=progress))

    def synchronize(_app: object) -> object:
        yield from ()
        return True

    monkeypatch.setattr(context, "_phase_sync_outline_progress", synchronize)
    monkeypatch.setattr(
        context,
        "_get_run_script_info",
        Mock(return_value=SimpleNamespace(outline_bid="lesson", block_position=0)),
    )
    settings = context_module.LLMSettings(model="1", temperature=0.2)
    usage = context_module.UsageContext(
        user_bid="learner", shifu_bid="course", progress_record_bid="next-progress"
    )
    monkeypatch.setattr(context, "get_llm_settings", Mock(return_value=settings))
    monkeypatch.setattr(
        context, "get_system_prompt", Mock(return_value="Teach clearly.")
    )
    monkeypatch.setattr(
        context,
        "_prepare_step_state",
        Mock(return_value=SimpleNamespace(block_list=["Lesson script"])),
    )

    def chat(_app: object, _user: object, parent: object, **kwargs: object) -> object:
        # A no-op root still needs all observation methods and a real trace id
        # for the unchanged provider, interaction, ask, and billing paths.
        context._bind_trace_session()
        expected_id = get_session_trace_id("next-progress", user_id="learner")
        assert parent.trace_id == expected_id
        assert kwargs["usage_context"] is usage
        assert kwargs["stream"] is True
        for observation in (
            parent.generation(name="teaching"),
            parent.span(name="ask"),
            parent.event(name="interaction"),
        ):
            assert observation.trace_id == expected_id
            assert isinstance(observation.id, str)
            observation.end(output="Model result")
        if business_error is not None:
            raise business_error
        yield SimpleNamespace(result="Lesson response")

    gateway = Mock(side_effect=chat)
    monkeypatch.setattr(context_module, "chat_llm", gateway)

    def teach(app: Flask, _state: object) -> object:
        provider = context_module.RUNLLMProvider(
            app,
            settings,
            context._trace,
            context._trace_root_span,
            context._trace_args,
            usage,
            context_module.BILL_USAGE_SCENE_PROD,
        )
        output = "".join(provider.stream([{"role": "user", "content": "Question"}]))
        context.append_langfuse_output(output)
        context._can_continue = False
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="block",
            type=GeneratedType.CONTENT,
            content=output,
        )
        return True

    monkeypatch.setattr(context, "_phase_process_input", teach)
    create = Mock(side_effect=RuntimeError("trace unavailable"))
    monkeypatch.setattr(context_module, "create_trace_with_root_span", create)
    return SimpleNamespace(
        create=create, gateway=gateway, first_update=first_update, first_end=first_end
    )


@pytest.mark.parametrize("rollover", [False, True])
def test_trace_creation_failure_keeps_learning_stream_and_successful_outer_cleanup(
    execution: object, monkeypatch: pytest.MonkeyPatch, rollover: bool
) -> None:
    """A tracing outage cannot abort an initial or automatically advanced lesson."""
    calls = _resume_learning(execution, monkeypatch, rollover=rollover)
    assert [event.content for event in _run(execution)] == ["Lesson response"]
    calls.create.assert_called_once()
    calls.gateway.assert_called_once()
    execution.session.rollback.assert_not_called()
    execution.commit.assert_called_once()
    execution.remove.assert_called_once()
    roots = execution.exporter.get_finished_spans()
    assert len(roots) == int(rollover)
    if rollover:
        calls.first_update.assert_called_once()
        calls.first_end.assert_called_once()
        first = roots[0]
        assert first.attributes["session.id"] == "first-progress"
        assert first.attributes["langfuse.observation.output"] == "First session output"
        assert first.attributes.get("langfuse.observation.level") != "ERROR"


@pytest.mark.parametrize("rollover", [False, True])
def test_business_error_after_trace_outage_still_propagates_and_rolls_back(
    execution: object, monkeypatch: pytest.MonkeyPatch, rollover: bool
) -> None:
    """Only the optional trace failure is ignored; real model failures still fail."""
    calls = _resume_learning(
        execution, monkeypatch, rollover=rollover, business_error=execution.error
    )
    with pytest.raises(LookupError) as caught:
        _run(execution)
    assert caught.value is execution.error
    calls.create.assert_called_once()
    calls.gateway.assert_called_once()
    execution.session.rollback.assert_called_once()
    execution.commit.assert_not_called()
    execution.remove.assert_called_once()
    if rollover:
        calls.first_update.assert_called_once()
        calls.first_end.assert_called_once()
        first = execution.exporter.get_finished_spans()[0]
        assert first.attributes["session.id"] == "first-progress"
        assert first.attributes.get("langfuse.observation.level") != "ERROR"


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

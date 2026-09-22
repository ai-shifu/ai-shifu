"""Check provider and stream failures leave the run available for recovery."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.learn import context_v2 as runtime
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.metering import UsageContext

from . import test_input_dispatch_storage as input_storage

dispatch = input_storage.dispatch


@pytest.mark.parametrize("stream", [True, False])
def test_provider_rejects_empty_messages_before_calling_gateway(
    monkeypatch: pytest.MonkeyPatch,
    stream: bool,
) -> None:
    gateway = Mock()
    monkeypatch.setattr(runtime, "chat_llm", gateway)
    provider = runtime.RUNLLMProvider(
        Flask("empty-provider"),
        LLMSettings(model="1", temperature=0.2),
        None,
        None,
        {},
        UsageContext(),
        runtime.BILL_USAGE_SCENE_PREVIEW,
    )
    with pytest.raises(ValueError, match="No messages provided"):
        list(provider.stream([])) if stream else provider.complete([])
    gateway.assert_not_called()


@pytest.mark.parametrize("stream", [True, False])
def test_corrupt_trace_metadata_does_not_drop_model_output_or_usage_context(
    monkeypatch: pytest.MonkeyPatch,
    stream: bool,
) -> None:
    usage = UsageContext(user_bid="learner", shifu_bid="course")
    settings = LLMSettings(
        model="1", temperature=0.2, usage_metadata={"selected_model": "1"}
    )
    gateway = Mock(
        return_value=iter(
            [SimpleNamespace(result=""), SimpleNamespace(result="answer")]
        )
    )
    monkeypatch.setattr(runtime, "chat_llm", gateway)
    provider = runtime.RUNLLMProvider(
        Flask("legacy-trace"),
        settings,
        None,
        None,
        {"user_id": "learner", "metadata": "legacy"},
        usage,
        runtime.BILL_USAGE_SCENE_PREVIEW,
    )
    output = (
        "".join(provider.stream([{"role": "user", "content": "question"}]))
        if stream
        else provider.complete([{"role": "user", "content": "question"}])
    )
    assert output == "answer"
    assert gateway.call_args.kwargs["usage_context"] is usage
    assert gateway.call_args.kwargs["usage_metadata"] == settings.usage_metadata
    assert gateway.call_args.kwargs["model"] == "1"
    assert gateway.call_args.kwargs["stream"] is stream


def test_threaded_provider_error_reaches_consumer_and_releases_producer_session(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = runtime.RunScriptContextV2.__new__(runtime.RunScriptContextV2)
    context.app = app
    context._stop_event = threading.Event()
    error = RuntimeError("provider disconnected")
    invalidation = Mock()
    monkeypatch.setattr(runtime, "invalidate_session", invalidation)
    closed = threading.Event()

    def provider() -> object:
        try:
            yield "partial"
            raise error
        finally:
            closed.set()

    stream = context._iter_stream_result_with_idle_callback(provider())
    assert next(stream) == ("item", "partial")
    with pytest.raises(RuntimeError, match="provider disconnected") as caught:
        next(stream)
    assert caught.value is error
    assert closed.is_set()
    invalidation.assert_called_once_with(source="mdflow stream producer abort")
    assert not any(
        thread.name == "mdflow_stream_result_producer" and thread.is_alive()
        for thread in threading.enumerate()
    )


def test_failed_content_flush_still_finalizes_audio_and_advances_element_cursor(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = runtime.RunScriptContextV2.__new__(runtime.RunScriptContextV2)
    context.app = app
    context._element_index_cursor = 3
    error = RuntimeError("cache unavailable")
    cleanup = Mock()
    monkeypatch.setattr(runtime, "cleanup_session_after", cleanup)
    processor = SimpleNamespace(
        next_element_index=7, finalize=Mock(return_value=iter(["audio-complete"]))
    )
    flush = Mock(side_effect=error)
    assert list(
        context._teardown_stream_tts_state(
            tts_processor=processor, flush_content_cache=flush, log_prefix="finalize"
        )
    ) == ["audio-complete"]
    cleanup.assert_called_once_with(error, source="flush streaming content cache")
    processor.finalize.assert_called_once_with(commit=False)
    assert context._element_index_cursor == 7
    assert list(context._finalize_stream_tts_processor(None, log_prefix="absent")) == []


@pytest.mark.parametrize("next_lesson", [True, False])
def test_exhausted_script_never_invokes_model_and_emits_available_next_lesson(
    dispatch: object,
    next_lesson: bool,
) -> None:
    context, state = dispatch.context, dispatch.state
    context._input_type = ""
    context._get_current_attend = Mock(return_value=context._current_attend)
    context._bind_trace_session = Mock()

    def synchronize(_app: object) -> object:
        yield "progress"
        return True

    context._phase_sync_outline_progress = synchronize
    state.run_script_info.block_position = len(state.block_list)
    context._get_run_script_info = Mock(return_value=state.run_script_info)
    context.get_llm_settings = Mock(return_value=state.llm_settings)
    context.get_system_prompt = Mock(return_value=None)
    context._prepare_step_state = Mock(return_value=state)
    context._get_next_outline_item = Mock(return_value=["next"] if next_lesson else [])
    context._render_outline_updates = Mock(return_value=iter(["next-lesson"]))
    assert list(context.run_inner(dispatch.app)) == [
        "progress",
        *(["next-lesson"] if next_lesson else []),
    ]
    assert context._can_continue is (not next_lesson)
    if next_lesson:
        context._render_outline_updates.assert_called_once_with(
            ["next"], new_chapter=True
        )
    else:
        context._render_outline_updates.assert_not_called()
    state.mdflow_context.process.assert_not_called()


@pytest.mark.parametrize("stage", ["sync", "missing-script"])
def test_terminal_run_phase_stops_before_resolving_model_settings(
    dispatch: object,
    stage: str,
) -> None:
    context = dispatch.context
    context._input_type = ""
    context._get_current_attend = Mock(return_value=context._current_attend)
    context._bind_trace_session = Mock()

    def synchronize(_app: object) -> object:
        yield "progress"
        return stage != "sync"

    context._phase_sync_outline_progress = synchronize
    context._get_run_script_info = Mock(return_value=None)
    context._phase_completion_when_script_missing = Mock(
        return_value=iter(["completed"])
    )
    context.get_llm_settings = Mock()
    assert list(context.run_inner(dispatch.app)) == [
        "progress",
        *(["completed"] if stage == "missing-script" else []),
    ]
    context.get_llm_settings.assert_not_called()
    if stage == "sync":
        context._get_run_script_info.assert_not_called()

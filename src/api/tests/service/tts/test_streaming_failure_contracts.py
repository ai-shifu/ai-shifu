"""Exercise streaming provider, future and persistence failure recovery."""

from concurrent.futures import Future
from unittest.mock import Mock

import pytest
from flaskr.service.tts import streaming_tts as streaming
from flaskr.service.tts import tts_handler, tts_usage_recorder

from tests.service.tts.test_request_scoped_streams import _processor
from tests.service.tts.test_streaming_tts_rate_limit_retry import _run_retry


@pytest.mark.parametrize("queue_timeout", [False, True])
def test_provider_failure_marks_segment_ready_and_only_queue_timeout_disables_stream(
    monkeypatch: pytest.MonkeyPatch,
    queue_timeout: bool,
) -> None:
    processor = _processor("gemini")
    error = (
        streaming.TTSRpmQueueTimeoutError("queue timeout")
        if queue_timeout
        else RuntimeError("provider unavailable")
    )
    monkeypatch.setattr(
        processor, "_synthesize_text_with_retry", Mock(side_effect=error)
    )
    usage = Mock()
    monkeypatch.setattr(tts_usage_recorder, "record_tts_segment_usage", usage)
    segment = streaming.TTSSegment(index=0, text="Hello")
    result = processor._synthesize_in_thread(
        segment, processor.voice_settings, processor.audio_settings, "gemini", "model"
    )
    assert result is segment
    assert segment.is_ready
    assert segment.error == str(error)
    assert processor._enabled is not queue_timeout
    assert processor._completed_segments[0] is segment
    assert list(processor.drain_ready_segments()) == []
    assert processor._next_yield_index == 1
    usage.assert_not_called()


def test_provider_returning_no_result_is_an_explicit_synthesis_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="returned no result"):
        _run_retry(monkeypatch, [None])


@pytest.mark.parametrize("chunk", ["", "new text"])
def test_disabled_processor_does_not_enqueue_text_but_drains_completed_work(
    monkeypatch: pytest.MonkeyPatch,
    chunk: str,
) -> None:
    processor = _processor("gemini")
    processor._enabled = False
    submit = Mock()
    monkeypatch.setattr(processor, "_try_submit_tts_task", submit)
    processor._completed_segments[0] = streaming.TTSSegment(
        index=0, text="failed", is_ready=True, error="failed"
    )
    assert list(processor.process_chunk(chunk)) == []
    assert processor._next_yield_index == 1
    assert processor._buffer == ""
    submit.assert_not_called()


def test_failed_pending_future_does_not_prevent_finalize_cleanup() -> None:
    processor = _processor("gemini")
    processor._enabled = False
    future = Future()
    future.set_exception(RuntimeError("worker failed"))
    processor._pending_futures = [future]
    assert list(processor.finalize(commit=False)) == []
    assert not processor._all_audio_data


def test_disabled_empty_processor_can_finalize_when_text_preprocessing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor = _processor("gemini")
    processor._enabled = False
    monkeypatch.setattr(
        streaming,
        "preprocess_for_tts",
        Mock(side_effect=ValueError("invalid markdown")),
    )
    assert list(processor.finalize(commit=False)) == []


@pytest.mark.parametrize("failure_phase", ["concat", "upload", "persistence"])
def test_finalization_failure_cleans_session_and_does_not_emit_success_or_record_usage(
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    processor = _processor("gemini")
    error = RuntimeError("operation failed")
    concatenate = Mock(return_value=b"audio")
    upload = Mock(return_value=("https://example.test/audio.mp3", "bucket"))
    save = Mock()
    cleanup = Mock()
    usage = Mock()
    {"concat": concatenate, "upload": upload, "persistence": save}[
        failure_phase
    ].side_effect = error
    monkeypatch.setattr(streaming, "concat_audio_best_effort", concatenate)
    monkeypatch.setattr(streaming, "get_audio_duration_ms", lambda _data: 100)
    monkeypatch.setattr(tts_handler, "upload_audio_to_oss", upload)
    monkeypatch.setattr(streaming, "save_audio_record", save)
    monkeypatch.setattr(streaming, "cleanup_session_after", cleanup)
    monkeypatch.setattr(tts_usage_recorder, "record_tts_aggregated_usage", usage)
    events = list(
        processor._yield_audio_complete_from_segments(
            all_segments=[(0, b"segment", 100, "Hello")],
            raw_text="Hello",
            cleaned_text="Hello",
            cleaned_text_length=5,
            commit=False,
        )
    )
    assert events == []
    cleanup.assert_called_once_with(error, source="streaming tts finalize")
    usage.assert_not_called()
    if failure_phase != "persistence":
        save.assert_not_called()


@pytest.mark.parametrize("duration", [0, 100])
def test_provider_subtitles_without_coverage_cannot_replace_full_segment_text(
    duration: int,
) -> None:
    processor = _processor("gemini")
    processor._segment_subtitle_cues[0] = [
        {"text": "partial", "start_ms": 0, "end_ms": 100}
    ]
    assert (
        processor._build_provider_segment_subtitle_cues(
            segment_index=0,
            duration_ms=duration,
            offset_ms=0,
            segment_text="partial plus missing words",
        )
        == []
    )

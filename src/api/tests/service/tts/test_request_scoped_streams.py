"""Verify request-scoped strategy selection and dispatch in the TTS processor."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from flaskr.service.tts import streaming_tts
from flaskr.service.tts.request_scoped_streams import (
    MinimaxHttpStreamStrategy,
    VolcengineTimestampStreamStrategy,
)
from flaskr.service.tts.streaming_tts import (
    StreamingTTSProcessor,
    _select_request_scoped_strategy,
)

if TYPE_CHECKING:
    import pytest


def _processor(tts_provider: str) -> StreamingTTSProcessor:
    app = MagicMock()
    with (
        patch("flaskr.service.tts.streaming_tts.is_tts_configured", return_value=True),
        patch("flaskr.service.tts.streaming_tts.generate_id", return_value="usage"),
    ):
        return StreamingTTSProcessor(
            app=app,
            generated_block_bid="block",
            outline_bid="outline",
            progress_record_bid="progress",
            user_bid="user",
            shifu_bid="shifu",
            tts_provider=tts_provider,
            tts_model="model",
        )


def test_selector_maps_capabilities_to_strategies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        streaming_tts, "should_use_minimax_http_stream", lambda name: name == "minimax"
    )
    assert isinstance(
        _select_request_scoped_strategy("minimax"), MinimaxHttpStreamStrategy
    )
    assert isinstance(
        _select_request_scoped_strategy("volcengine"), VolcengineTimestampStreamStrategy
    )
    for name in ("", "elevenlabs", "gemini", "tencent_texttovoice", "unknown"):
        assert _select_request_scoped_strategy(name) is None


def test_processor_exposes_compat_flags_from_selected_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        streaming_tts, "should_use_minimax_http_stream", lambda name: name == "minimax"
    )
    minimax = _processor("minimax")
    assert minimax._use_minimax_http_stream is True
    assert minimax._use_volcengine_timestamp_stream is False

    volcengine = _processor("volcengine")
    assert volcengine._use_minimax_http_stream is False
    assert volcengine._use_volcengine_timestamp_stream is True

    segmented = _processor("gemini")
    assert segmented._request_scoped_strategy is None
    assert segmented._use_minimax_http_stream is False
    assert segmented._use_volcengine_timestamp_stream is False


def test_request_scoped_processor_buffers_chunks_and_delegates_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        streaming_tts, "should_use_minimax_http_stream", lambda _n: False
    )
    processor = _processor("volcengine")
    strategy = MagicMock()
    strategy.finalize.return_value = iter(["event-1", "event-2"])
    processor._request_scoped_strategy = strategy

    assert list(processor.process_chunk("First sentence. ")) == []
    assert list(processor.process_chunk("Second sentence.")) == []
    assert processor._pending_futures == []
    assert processor._buffer == "First sentence. Second sentence."

    events = list(processor.finalize(commit=False))

    assert events == ["event-1", "event-2"]
    strategy.finalize.assert_called_once()
    args, kwargs = strategy.finalize.call_args
    assert args == (processor,)
    assert kwargs["raw_text"] == "First sentence. Second sentence."
    assert kwargs["cleaned_text"] == "First sentence. Second sentence."
    assert kwargs["cleaned_text_length"] == len("First sentence. Second sentence.")
    assert kwargs["commit"] is False
    assert processor._buffer == ""


def test_explicit_finalize_entry_points_use_matching_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        streaming_tts, "should_use_minimax_http_stream", lambda _n: False
    )
    processor = _processor("gemini")
    seen: list[tuple[str, object]] = []

    def _fake_finalize(self: object, target: object, **_kwargs: object) -> object:
        seen.append((type(self).__name__, target))
        yield "done"

    monkeypatch.setattr(MinimaxHttpStreamStrategy, "finalize", _fake_finalize)
    monkeypatch.setattr(VolcengineTimestampStreamStrategy, "finalize", _fake_finalize)

    kwargs = {
        "raw_text": "x",
        "cleaned_text": "x",
        "cleaned_text_length": 1,
        "commit": True,
    }
    assert list(processor._finalize_minimax_http_stream(**kwargs)) == ["done"]
    assert list(processor._finalize_volcengine_timestamp_stream(**kwargs)) == ["done"]
    assert seen == [
        ("MinimaxHttpStreamStrategy", processor),
        ("VolcengineTimestampStreamStrategy", processor),
    ]

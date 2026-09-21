"""Protect live subtitle continuity when providers revise streamed timing."""

from unittest.mock import Mock

import pytest
from flaskr.api.tts.base import TTSResult
from flaskr.service.tts import request_scoped_streams as scoped
from flaskr.service.tts import streaming_tts

from tests.service.tts.test_request_scoped_streams import _processor


def _cue(text: str, start: int, end: int) -> dict:
    return {
        "text": text,
        "start_ms": start,
        "end_ms": end,
        "segment_index": 0,
        "position": 2,
    }


@pytest.fixture
def processor() -> streaming_tts.StreamingTTSProcessor:
    result = _processor("gemini")
    result.position = 2
    return result


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("aa. bbbbbbbb. cc.", ["aa.", "bbbbb", "bbb.", "cc."]),
        ("ab. cd.", ["ab.", "cd."]),
        ("", []),
    ],
)
def test_stream_request_splitting_preserves_units_and_bounds_oversized_sentences(
    processor: object, monkeypatch: pytest.MonkeyPatch, text: str, expected: list[str]
) -> None:
    monkeypatch.setattr(scoped, "_MINIMAX_HTTP_STREAM_MAX_CHARS", 5)
    assert (
        scoped.MinimaxHttpStreamStrategy()._split_minimax_http_stream_text(
            processor, text
        )
        == expected
    )


def test_duplicate_provider_subtitles_replace_timings_without_duplicating_text(
    processor: object,
) -> None:
    target = [
        {"text": "First", "time_begin": 0, "time_end": 100},
        {"text": "Second", "time_begin": 100, "time_end": 200},
    ]
    incoming = [
        None,
        {},
        {"text": "First", "time_begin": 0, "time_end": 120},
        {"text": " second ", "time_begin": 120, "time_end": 250},
    ]
    scoped.MinimaxHttpStreamStrategy()._extend_unique_minimax_subtitles(
        processor, target, incoming
    )
    assert target == [incoming[2], incoming[3]]


@pytest.mark.parametrize("text_key", ["text", "content", "sentence"])
def test_subtitle_aliases_skip_empty_and_invalid_values(
    processor: object, text_key: str
) -> None:
    raw = [
        None,
        {},
        {
            text_key: " hello ",
            "time_begin": None,
            "start_ms": "",
            "start_time": "invalid",
            "begin_time": "20.5",
            "time_end": "bad",
        },
    ]
    cues = scoped.MinimaxHttpStreamStrategy()._minimax_subtitles_to_cues(
        processor, raw, offset_ms=100
    )
    assert cues == [_cue("hello", 120, 120)]


@pytest.mark.parametrize(
    ("previous", "incoming", "expected"),
    [
        ([], [_cue("first", 0, 100)], [_cue("first", 0, 100)]),
        ([_cue("first", 0, 100)], [], [_cue("first", 0, 100)]),
        (
            [_cue("first", 0, 100)],
            [_cue("unrelated", 0, 90), _cue("next", 100, 200)],
            [_cue("first", 0, 100), _cue("next", 100, 200)],
        ),
        (
            [_cue("first", 0, 100), _cue("tail", 100, 200)],
            [
                _cue("changed", 0, 50),
                _cue("noise", 50, 80),
                _cue("tail", 80, 250),
                _cue("last", 250, 300),
            ],
            [_cue("first", 0, 100), _cue("tail", 100, 250), _cue("last", 250, 300)],
        ),
    ],
)
def test_live_cue_merge_keeps_played_prefix_and_extends_only_tail(
    processor: object, previous: list, incoming: list, expected: list
) -> None:
    before = [dict(item) for item in previous]
    result = scoped.MinimaxHttpStreamStrategy()._merge_minimax_live_request_cues(
        processor, previous, incoming
    )
    assert result == expected
    assert previous == before


@pytest.mark.parametrize(
    ("offset", "duration", "expected"),
    [(100, 100, [_cue("first", 100, 200)]), (0, 0, [])],
)
def test_live_timeline_clamps_overlap_and_drops_cues_past_request_end(
    processor: object, offset: int, duration: int, expected: list
) -> None:
    cues = [_cue("first", 0, 300), _cue("late", 400, 500)]
    result = scoped.MinimaxHttpStreamStrategy()._normalize_minimax_live_request_cues(
        processor, cues, live_offset_ms=offset, live_request_end_ms=duration
    )
    assert result == expected


def test_empty_or_zero_duration_live_subtitles_do_not_create_events(
    processor: object,
) -> None:
    strategy = scoped.MinimaxHttpStreamStrategy()
    assert (
        strategy._normalize_minimax_live_request_cues(
            processor, [], live_offset_ms=0, live_request_end_ms=10
        )
        == []
    )
    assert (
        strategy._scale_minimax_cues_to_live_request(
            processor,
            [],
            provider_offset_ms=0,
            live_offset_ms=0,
            live_request_end_ms=10,
        )
        == []
    )
    assert (
        strategy._scale_minimax_cues_to_live_request(
            processor,
            [_cue("hello", 0, 10)],
            provider_offset_ms=0,
            live_offset_ms=0,
            live_request_end_ms=0,
        )
        == []
    )


def test_zero_source_duration_does_not_divide_by_zero(processor: object) -> None:
    cues = scoped.MinimaxHttpStreamStrategy()._scale_minimax_cues_to_live_request(
        processor,
        [_cue("hello", 20, 20)],
        provider_offset_ms=20,
        live_offset_ms=100,
        live_request_end_ms=200,
    )
    assert cues == [_cue("hello", 100, 100)]


@pytest.mark.parametrize("decode_duration", [None, 0, -1])
def test_complete_fallback_rejects_undecodable_audio(
    processor: object, monkeypatch: pytest.MonkeyPatch, decode_duration: int | None
) -> None:
    provider = Mock()
    provider.synthesize.return_value = TTSResult(b"invalid", 50, 24000, "mp3")
    monkeypatch.setattr(
        streaming_tts, "try_get_audio_duration_ms", lambda *_a, **_k: decode_duration
    )
    result = scoped.MinimaxHttpStreamStrategy()._synthesize_minimax_complete_fallback(
        processor, provider, request_text="hello", request_format="mp3", request_index=2
    )
    assert result is None
    provider.synthesize.assert_called_once_with(
        text="hello",
        voice_settings=processor.voice_settings,
        audio_settings=processor.audio_settings,
        model=processor.tts_model,
    )


def test_complete_fallback_failure_preserves_stream_recovery_path(
    processor: object,
) -> None:
    provider = Mock()
    provider.synthesize.side_effect = RuntimeError("provider unavailable")
    assert (
        scoped.MinimaxHttpStreamStrategy()._synthesize_minimax_complete_fallback(
            processor,
            provider,
            request_text="hello",
            request_format="mp3",
            request_index=0,
        )
        is None
    )


def test_complete_fallback_uses_decoded_duration_and_provider_accounting(
    processor: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    provider.synthesize.return_value = TTSResult(
        b"valid", 0, 24000, "", word_count=2, usage_characters=6
    )
    monkeypatch.setattr(
        streaming_tts, "try_get_audio_duration_ms", lambda *_a, **_k: 250
    )
    result = scoped.MinimaxHttpStreamStrategy()._synthesize_minimax_complete_fallback(
        processor, provider, request_text="hello", request_format="mp3", request_index=0
    )
    assert result.audio_data == b"valid"
    assert result.duration_ms == 250
    assert result.word_count == 2
    assert result.usage_characters == 6
    assert result.audio_format == "mp3"

"""Protect source text alignment and monotonic Tencent subtitle timing."""

import pytest
from flaskr.api.tts import tencent_provider as tencent
from flaskr.api.tts.base import AudioSettings, VoiceSettings


def _cue(text: str, start: int, end: int, segment: int = 0, position: int = 0) -> dict:
    return {
        "text": text,
        "start_ms": start,
        "end_ms": end,
        "segment_index": segment,
        "position": position,
    }


@pytest.mark.parametrize(
    "text_key", ["Text", "text", "Word", "word", "Sentence", "sentence"]
)
def test_subtitle_aliases_skip_invalid_values_and_clamp_timing(text_key: str) -> None:
    source = {
        text_key: " hello. ",
        "BeginTime": "bad",
        "begin_time": None,
        "beginTime": "",
        "StartTime": "-10",
        "EndTime": object(),
        "end_time": "-20",
        "BeginIndex": "bad",
        "begin_index": None,
        "beginIndex": "",
        "TextBegin": "3",
        "EndIndex": "1",
    }
    result = tencent.normalize_tencent_subtitle_cues(
        [None, "noise", {}, source, source.copy()],
        offset_ms=30,
        segment_index=-1,
        position=-2,
    )
    assert result == [_cue("hello.", 20, 20)]
    assert source["StartTime"] == "-10"


def test_word_cues_merge_until_sentence_boundary_and_retain_unpunctuated_tail() -> None:
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {"Text": "hello", "BeginTime": 10, "EndTime": 30},
            {"Text": "!", "BeginTime": 30, "EndTime": 40},
            {"Text": "tail", "BeginTime": 50},
        ],
        offset_ms=100,
        segment_index=2,
        position=4,
    )
    assert result == [_cue("hello!", 110, 140, 2, 4), _cue("tail", 150, 150, 2, 4)]


def test_indexed_subtitles_preserve_source_punctuation_and_trim_inter_sentence_space() -> (
    None
):
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {
                "Text": "A",
                "BeginTime": 10,
                "EndTime": 50,
                "BeginIndex": 2,
                "EndIndex": 4,
            },
            {
                "Text": "BB",
                "BeginTime": 100,
                "EndTime": 200,
                "BeginIndex": 6,
                "EndIndex": 9,
            },
        ],
        source_text="  A!  BB?  ",
        offset_ms=300,
        segment_index=3,
        position=5,
    )
    assert result == [_cue("A!", 310, 350, 3, 5), _cue("BB?", 400, 500, 3, 5)]


def test_missing_sentence_indices_fall_back_to_weighted_source_alignment() -> None:
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {
                "Text": "ABC",
                "BeginTime": 100,
                "EndTime": 400,
                "BeginIndex": 0,
                "EndIndex": 2,
            },
        ],
        source_text="A! BB?",
    )
    assert result == [_cue("A!", 100, 200), _cue("BB?", 200, 400)]


def test_weighted_alignment_assigns_silent_punctuation_to_previous_sentence() -> None:
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {"Text": "A", "BeginTime": 100, "EndTime": 200},
            {"Text": ",", "BeginTime": 200, "EndTime": 250},
            {"Text": "B", "BeginTime": 300, "EndTime": 400},
        ],
        source_text="A! B?",
    )
    assert result == [_cue("A!", 100, 250), _cue("B?", 250, 400)]


def test_weighted_alignment_handles_leading_silence_and_overlapping_provider_times() -> (
    None
):
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {"Text": ",", "BeginTime": 0, "EndTime": 50},
            {"Text": "AA", "BeginTime": 50, "EndTime": 150},
            {"Text": "BB", "BeginTime": 100, "EndTime": 200},
        ],
        source_text="AAA! B?",
    )
    assert result == [_cue("AAA!", 50, 150), _cue("B?", 150, 200)]


def test_punctuation_only_provider_text_uses_proportional_source_duration() -> None:
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {"Text": "...", "BeginTime": 100, "EndTime": 400},
        ],
        source_text="A! BB?",
    )
    assert result == [_cue("A!", 100, 200), _cue("BB?", 200, 400)]


@pytest.mark.parametrize("source", ["", " \t ", "A! B?"])
def test_absent_subtitles_never_invent_source_timing(source: str) -> None:
    assert (
        tencent.normalize_tencent_subtitle_cues(
            [{}, None, {"Text": " "}], source_text=source
        )
        == []
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-9, 0.5), (-1, 0.8), (8, 2.0), ("bad", 1.0), (object(), 1.0)],
)
def test_voice_speed_mapping_preserves_supported_flow_range(
    value: object, expected: float
) -> None:
    payload = tencent.build_tencent_sse_payload(
        app_id="123",
        text=" hello ",
        voice_settings=VoiceSettings(voice_id="unknown", speed=value),
        audio_settings=AudioSettings(),
    )
    assert payload["Voice"]["Speed"] == expected
    assert payload["Language"] == "zh"
    assert payload["Text"] == "hello"


@pytest.mark.parametrize(
    ("value", "expected"), [(0.01, 0.1), (0.6, 0.6), (5, 1), ("bad", 1), (object(), 1)]
)
def test_voice_volume_mapping_uses_safe_defaults(
    value: object, expected: float
) -> None:
    payload = tencent.build_tencent_sse_payload(
        app_id="123",
        text="hello",
        voice_settings=VoiceSettings(volume=value, emotion="fear"),
        audio_settings=AudioSettings(),
    )
    assert payload["Voice"]["Volume"] == expected
    assert payload["Voice"]["Emotion"] == "fearful"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, True),
        (False, False),
        (None, False),
        (0, False),
        (1, True),
        ("yes", True),
        ("false", False),
    ],
)
def test_final_flags_are_normalized_without_requiring_audio(
    raw: object, expected: bool
) -> None:
    result = tencent.parse_tencent_sse_message(
        {"response": {"final": raw}}, request_text="hello"
    )
    assert result is not None
    assert result.is_final is expected
    assert result.audio_data == b""


def test_alignment_parser_ignores_noise_and_recovers_missing_text_from_source() -> None:
    result = tencent.parse_tencent_sse_message(
        {
            "Alignments": [
                None,
                {},
                {
                    "text_begin": 1,
                    "text_end": 3,
                    "time_begin_ms": 20,
                    "time_end_ms": 10,
                },
                {"Text": "tail", "TextBegin": 4, "TextEnd": 2, "TimeBeginMs": "bad"},
            ]
        },
        request_text="ABCD",
    )
    assert result is not None
    assert result.subtitles == [
        {"Text": "BC", "BeginTime": 20, "EndTime": 20, "BeginIndex": 1, "EndIndex": 3},
        {"Text": "tail", "BeginTime": 0, "EndTime": 0, "BeginIndex": 4, "EndIndex": 4},
    ]


@pytest.mark.parametrize(
    "payload",
    [{"Alignments": "noise"}, {"Type": "heartbeat"}, {"Code": 0}, {"Code": "0"}],
)
def test_metadata_only_messages_do_not_create_audio_chunks(payload: dict) -> None:
    assert tencent.parse_tencent_sse_message(payload, request_text="hello") is None


@pytest.mark.parametrize("code", [1, "denied"])
def test_nonzero_status_codes_preserve_provider_correlation_ids(code: object) -> None:
    with pytest.raises(tencent.TencentTTSError) as caught:
        tencent.parse_tencent_sse_message(
            {
                "Response": {"Code": code, "Message": "unavailable"},
                "RequestId": "request",
                "MessageId": "message",
            },
            request_text="hello",
        )
    assert caught.value.code == code
    assert caught.value.request_id == "request"
    assert caught.value.message_id == "message"

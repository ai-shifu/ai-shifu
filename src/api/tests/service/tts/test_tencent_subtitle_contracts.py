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


def test_indexed_cue_spanning_unicode_sentences_divides_duration_without_overlap() -> (
    None
):
    source = "مرحبا؟ نعم۔"
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {
                "Text": source,
                "BeginTime": 0,
                "EndTime": 1000,
                "BeginIndex": 0,
                "EndIndex": len(source),
            }
        ],
        source_text=source,
        offset_ms=100,
        segment_index=2,
        position=4,
    )

    assert result == [_cue("مرحبا؟", 100, 725, 2, 4), _cue("نعم۔", 725, 1100, 2, 4)]


@pytest.mark.parametrize(
    ("duration_ms", "boundaries"),
    [
        (0, (10, 10, 10, 10)),
        (1, (10, 10, 10, 11)),
        (5, (10, 11, 12, 15)),
    ],
)
def test_indexed_cue_spanning_three_sentences_rounds_cumulative_boundaries(
    duration_ms: int, boundaries: tuple[int, int, int, int]
) -> None:
    source = "  A؟  BB।  CCC။  "
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {
                "Text": source,
                "BeginTime": 10,
                "EndTime": 10 + duration_ms,
                "BeginIndex": 0,
                "EndIndex": len(source),
            }
        ],
        source_text=source,
    )

    assert result == [
        _cue("A؟", boundaries[0], boundaries[1]),
        _cue("BB।", boundaries[1], boundaries[2]),
        _cue("CCC။", boundaries[2], boundaries[3]),
    ]


@pytest.mark.parametrize("with_anchors", [False, True], ids=["crossing", "anchored"])
def test_indexed_cue_splits_use_overlap_weights_and_preserve_sentence_anchors(
    with_anchors: bool,
) -> None:
    source = "AA؟ BBBB۔ CCC।"
    second_start = source.index("BBBB")
    split_at = second_start + 1
    subtitles = [
        {
            "Text": source[:split_at],
            "BeginTime": 100,
            "EndTime": 400,
            "BeginIndex": 0,
            "EndIndex": split_at,
        },
        {
            "Text": source[split_at:],
            "BeginTime": 500,
            "EndTime": 1000,
            "BeginIndex": split_at,
            "EndIndex": len(source),
        },
    ]
    if with_anchors:
        subtitles.extend(
            [
                {
                    "Text": "A",
                    "BeginTime": 20,
                    "EndTime": 80,
                    "BeginIndex": 0,
                    "EndIndex": 1,
                },
                {
                    "Text": "C",
                    "BeginTime": 1020,
                    "EndTime": 1100,
                    "BeginIndex": source.index("CCC") + 2,
                    "EndIndex": source.index("CCC") + 3,
                },
            ]
        )

    result = tencent.normalize_tencent_subtitle_cues(subtitles, source_text=source)

    assert result == [
        _cue("AA؟", 20 if with_anchors else 100, 300),
        _cue("BBBB۔", 300, 750),
        _cue("CCC।", 750, 1100 if with_anchors else 1000),
    ]


def test_indexed_shared_cue_clamps_overlapping_sentence_anchor() -> None:
    source = "AA؟ B۔"
    second_start = source.index("B")
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {
                "Text": source,
                "BeginTime": 100,
                "EndTime": 400,
                "BeginIndex": 0,
                "EndIndex": len(source),
            },
            {
                "Text": "B",
                "BeginTime": 250,
                "EndTime": 260,
                "BeginIndex": second_start,
                "EndIndex": second_start + 1,
            },
        ],
        source_text=source,
    )

    assert result == [_cue("AA؟", 100, 300), _cue("B۔", 300, 400)]


def test_indexed_sentences_clamp_short_later_cues_without_extending_total_duration() -> (
    None
):
    source = "A؟ B। C။"
    subtitles = [
        {
            "Text": text,
            "BeginTime": start,
            "EndTime": end,
            "BeginIndex": source.index(text),
            "EndIndex": source.index(text) + len(text),
        }
        for text, start, end in [("A", 100, 600), ("B", 250, 260), ("C", 300, 500)]
    ]
    result = tencent.normalize_tencent_subtitle_cues(
        subtitles,
        source_text=source,
        offset_ms=50,
        segment_index=2,
        position=4,
    )

    assert result == [
        _cue("A؟", 150, 650, 2, 4),
        _cue("B।", 650, 650, 2, 4),
        _cue("C။", 650, 650, 2, 4),
    ]
    assert result[-1]["end_ms"] == max(item["EndTime"] for item in subtitles) + 50


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("مرحبا\u061f", "التالي\u06d4"),
        ("पहला\u0964", "दूसरा\u0965"),
        ("ပထမ\u104b", "ဒုတိယ\u104b"),
        ('"First!?"', "Second."),
        ("\u201c第一句\uff1f\uff01\u201d", "第二句\u3002"),
        ("(First!?)", "Second."),
        ("„Hallo!“", "„Weiter.“"),
        ("»Hallo!«", "»Weiter.«"),
        ("‹Hallo!›", "‹Weiter.›"),
        ("›Hallo!‹", "›Weiter.‹"),
    ],
)
def test_multilingual_sentence_ranges_preserve_source_indices_and_provider_timing(
    first: str, second: str
) -> None:
    source = f"  {first}  {second}  "
    first_start = source.index(first)
    second_start = source.index(second)
    ranges = [
        (first, first_start, first_start + len(first)),
        (second, second_start, second_start + len(second)),
    ]
    assert tencent._split_tencent_sentence_units_with_ranges(source) == ranges
    assert tencent._split_tencent_sentence_units(source) == [first, second]

    result = tencent.normalize_tencent_subtitle_cues(
        [
            {
                "Text": "first",
                "BeginTime": 10,
                "EndTime": 50,
                "BeginIndex": ranges[0][1],
                "EndIndex": ranges[0][2],
            },
            {
                "Text": "second",
                "BeginTime": 100,
                "EndTime": 200,
                "BeginIndex": ranges[1][1],
                "EndIndex": ranges[1][2],
            },
        ],
        source_text=source,
        offset_ms=300,
        segment_index=3,
        position=5,
    )
    assert result == [_cue(first, 310, 350, 3, 5), _cue(second, 400, 500, 3, 5)]


def test_adjacent_quoted_sentence_keeps_its_opening_quote_and_source_indices() -> None:
    first = "第一句。"
    second = "「第二句。」"
    source = first + second
    assert tencent._split_tencent_sentence_units_with_ranges(source) == [
        (first, 0, len(first)),
        (second, len(first), len(source)),
    ]

    result = tencent.normalize_tencent_subtitle_cues(
        [
            {
                "Text": first,
                "BeginTime": 10,
                "EndTime": 50,
                "BeginIndex": 0,
                "EndIndex": len(first),
            },
            {
                "Text": second,
                "BeginTime": 100,
                "EndTime": 200,
                "BeginIndex": len(first),
                "EndIndex": len(source),
            },
        ],
        source_text=source,
    )

    assert result == [_cue(first, 10, 50), _cue(second, 100, 200)]


@pytest.mark.parametrize(
    "ending", ["\u061f", "\u0964", "\u0965", "\u104b", '!?"', "\u3002\u201d"]
)
def test_multilingual_word_cues_finish_at_sentence_endings_and_closing_quotes(
    ending: str,
) -> None:
    result = tencent.normalize_tencent_subtitle_cues(
        [
            {"Text": "first", "BeginTime": 10, "EndTime": 30},
            {"Text": ending, "BeginTime": 30, "EndTime": 40},
            {"Text": "tail", "BeginTime": 50, "EndTime": 100},
        ]
    )
    assert result == [_cue(f"first{ending}", 10, 40), _cue("tail", 50, 100)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("مرحبا\u061f", "مرحبا\u061f"),
        ("पहला\u0964", "पहला\u0964"),
        ("ပထမ\u104b", "ပထမ\u104b"),
        (' "First!?" ', '"First!?"'),
        ("\u201c第一句\u3002\u201d", "\u201c第一句\u3002\u201d"),
        ("„Hallo!“", "„Hallo!“"),
        ("»Hallo!«", "»Hallo!«"),
        ("‹Hallo!›", "‹Hallo!›"),
        ("›Hallo!‹", "›Hallo!‹"),
        ("First? tail", "First? tail."),
        ("你好", "你好\u3002"),
        ("", ""),
    ],
)
def test_terminal_punctuation_preserves_unicode_endings_and_adds_only_missing_ones(
    text: str, expected: str
) -> None:
    assert tencent.ensure_tencent_terminal_punctuation(text) == expected


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

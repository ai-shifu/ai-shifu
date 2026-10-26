"""Exercise replay payload round trips and audio snapshot isolation."""

import copy
import json

import pytest
from flaskr.service.learn import listen_element_payloads as payloads
from flaskr.service.learn import listen_element_rows as rows
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    ElementAudioDTO,
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    ElementVisualDTO,
    GeneratedType,
    LearnStatus,
    OutlineItemUpdateDTO,
    SubtitleCueDTO,
    VariableUpdateDTO,
)
from flaskr.service.learn.models import LearnGeneratedElement, LearnProgressRecord


def _cue() -> dict:
    return {
        "text": "Hello",
        "start_ms": 0,
        "end_ms": 120,
        "segment_index": 0,
        "position": 2,
    }


def _segment(index: int = 0, **kwargs: object) -> dict:
    return {
        "position": 2,
        "segment_index": index,
        "audio_data": "pcm",
        "duration_ms": 120,
        "is_final": False,
        **kwargs,
    }


def _element(**kwargs: object) -> ElementDTO:
    return ElementDTO(
        element_bid="element",
        generated_block_bid="block",
        element_index=4,
        role="teacher",
        element_type=kwargs.pop("element_type", ElementType.TEXT),
        element_type_code=213,
        content_text="Narration",
        **kwargs,
    )


@pytest.mark.parametrize(
    "raw", ["", "broken JSON", "null", "[]", '"text"', "1", "true"]
)
def test_unusable_stored_payload_does_not_break_history_replay(raw: str) -> None:
    assert payloads._deserialize_payload(raw).__json__() == {
        "audio": None,
        "previous_visuals": [],
    }


def test_complete_payload_round_trip_preserves_live_follow_up_and_subtitle_fields() -> (
    None
):
    payload = ElementPayloadDTO(
        audio=ElementAudioDTO(
            "https://example.test/a.mp3", "audio", 120, 2, [SubtitleCueDTO(**_cue())]
        ),
        previous_visuals=[ElementVisualDTO("html", "<b>Hello</b>")],
        anchor_element_bid="anchor",
        ask_element_bid="ask",
        user_input="Question?",
        diff_payload=[{"op": "replace", "value": "Answer"}],
        asks=[{"ask": "Q", "answer": "A"}],
        interaction_mode="live_voice",
        live_session_bid="live",
        live_turn_index=0,
        interrupted=False,
    )
    assert (
        payloads._deserialize_payload(payloads._serialize_payload(payload)).__json__()
        == payload.__json__()
    )
    assert payloads._serialize_payload(None) == ""


def test_optional_payload_fields_ignore_incompatible_legacy_values() -> None:
    payload = payloads._deserialize_payload(
        json.dumps(
            {
                "audio": "legacy",
                "previous_visuals": [None, {}, {"visual_type": "svg", "content": None}],
                "anchor_element_bid": 1,
                "ask_element_bid": False,
                "user_input": False,
                "diff_payload": {},
                "asks": "legacy",
                "interaction_mode": "unknown",
                "live_session_bid": 7,
                "live_turn_index": True,
                "interrupted": "false",
            }
        )
    )
    assert payload.audio is None
    assert [item.__json__() for item in payload.previous_visuals] == [
        {"visual_type": "", "content": ""},
        {"visual_type": "svg", "content": ""},
    ]
    assert (
        payload.anchor_element_bid,
        payload.ask_element_bid,
        payload.user_input,
        payload.live_session_bid,
    ) == ("1", "", "", "7")
    assert payload.diff_payload is payload.asks is payload.interaction_mode is None
    assert payload.live_turn_index is payload.interrupted is None


@pytest.mark.parametrize(
    ("kind", "visual"),
    [
        (ElementType.HTML, "html"),
        (ElementType.TABLES, "md_table"),
        (ElementType.CODE, "fence"),
        (ElementType.MD_IMG, "md_img"),
        (ElementType.TEXT, None),
    ],
)
def test_stream_payload_only_retains_content_for_visual_elements(
    kind: ElementType, visual: str | None
) -> None:
    result = payloads._payload_from_stream_element(kind, "content")
    assert [item.__json__() for item in result.previous_visuals] == (
        [{"visual_type": visual, "content": "content"}] if visual else []
    )
    assert payloads._payload_from_stream_element(kind, "").previous_visuals == []


def test_retransmitted_audio_merges_without_erasing_data_subtitles_or_finality() -> (
    None
):
    existing = [_segment(is_final=True, subtitle_cues=[_cue()])]
    original = copy.deepcopy(existing)
    merged = payloads._upsert_audio_segment_payload(
        existing, _segment(audio_data="", duration_ms=0)
    )
    assert merged == original
    merged[0]["subtitle_cues"][0]["text"] = "Changed"
    assert existing == original
    updated = payloads._upsert_audio_segment_payload(
        existing, _segment(subtitle_cues=[{**_cue(), "text": "Updated"}])
    )
    assert updated[0]["subtitle_cues"][0]["text"] == "Updated"
    assert updated[0]["is_final"] is True


def test_out_of_order_audio_is_sorted_and_invalid_entries_are_removed() -> None:
    result = payloads._upsert_audio_segment_payload(
        [None, _segment(2), _segment(0, position=3)], _segment(1)
    )
    assert [(item["position"], item["segment_index"]) for item in result] == [
        (2, 1),
        (2, 2),
        (3, 0),
    ]
    assert payloads._upsert_audio_segment_payload(result, None) == result
    assert payloads._prepare_audio_segments_for_element(None, is_final=True) == []


@pytest.mark.parametrize("final", [True, False])
def test_storage_strips_audio_bytes_and_subtitles_without_mutating_live_snapshot(
    final: bool,
) -> None:
    segments = [
        _segment(0, is_final=True, subtitle_cues=[_cue()]),
        _segment(1, subtitle_cues="invalid"),
    ]
    before = copy.deepcopy(segments)
    stored = payloads._sanitize_audio_segments_for_storage(segments, is_final=final)
    assert segments == before
    assert [item["is_final"] for item in stored] == (
        [False, True] if final else [True, False]
    )
    assert all(
        item["audio_data"] == "" and "subtitle_cues" not in item for item in stored
    )
    assert payloads._mark_last_audio_segment_final({}, 7) == []


@pytest.mark.parametrize(
    ("audios", "segments", "position"),
    [
        ({3: None}, {}, 3),
        ({2: None, 4: None}, {7: []}, 7),
        ({0: None, 4: None}, {1: [], 2: []}, 0),
        ({2: None, 4: None}, {}, None),
        ({}, {}, None),
    ],
)
def test_default_audio_position_uses_only_unambiguous_or_zero_fallback(
    audios: dict, segments: dict, position: int | None
) -> None:
    assert payloads._pick_default_audio_position(audios, segments) == position


def test_audio_dto_conversions_preserve_subtitle_alignment() -> None:
    segment = AudioSegmentDTO(
        0, "pcm", 120, is_final=False, position=2, subtitle_cues=[_cue()]
    )
    assert payloads._audio_segment_payload(segment) == _segment(subtitle_cues=[_cue()])
    complete = AudioCompleteDTO(
        "https://example.test/a.mp3", "audio", 120, position=2, subtitle_cues=[_cue()]
    )
    result = payloads._make_audio_payload(complete)
    assert result.__json__() == complete.__json__()
    assert result.subtitle_cues is not complete.subtitle_cues


def test_element_storage_round_trip_preserves_identity_and_drops_transient_audio_bytes() -> (
    None
):
    source = _element(
        change_type=ElementChangeType.RENDER,
        is_renderable=False,
        is_speakable=True,
        is_final=True,
        audio_url="https://example.test/audio.mp3",
        audio_segments=[_segment()],
        payload=ElementPayloadDTO(user_input="answer"),
        target_element_bid="target",
        sequence_number=8,
    )
    progress = LearnProgressRecord(
        progress_record_bid="progress",
        user_bid="user",
        outline_item_bid="outline",
        shifu_bid="course",
    )
    row = rows._serialize_element_row(
        progress_record=progress, element=source, run_session_bid="run", run_event_seq=9
    )
    assert (
        row.progress_record_bid,
        row.user_bid,
        row.outline_item_bid,
        row.shifu_bid,
    ) == ("progress", "user", "outline", "course")
    restored = rows._element_from_row(row)
    assert restored.element_bid == source.element_bid
    assert restored.content_text == "Narration"
    assert restored.run_session_bid == "run"
    assert restored.run_event_seq == 9
    assert restored.audio_segments == [_segment(audio_data="", is_final=True)]
    assert restored.payload.user_input == "answer"
    assert not restored.is_renderable
    assert restored.is_speakable


@pytest.mark.parametrize(
    ("stored_type", "expected_type"),
    [
        ("sandbox", ElementType.HTML),
        ("picture", ElementType.IMG),
        ("video", ElementType.HTML),
        ("future", ElementType.TEXT),
    ],
)
@pytest.mark.parametrize("audio_json", ["invalid", "{}", "[]"])
def test_legacy_rows_normalize_types_and_corrupt_audio_trails(
    stored_type: str, expected_type: ElementType, audio_json: str
) -> None:
    row = LearnGeneratedElement(
        element_type=stored_type,
        change_type="future",
        audio_segments=audio_json,
        payload="{}",
        is_final=1,
        content_text="content",
        is_renderable=1,
    )
    restored = rows._element_from_row(row)
    assert restored.element_type == expected_type
    assert restored.change_type is None
    assert restored.audio_segments == []
    assert restored.is_speakable is (expected_type == ElementType.TEXT)


def test_interaction_replay_copies_latest_answer_into_payload() -> None:
    row = LearnGeneratedElement(
        element_type="interaction", payload='{"user_input":"old"}', event_type="element"
    )
    event = rows._event_from_row(row, interaction_user_input="latest answer")
    assert event.content.payload.user_input == "latest answer"
    assert event.type == event.event_type == "element"


@pytest.mark.parametrize(
    ("kind", "content"),
    [
        ("done", '{"text":"done"}'),
        ("break", '"break"'),
        ("error", '{"error":true}'),
        ("future", "{}"),
        ("variable_update", "not JSON"),
        ("variable_update", "[]"),
        ("audio_segment", "{}"),
        ("audio_complete", "{}"),
        ("outline_item_update", '{"status":"unknown"}'),
        ("done", ""),
    ],
)
def test_non_structured_or_incomplete_event_payloads_remain_replayable(
    kind: str, content: str
) -> None:
    row = LearnGeneratedElement(event_type=kind, content_text=content)
    assert rows._deserialize_event_content(row) == content


@pytest.mark.parametrize(
    ("kind", "content", "dto"),
    [
        (
            GeneratedType.VARIABLE_UPDATE,
            {"variable_name": "name", "variable_value": "value"},
            VariableUpdateDTO,
        ),
        (
            GeneratedType.OUTLINE_ITEM_UPDATE,
            {
                "outline_bid": "outline",
                "title": "Lesson",
                "status": LearnStatus.COMPLETED.value,
                "has_children": "false",
            },
            OutlineItemUpdateDTO,
        ),
        (
            GeneratedType.AUDIO_SEGMENT,
            {
                "audio_data": "pcm",
                "segment_index": 0,
                "duration_ms": 120,
                "position": 2,
                "is_final": "true",
                "stream_element_number": 4,
                "stream_element_type": "text",
                "subtitle_cues": [_cue()],
            },
            AudioSegmentDTO,
        ),
        (
            GeneratedType.AUDIO_COMPLETE,
            {
                "audio_url": "https://example.test/a.mp3",
                "audio_bid": "audio",
                "duration_ms": 120,
                "position": 2,
                "subtitle_cues": [_cue()],
            },
            AudioCompleteDTO,
        ),
    ],
)
def test_structured_events_rehydrate_their_typed_payload(
    kind: GeneratedType, content: dict, dto: type
) -> None:
    row = LearnGeneratedElement(
        event_type=kind.value,
        content_text=json.dumps(content),
        generated_block_bid="block",
        run_session_bid="run",
        run_event_seq=4,
    )
    event = rows._event_from_row(row)
    assert isinstance(event.content, dto)
    assert event.run_event_seq == 4
    assert event.run_session_bid == "run"
    assert event.generated_block_bid == "block"
    serialized = event.content.__json__()
    if kind == GeneratedType.OUTLINE_ITEM_UPDATE:
        assert serialized["has_children"] is False
    if kind == GeneratedType.AUDIO_SEGMENT:
        assert serialized["is_final"] is True
    if "subtitle_cues" in content:
        assert serialized["subtitle_cues"] == [_cue()]


@pytest.mark.parametrize("existing_text", ["", "current"])
def test_history_moves_visual_content_once_to_primary_element(
    existing_text: str,
) -> None:
    element = _element(
        payload=ElementPayloadDTO(
            previous_visuals=[
                ElementVisualDTO("html", ""),
                ElementVisualDTO("svg", "visual"),
            ]
        )
    )
    element.content_text = existing_text
    normalized = rows._normalize_record_element(element)
    assert normalized.content_text == (existing_text or "visual")
    assert [item.content for item in normalized.payload.previous_visuals] == ["", ""]
    assert rows._normalize_record_element(_element()).content_text == "Narration"

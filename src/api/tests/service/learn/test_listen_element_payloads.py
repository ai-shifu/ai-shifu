"""Verify listen element payloads behavior."""

import json

import pytest
from flaskr.service.learn.elements.payloads import (
    _deserialize_payload,
    _mark_last_audio_segment_final,
    _serialize_payload,
    _upsert_audio_segment_payload,
)
from flaskr.service.learn.learn_dtos import ElementPayloadDTO


def test_interaction_title_round_trip_preserves_markdown_and_submitted_answer() -> None:
    prompt = "    First line\n**Which example?**  "
    payload = ElementPayloadDTO(interaction_prompt=prompt, user_input="First")
    restored = _deserialize_payload(_serialize_payload(payload))
    assert restored.interaction_prompt == prompt
    assert restored.user_input == "First"
    assert restored.__json__()["interaction_prompt"] == prompt


@pytest.mark.parametrize("value", [None, "", "  ", 12, [], {}])
def test_legacy_or_empty_interaction_titles_are_absent(value: object) -> None:
    raw = json.dumps({"interaction_prompt": value}) if value is not None else "{}"
    restored = _deserialize_payload(raw)
    assert restored.interaction_prompt is None
    assert "interaction_prompt" not in restored.__json__()


def test_upsert_audio_segment_payload_deduplicates_by_position_and_segment_index() -> (
    None
):
    existing = [
        {
            "position": 0,
            "segment_index": 0,
            "audio_data": "segment-0",
            "duration_ms": 120,
            "is_final": False,
        }
    ]

    merged = _upsert_audio_segment_payload(
        existing,
        {
            "position": 0,
            "segment_index": 0,
            "audio_data": "segment-0",
            "duration_ms": 180,
            "is_final": False,
        },
    )

    assert merged == [
        {
            "position": 0,
            "segment_index": 0,
            "audio_data": "segment-0",
            "duration_ms": 180,
            "is_final": False,
        }
    ]


def test_mark_last_audio_segment_final_keeps_deduplicated_state() -> None:
    audio_segments_by_position = {
        0: _upsert_audio_segment_payload(
            [],
            {
                "position": 0,
                "segment_index": 0,
                "audio_data": "segment-0",
                "duration_ms": 180,
                "is_final": False,
            },
        )
    }

    audio_segments_by_position[0] = _upsert_audio_segment_payload(
        audio_segments_by_position[0],
        {
            "position": 0,
            "segment_index": 0,
            "audio_data": "segment-0",
            "duration_ms": 180,
            "is_final": False,
        },
    )

    finalized = _mark_last_audio_segment_final(audio_segments_by_position, 0)

    assert finalized == [
        {
            "position": 0,
            "segment_index": 0,
            "audio_data": "segment-0",
            "duration_ms": 180,
            "is_final": True,
        }
    ]

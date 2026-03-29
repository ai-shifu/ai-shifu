from flaskr.service.learn.listen_element_payloads import (
    _mark_last_audio_segment_final,
    _upsert_audio_segment_payload,
)


def test_upsert_audio_segment_payload_deduplicates_by_position_and_segment_index():
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


def test_mark_last_audio_segment_final_keeps_deduplicated_state():
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

"""Regression coverage for the accompanying runtime fix."""

import pytest
from flaskr.service.learn import listen_element_payloads as payloads
from flaskr.service.learn.learn_dtos import (
    ElementAudioDTO,
    ElementPayloadDTO,
    ElementVisualDTO,
    SubtitleCueDTO,
)


def _cue() -> dict:
    return {
        "text": "Hello",
        "start_ms": 0,
        "end_ms": 120,
        "segment_index": 0,
        "position": 2,
    }


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

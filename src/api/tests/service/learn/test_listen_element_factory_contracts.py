"""Verify final listen snapshots retain visual order and narration alignment."""

from itertools import count

import pytest
from flaskr.service.learn import listen_element_factory as factory
from flaskr.service.learn.learn_dtos import ElementAudioDTO, ElementType
from flaskr.service.learn.listen_slide_builder import VisualSegment
from flaskr.service.learn.listen_source_span_utils import (
    normalize_source_span,
    slice_source_by_span,
)


@pytest.fixture(autouse=True)
def deterministic_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = count()
    monkeypatch.setattr(factory, "_new_element_bid", lambda _app: f"text-{next(ids)}")


def _build(**kwargs: object) -> list:
    return factory._build_final_elements_for_av_contract(
        app=None,
        generated_block_bid="block",
        role="teacher",
        raw_content=kwargs.pop("raw_content", "<svg/>\nFirst\nSecond"),
        av_contract=kwargs.pop("av_contract", None),
        visual_segments=kwargs.pop("visual_segments", []),
        audio_by_position=kwargs.pop("audio_by_position", {}),
        audio_segments_by_position=kwargs.pop("audio_segments_by_position", {}),
        **kwargs,
    )


def _visual(bid: str = "visual", **kwargs: object) -> VisualSegment:
    return VisualSegment(
        segment_id=bid,
        generated_block_bid="block",
        element_index=0,
        visual_kind=kwargs.pop("visual_kind", "svg"),
        source_span=kwargs.pop("source_span", [0, 6]),
        **kwargs,
    )


def test_final_contract_sorts_narration_and_emits_each_shared_visual_once() -> None:
    audio = ElementAudioDTO("https://example.test/audio.mp3", "audio", 200, 1)
    shared, trailing, blank = (
        _visual(),
        _visual("trailing"),
        _visual("blank", visual_kind=" "),
    )
    elements = _build(
        av_contract={
            "speakable_segments": [
                {"position": 2, "text": "Second", "source_span": [13, 19]},
                None,
                {"position": "invalid"},
                {"position": 1, "text": "fallback", "source_span": [7, 12]},
                {"position": 3, "text": " "},
            ]
        },
        visual_segments=[shared, trailing, blank],
        audio_by_position={1: audio},
        position_to_segment_id={1: "visual", 2: "visual"},
        element_index_offset=5,
    )
    assert [item.element_type for item in elements] == [
        ElementType.SVG,
        ElementType.TEXT,
        ElementType.TEXT,
        ElementType.SVG,
    ]
    assert [item.element_index for item in elements] == [5, 6, 7, 8]
    assert [item.content_text for item in elements] == ["", "First", "Second", ""]
    assert elements[0].payload.previous_visuals[0].content == "<svg/>"
    assert elements[1].payload.audio == audio
    assert elements[1].audio_url == audio.audio_url
    assert elements[2].payload.audio is None


def test_legacy_segments_use_stored_narration_when_source_span_is_missing() -> None:
    elements = _build(
        visual_segments=[
            _visual(),
            _visual(
                "text",
                visual_kind="",
                source_span=[],
                segment_content=" stored narration ",
            ),
            _visual("empty", visual_kind="", source_span=[], segment_content=" "),
        ]
    )
    assert [item.element_type for item in elements] == [
        ElementType.SVG,
        ElementType.TEXT,
    ]
    assert elements[1].content_text == "stored narration"
    assert elements[1].is_final is True
    assert elements[1].is_speakable is True


def test_speakable_contract_falls_back_to_text_when_source_span_is_unusable() -> None:
    elements = _build(
        av_contract={
            "speakable_segments": [
                {"position": 0, "text": " fallback ", "source_span": [-1, 4]}
            ]
        }
    )
    assert len(elements) == 1
    assert elements[0].content_text == "fallback"


@pytest.mark.parametrize(
    ("kind", "span"), [("", [0, 6]), ("svg", [50, 60]), ("svg", [])]
)
def test_visual_payload_omits_empty_or_unaddressable_visual(
    kind: str, span: list[int]
) -> None:
    assert (
        factory._visuals_from_segment(
            _visual(visual_kind=kind, source_span=span), "<svg/>"
        )
        == []
    )


@pytest.mark.parametrize("answer", ["", "learner answer"])
def test_interaction_snapshot_retains_question_and_answer_without_audio(
    answer: str,
) -> None:
    element = factory._interaction_element_from_record(
        None, "block", "Question?", user_input=answer, role="teacher", element_index=9
    )
    assert element.element_type == ElementType.INTERACTION
    assert element.content_text == "Question?"
    assert element.payload.user_input == (answer or None)
    assert element.payload.audio is None
    assert element.is_marker is True
    assert element.is_renderable is False
    assert element.is_navigable == 0


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        (None, []),
        ([1], []),
        ([None, 2], []),
        (["bad", 2], []),
        ([-1, 2], []),
        ([2, 2], []),
        ([3, 2], []),
        (["1", "3", 8], [1, 3]),
    ],
)
def test_source_span_rejects_invalid_ranges_and_normalizes_integer_strings(
    span: object, expected: list[int]
) -> None:
    assert normalize_source_span(span) == expected


@pytest.mark.parametrize(
    ("text", "span", "expected"),
    [("", [0, 2], ""), ("abc", [], ""), ("abc", [3, 4], ""), ("abc", [1, 99], "bc")],
)
def test_source_slice_clamps_to_available_content(
    text: str, span: list[int], expected: str
) -> None:
    assert slice_source_by_span(text, span) == expected

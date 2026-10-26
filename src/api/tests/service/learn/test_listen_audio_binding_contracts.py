"""Keep delayed and out-of-order audio attached to its intended text element."""

from collections import OrderedDict

import pytest
from flaskr.service.learn import listen_element_audio_binding as binding
from flaskr.service.learn.learn_dtos import ElementAudioDTO, ElementType
from flaskr.service.learn.listen_element_run_state import BlockState, StreamElementState


def _text(number: int = 1, bid: str = "text-1", **kwargs: object) -> StreamElementState:
    return StreamElementState(
        number=number,
        element_bid=bid,
        element_index=number,
        element_type=kwargs.pop("element_type", ElementType.TEXT),
        stream_type="paragraph",
        content_text=kwargs.pop("content_text", "Narration"),
        **kwargs,
    )


def _audio(position: int = 0) -> ElementAudioDTO:
    return ElementAudioDTO("https://example.test/audio.mp3", "audio", 240, position)


@pytest.mark.parametrize(
    ("number", "kind", "matches"),
    [
        (1, None, True),
        ("1", " TEXT ", True),
        (1, "paragraph", True),
        (1, "html", False),
        (2, "text", False),
        (None, "text", False),
        ("invalid", "text", False),
    ],
)
def test_audio_target_requires_matching_text_identity(
    number: object, kind: str | None, matches: bool
) -> None:
    assert (
        binding._stream_element_matches_audio_target(_text(), number, kind) is matches
    )
    assert not binding._stream_element_matches_audio_target(
        _text(element_type=ElementType.HTML), 1, None
    )


def test_pending_explicit_audio_skips_empty_positions_and_claims_only_matching_text() -> (
    None
):
    audio = _audio(2)
    segments = [{"segment_index": 0, "audio_data": "pcm"}]
    state = BlockState(
        "block",
        audio_by_position={2: audio},
        audio_segments_by_position={2: segments},
        pending_stream_audio_target_by_position={
            0: (1, "text"),
            1: (9, "text"),
            2: (1, "text"),
        },
    )
    assert binding._resolve_pending_audio_for_stream_element(state, _text()) == (
        audio,
        segments,
    )
    assert state.audio_target_element_bid_by_position == {2: "text-1"}
    assert state.pending_stream_audio_target_by_position == {1: (9, "text")}
    assert binding._resolve_pending_audio_for_stream_element(
        state, _text(2, "text-2")
    ) == (None, None)


@pytest.mark.parametrize(
    "block_reason", ["visual", "other_target", "claimed", "empty", "ambiguous"]
)
def test_default_audio_is_not_stolen_when_binding_is_unsafe(block_reason: str) -> None:
    state = BlockState("block", audio_by_position={3: _audio(3)})
    target = _text()
    if block_reason == "visual":
        target.element_type = ElementType.HTML
    elif block_reason == "other_target":
        state.pending_stream_audio_target_by_position[3] = (99, "text")
    elif block_reason == "claimed":
        state.audio_target_element_bid_by_position[3] = "other"
    elif block_reason == "empty":
        state.audio_by_position.clear()
        state.audio_segments_by_position[3] = []
    else:
        state.audio_by_position[4] = _audio(4)
    assert binding._resolve_pending_audio_for_stream_element(state, target) == (
        None,
        None,
    )


def test_single_unclaimed_segment_trail_can_bind_before_final_audio_arrives() -> None:
    segments = [{"segment_index": 0, "audio_data": "pcm"}]
    state = BlockState("block", audio_segments_by_position={7: segments})
    assert binding._resolve_pending_audio_for_stream_element(state, _text()) == (
        None,
        segments,
    )
    assert state.audio_target_element_bid_by_position == {7: "text-1"}


def test_explicit_binding_prefers_latest_position_for_same_element() -> None:
    earlier, latest = _audio(0), _audio(3)
    state = BlockState(
        "block",
        audio_by_position={0: earlier, 3: latest},
        audio_target_element_bid_by_position={0: "text-1", 3: "text-1"},
    )
    assert binding._resolve_stream_audio_for_element_bid(state, "text-1") == (
        latest,
        [],
    )
    assert binding._resolve_stream_audio_for_element_bid(state, "absent") == (None, [])


@pytest.mark.parametrize("fallback", [True, False])
@pytest.mark.parametrize("pending", [True, False])
def test_implicit_binding_only_uses_unreserved_single_audio(
    fallback: bool, pending: bool
) -> None:
    audio = _audio()
    state = BlockState("block", audio_by_position={0: audio})
    if fallback:
        state.fallback_element_bid = "text-1"
    else:
        state.stream_elements["text"] = _text()
    if pending:
        state.pending_stream_audio_target_by_position[0] = (9, "text")
    assert binding._resolve_stream_audio_for_element_bid(state, "text-1") == (
        None if pending else audio,
        [],
    )


@pytest.mark.parametrize(
    "kind", ["different_id", "visual", "multiple", "ambiguous_audio"]
)
def test_implicit_audio_binding_rejects_ambiguous_elements(kind: str) -> None:
    state = BlockState("block", audio_by_position={1: _audio(1)})
    state.stream_elements["text"] = _text()
    if kind == "different_id":
        state.stream_elements["text"].element_bid = "other"
    elif kind == "visual":
        state.stream_elements["text"].element_type = ElementType.HTML
    elif kind == "multiple":
        state.stream_elements["second"] = _text(2, "text-2")
    else:
        state.audio_by_position[2] = _audio(2)
    assert binding._resolve_stream_audio_for_element_bid(state, "text-1") == (None, [])


def test_active_stream_version_takes_precedence_over_older_same_number() -> None:
    state = BlockState("block")
    state.stream_elements = OrderedDict(
        old=_text(bid="old"), current=_text(bid="current")
    )
    state.active_stream_element_key_by_number[1] = "current"
    assert (
        binding._resolve_audio_target_element_bid_for_stream_number(
            state, "1", "paragraph"
        )
        == "current"
    )
    state.active_stream_element_key_by_number[1] = "missing"
    assert (
        binding._resolve_audio_target_element_bid_for_stream_number(state, 1, "text")
        == "old"
    )
    assert (
        binding._resolve_audio_target_element_bid_for_stream_number(state, "invalid")
        is None
    )
    assert (
        binding._resolve_audio_target_element_bid_for_stream_number(state, 99) is None
    )


def test_positional_audio_skips_visual_and_blank_elements_and_reuses_latest_text() -> (
    None
):
    state = BlockState(
        "block", raw_content="Narration", fallback_element_bid="fallback"
    )
    state.stream_elements = OrderedDict(
        visual=_text(element_type=ElementType.HTML),
        blank=_text(content_text=" \n"),
        first=_text(bid="first"),
        second=_text(2, "second"),
    )
    assert binding._resolve_audio_target_element_bid(state, 0) == "first"
    assert binding._resolve_audio_target_element_bid(state, 1) == "second"
    assert binding._resolve_audio_target_element_bid(state, 99) == "second"
    state.audio_target_element_bid_by_position[0] = "explicit"
    assert binding._resolve_audio_target_element_bid(state, 0) == "explicit"
    state.pending_stream_audio_target_by_position[1] = (99, "text")
    assert binding._resolve_audio_target_element_bid(state, 1) is None
    state.stream_elements.clear()
    assert binding._resolve_audio_target_element_bid(state, 2) == "fallback"
    state.raw_content = " \n"
    assert binding._resolve_audio_target_element_bid(state, 2) is None

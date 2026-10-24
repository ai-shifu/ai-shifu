"""Verify preview snapshots stay isolated and retire obsolete render elements."""

import pytest
from flask import Flask
from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
from flaskr.service.learn.listen_element_run_state import BlockState, StreamElementState
from flaskr.service.learn.preview_elements import PreviewElementRunAdapter


@pytest.fixture
def adapter() -> PreviewElementRunAdapter:
    return PreviewElementRunAdapter(
        Flask(__name__),
        shifu_bid="course",
        outline_bid="lesson",
        user_bid="teacher",
        run_session_bid="preview",
    )


def _element(bid: str, index: int = 0) -> ElementDTO:
    return ElementDTO(
        element_bid=bid,
        generated_block_bid="block",
        element_index=index,
        role="teacher",
        element_type=ElementType.TEXT,
        element_type_code=213,
        content="Preview text",
        audio_segments=[{"segment_index": 0, "duration_ms": 20}],
    )


def test_preview_storage_and_reads_both_copy_nested_snapshots(
    adapter: PreviewElementRunAdapter,
) -> None:
    element = _element("element")
    adapter._persist_element(element)
    element.content_text = "Mutated producer buffer"
    element.audio_segments[0]["duration_ms"] = 100
    loaded = adapter._load_latest_element_snapshot("element")
    assert loaded.content_text == "Preview text"
    assert loaded.audio_segments[0]["duration_ms"] == 20
    loaded.audio_segments[0]["duration_ms"] = 200
    assert (
        adapter._load_latest_element_snapshot("element").audio_segments[0][
            "duration_ms"
        ]
        == 20
    )
    assert adapter._load_latest_element_snapshot("absent") is None


def test_preview_audio_backfill_updates_only_the_requested_snapshot(
    adapter: PreviewElementRunAdapter,
) -> None:
    adapter._persist_element(_element("first"))
    adapter._persist_element(_element("second", 1))
    adapter._backfill_audio_url("first", "https://example.test/audio.mp3")
    adapter._backfill_audio_url("missing", "https://example.test/ignored.mp3")
    assert (
        adapter._load_latest_element_snapshot("first").audio_url
        == "https://example.test/audio.mp3"
    )
    assert adapter._load_latest_element_snapshot("second").audio_url == ""
    adapter._backfill_audio_url("first", "")
    assert adapter._load_latest_element_snapshot("first").audio_url == ""
    assert adapter._load_latest_element_snapshot("missing") is None


@pytest.mark.parametrize("notify", [False, True])
def test_retiring_preview_fallback_removes_snapshot_and_optionally_notifies_the_client(
    adapter: PreviewElementRunAdapter, notify: bool
) -> None:
    state = BlockState(generated_block_bid="block", fallback_element_bid="fallback")
    adapter._persist_element(_element("fallback"))
    events = list(adapter._retire_fallback_element(state, emit_notification=notify))
    assert adapter._load_latest_element_snapshot("fallback") is None
    assert len(events) == int(notify)
    if notify:
        assert events[0].content.element_bid == "fallback"
        assert events[0].content.is_renderable is False
        assert events[0].content.is_navigable == 0


@pytest.mark.parametrize("notify", [False, True])
def test_retiring_stream_elements_preserves_order_and_unrelated_snapshots(
    adapter: PreviewElementRunAdapter, notify: bool
) -> None:
    state = BlockState(generated_block_bid="block")
    for index, bid in enumerate(("first", "second")):
        adapter._persist_element(_element(bid, index))
        state.stream_elements[bid] = StreamElementState(
            number=index,
            element_bid=bid,
            element_index=index,
            element_type=ElementType.TEXT,
        )
    adapter._persist_element(_element("retained", 2))
    events = list(adapter._retire_stream_elements(state, emit_notification=notify))
    assert adapter._load_latest_element_snapshot("first") is None
    assert adapter._load_latest_element_snapshot("second") is None
    assert adapter._load_latest_element_snapshot("retained") is not None
    if notify:
        assert [event.content.element_bid for event in events] == [
            "first",
            "second",
        ]
        assert [event.content.element_index for event in events] == [0, 1]
        assert all(event.content.is_renderable is False for event in events)
    else:
        assert events == []


def test_empty_preview_retirement_does_not_emit_events(
    adapter: PreviewElementRunAdapter,
) -> None:
    state = BlockState(generated_block_bid="block")
    assert list(adapter._retire_fallback_element(state)) == []
    assert list(adapter._retire_stream_elements(state)) == []

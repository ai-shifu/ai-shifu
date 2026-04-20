from flaskr.service.learn.listen_slide_builder import build_visual_segments_for_block
from flaskr.service.tts.pipeline import build_av_segmentation_contract


def test_build_visual_segments_with_boundary_and_pre_visual_text():
    raw = "Before intro.\n\n<svg><text>Chart</text></svg>\n\nAfter chart."
    contract = build_av_segmentation_contract(raw, "block-1")

    segments, mapping = build_visual_segments_for_block(
        raw_content=raw,
        generated_block_bid="block-1",
        av_contract=contract,
        element_index_offset=5,
    )

    assert len(segments) == 2
    assert mapping.keys() == {0, 1}

    first = segments[0]
    second = segments[1]

    assert first.element_index == 5
    assert first.is_placeholder is False
    assert first.visual_kind == ""
    assert first.segment_type == "markdown"
    assert first.segment_content.startswith("Before intro")

    assert second.element_index == 6
    assert second.is_placeholder is False
    assert second.visual_kind == "svg"
    assert second.segment_type == "markdown"
    assert second.segment_content.startswith("<svg")
    assert second.segment_content.endswith("</svg>")

    assert mapping[0] == first.segment_id
    assert mapping[1] == second.segment_id


def test_build_visual_segments_for_text_only_content():
    raw = "Pure narration without any visual."
    contract = build_av_segmentation_contract(raw, "block-2")

    segments, mapping = build_visual_segments_for_block(
        raw_content=raw,
        generated_block_bid="block-2",
        av_contract=contract,
        element_index_offset=0,
    )

    assert len(segments) == 1
    assert mapping == {0: segments[0].segment_id}
    assert segments[0].is_placeholder is False
    assert segments[0].visual_kind == ""
    assert segments[0].segment_type == "markdown"
    assert segments[0].segment_content == raw
    assert segments[0].source_span == [0, len(raw)]


def test_build_visual_segments_returns_empty_for_non_speakable_content():
    raw = "<svg><text>Only visual</text></svg>"
    contract = build_av_segmentation_contract(raw, "block-3")

    segments, mapping = build_visual_segments_for_block(
        raw_content=raw,
        generated_block_bid="block-3",
        av_contract=contract,
    )

    assert segments == []
    assert mapping == {}

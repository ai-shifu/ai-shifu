from flaskr.service.learn.listen_slide_builder import build_listen_slides_for_block
from flaskr.service.tts.pipeline import build_av_segmentation_contract


def test_build_listen_slides_with_visual_boundary_and_pre_visual_text():
    raw = "Before intro.\n\n<svg><text>Chart</text></svg>\n\nAfter chart."
    contract = build_av_segmentation_contract(raw, "block-1")

    slides, mapping = build_listen_slides_for_block(
        raw_content=raw,
        generated_block_bid="block-1",
        av_contract=contract,
        slide_index_offset=5,
    )

    assert len(slides) == 2
    assert mapping.keys() == {0, 1}

    first_slide = slides[0]
    second_slide = slides[1]

    assert first_slide.slide_index == 5
    assert first_slide.is_placeholder is False
    assert first_slide.visual_kind == ""
    assert first_slide.segment_type == "markdown"
    assert first_slide.segment_content.startswith("Before intro")

    assert second_slide.slide_index == 6
    assert second_slide.is_placeholder is False
    assert second_slide.visual_kind == "svg"
    assert second_slide.segment_type == "markdown"
    assert second_slide.segment_content.startswith("<svg")
    assert second_slide.segment_content.endswith("</svg>")

    assert mapping[0] == first_slide.slide_id
    assert mapping[1] == second_slide.slide_id


def test_build_listen_slides_for_text_only_content_uses_placeholder():
    raw = "Pure narration without any visual."
    contract = build_av_segmentation_contract(raw, "block-2")

    slides, mapping = build_listen_slides_for_block(
        raw_content=raw,
        generated_block_bid="block-2",
        av_contract=contract,
        slide_index_offset=0,
    )

    assert len(slides) == 1
    assert mapping == {0: slides[0].slide_id}
    assert slides[0].is_placeholder is False
    assert slides[0].visual_kind == ""
    assert slides[0].segment_type == "markdown"
    assert slides[0].segment_content == raw
    assert slides[0].source_span == [0, len(raw)]


def test_build_listen_slides_returns_empty_for_non_speakable_content():
    raw = "<svg><text>Only visual</text></svg>"
    contract = build_av_segmentation_contract(raw, "block-3")

    slides, mapping = build_listen_slides_for_block(
        raw_content=raw,
        generated_block_bid="block-3",
        av_contract=contract,
    )

    assert slides == []
    assert mapping == {}

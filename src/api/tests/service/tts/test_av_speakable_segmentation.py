import pytest


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_split_av_speakable_segments_splits_svg_blocks(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = (
        "Before.\n\n"
        '<svg width="800" height="600" xmlns="http://www.w3.org/2000/svg">'
        "<text>Hello</text>"
        "</svg>\n\n"
        "After."
    )

    assert split_av_speakable_segments(text) == ["Before.", "After."]


def test_split_av_speakable_segments_splits_multiple_svg_blocks(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = "A.\n\n<svg><text>1</text></svg>\n\nB.\n\n<svg><text>2</text></svg>\n\nC."

    assert split_av_speakable_segments(text) == ["A.", "B.", "C."]


def test_split_av_speakable_segments_splits_img_tag(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = 'Hello <img src="https://example.com/a.png" /> world.'
    assert split_av_speakable_segments(text) == ["Hello", "world."]


def test_split_av_speakable_segments_splits_markdown_image(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = "Hello ![alt](https://example.com/a.png) world."
    assert split_av_speakable_segments(text) == ["Hello", "world."]


def test_split_av_speakable_segments_treats_fenced_code_as_boundary(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = "Before.\n```\n<svg>inside fence</svg>\n```\nAfter."

    assert split_av_speakable_segments(text) == ["Before.", "After."]


def test_split_av_speakable_segments_splits_markdown_table(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = "Before.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nAfter."

    assert split_av_speakable_segments(text) == ["Before.", "After."]


def test_split_av_speakable_segments_splits_html_table(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = "Before.\n<table><tr><td>1</td></tr></table>\nAfter."
    assert split_av_speakable_segments(text) == ["Before.", "After."]


def test_split_av_speakable_segments_splits_video_tag(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = 'Before.\n<video src="https://example.com/a.mp4"></video>\nAfter.'
    assert split_av_speakable_segments(text) == ["Before.", "After."]


def test_split_av_speakable_segments_splits_iframe_tag(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = 'Before.\n<iframe src="https://player.bilibili.com/player.html?bvid=BV1x84y187yS"></iframe>\nAfter.'
    assert split_av_speakable_segments(text) == ["Before.", "After."]


def test_split_av_speakable_segments_splits_iframe_wrapped_by_fixed_markers(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = (
        '=== <iframe src="https://player.bilibili.com/player.html?bvid=BV1x84y187yS"></iframe> ===\n\n'
        "Hello.\n\n"
        "<svg><text>hi</text></svg>\n\n"
        "After."
    )
    assert split_av_speakable_segments(text) == ["Hello.", "After."]


def test_split_av_speakable_segments_splits_sandbox_html_block(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = "Before.\n<div><div>visual</div></div>\nAfter."
    assert split_av_speakable_segments(text) == ["Before.", "After."]


def test_split_av_speakable_segments_does_not_narrate_sandbox_html_block(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    text = "Before.\n<div><h3>Title</h3><p>Story.</p></div>\nAfter."
    assert split_av_speakable_segments(text) == ["Before.", "After."]


def test_split_av_speakable_segments_returns_single_segment_when_no_boundaries(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import split_av_speakable_segments

    assert split_av_speakable_segments("Hello.") == ["Hello."]


def test_build_av_segmentation_contract_contains_boundaries_and_positions(app):
    _require_app(app)

    from flaskr.service.tts.pipeline import build_av_segmentation_contract

    text = (
        "Intro.\n"
        '<svg width="10" height="10"></svg>\n'
        "After svg.\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n"
        "After table."
    )

    contract = build_av_segmentation_contract(text, "block-1")

    assert "visual_boundaries" in contract
    assert "speakable_segments" in contract
    assert [b["kind"] for b in contract["visual_boundaries"]] == ["svg", "md_table"]
    assert [s["position"] for s in contract["speakable_segments"]] == [0, 1, 2]
    assert [s["after_visual_kind"] for s in contract["speakable_segments"]] == [
        "",
        "svg",
        "md_table",
    ]

import pytest


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_preprocess_for_tts_removes_complete_svg(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = (
        "Before.\n\n"
        '<svg width="800" height="600" xmlns="http://www.w3.org/2000/svg">'
        "<text>Hello</text>"
        "</svg>\n\n"
        "After."
    )
    cleaned = preprocess_for_tts(text)

    assert "Before." in cleaned
    assert "After." in cleaned
    assert "<svg" not in cleaned.lower()
    assert "http://www.w3.org" not in cleaned


def test_preprocess_for_tts_strips_incomplete_svg_tail(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = 'Before.\n\n<svg width="800" height="600" xmlns="http://www.w3.org/2000/svg"'
    cleaned = preprocess_for_tts(text)

    assert cleaned == "Before."
    assert "<svg" not in cleaned.lower()
    assert "http://www.w3.org" not in cleaned


def test_preprocess_for_tts_strips_incomplete_fenced_code(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = "Hello.\n```python\nprint('hi')\n"
    cleaned = preprocess_for_tts(text)

    assert cleaned == "Hello."


def test_preprocess_for_tts_strips_escaped_html_tags(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = "Before &lt;p&gt;Hello&lt;/p&gt; After."
    cleaned = preprocess_for_tts(text)

    assert cleaned == "Before Hello After."
    assert "&lt;" not in cleaned
    assert "<p>" not in cleaned


def test_preprocess_for_tts_strips_double_escaped_html_tags(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = "Before &amp;lt;p&amp;gt;Hello&amp;lt;/p&amp;gt; After."
    cleaned = preprocess_for_tts(text)

    assert cleaned == "Before Hello After."
    assert "&amp;lt;" not in cleaned
    assert "&lt;" not in cleaned


def test_preprocess_for_tts_strips_incomplete_html_tag_tail(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = 'Before.\n\n<p class="x"'
    cleaned = preprocess_for_tts(text)

    assert cleaned == "Before."


def test_preprocess_for_tts_keeps_non_tag_angle_brackets(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = "I love you < 3."
    cleaned = preprocess_for_tts(text)

    assert cleaned == "I love you < 3."


def test_streaming_tts_processor_skips_svg_and_keeps_following_text(app, monkeypatch):
    _require_app(app)

    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )

    captured: list[str] = []

    def _capture_submit(self, text: str):
        captured.append(text)

    monkeypatch.setattr(StreamingTTSProcessor, "_submit_tts_task", _capture_submit)

    processor = StreamingTTSProcessor(
        app=app,
        generated_block_bid="generated_block_bid",
        outline_bid="outline_bid",
        progress_record_bid="progress_record_bid",
        user_bid="user_bid",
        shifu_bid="shifu_bid",
        tts_provider="minimax",
    )

    list(
        processor.process_chunk(
            "I'll create a diagram.\n\n"
            '<svg width="800" xmlns="http://www.w3.org/2000/svg">'
        )
    )
    assert captured == ["I'll create a diagram."]

    list(
        processor.process_chunk(
            "<text>Hello</text></svg>\n\nHello after svg! This should be spoken."
        )
    )

    list(processor.finalize())

    assert any("Hello after svg!" in t for t in captured)
    assert all("http://www.w3.org" not in t for t in captured)


# ---------------------------------------------------------------------------
# Tests for split_text_by_visual_boundaries
# ---------------------------------------------------------------------------


def test_split_visual_text_only(app):
    """Text with no visual elements returns a single segment."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    result = split_text_by_visual_boundaries("Hello world. This is a test.")
    assert result == ["Hello world. This is a test."]


def test_split_visual_text_svg_text(app):
    """Text + SVG + text returns 2 segments."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    text = (
        "Before the chart.\n\n"
        '<svg width="800" height="600"><rect/></svg>\n\n'
        "After the chart."
    )
    result = split_text_by_visual_boundaries(text)
    assert len(result) == 2
    assert "Before the chart." in result[0]
    assert "After the chart." in result[1]
    assert all("<svg" not in s.lower() for s in result)


def test_split_visual_text_svg_text_code_text(app):
    """Text + SVG + text + code block + text returns 3 segments."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    text = (
        "Introduction.\n\n"
        '<svg xmlns="http://www.w3.org/2000/svg"><circle/></svg>\n\n'
        "Middle explanation.\n\n"
        "```python\nprint('hi')\n```\n\n"
        "Final words."
    )
    result = split_text_by_visual_boundaries(text)
    assert len(result) == 3
    assert "Introduction." in result[0]
    assert "Middle explanation." in result[1]
    assert "Final words." in result[2]


def test_split_visual_svg_at_start(app):
    """SVG at the very start skips empty leading segment."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    text = "<svg><rect/></svg>\n\nAfter the svg."
    result = split_text_by_visual_boundaries(text)
    assert len(result) == 1
    assert "After the svg." in result[0]


def test_split_visual_svg_at_end(app):
    """SVG at the very end yields only the leading text."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    text = "Before the svg.\n\n<svg><rect/></svg>"
    result = split_text_by_visual_boundaries(text)
    assert len(result) == 1
    assert "Before the svg." in result[0]


def test_split_visual_consecutive_svgs(app):
    """Consecutive SVGs with no text between them produce no empty segments."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    text = "Start.\n\n<svg><rect/></svg>\n<svg><circle/></svg>\n\nEnd."
    result = split_text_by_visual_boundaries(text)
    assert len(result) == 2
    assert "Start." in result[0]
    assert "End." in result[1]


def test_split_visual_empty_text(app):
    """Empty input returns empty list."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    assert split_text_by_visual_boundaries("") == []
    assert split_text_by_visual_boundaries(None) == []


def test_split_visual_only_visual_elements(app):
    """Input with only visual elements returns empty list."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    text = "<svg><rect/></svg>\n\n```python\ncode\n```"
    result = split_text_by_visual_boundaries(text)
    assert result == []


def test_split_visual_mermaid_block(app):
    """Mermaid diagram is treated as a visual boundary."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    text = (
        "Here is a flowchart.\n\n```mermaid\ngraph TD;\nA-->B;\n```\n\nAs shown above."
    )
    result = split_text_by_visual_boundaries(text)
    assert len(result) == 2
    assert "Here is a flowchart." in result[0]
    assert "As shown above." in result[1]


def test_split_visual_mixed_boundaries(app):
    """Mix of SVG, code block and mermaid all act as boundaries."""
    _require_app(app)
    from flaskr.service.tts import split_text_by_visual_boundaries

    text = (
        "Part one.\n\n"
        "<svg><text>chart</text></svg>\n\n"
        "Part two.\n\n"
        "```mermaid\ngraph LR;\n```\n\n"
        "Part three.\n\n"
        "```js\nconsole.log(1)\n```\n\n"
        "Part four."
    )
    result = split_text_by_visual_boundaries(text)
    assert len(result) == 4
    assert "Part one." in result[0]
    assert "Part two." in result[1]
    assert "Part three." in result[2]
    assert "Part four." in result[3]

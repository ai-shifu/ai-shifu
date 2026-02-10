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

    from flaskr.service.tts.streaming_tts import (
        StreamingTTSProcessor,
        _StreamingTTSPart,
    )

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )

    captured: list[tuple[int, str]] = []

    def _capture_submit(self, text: str):
        captured.append((int(getattr(self, "position", 0) or 0), text))
        # Keep `segment_count` semantics so position advances when a part has
        # speakable text, without actually running background TTS synthesis.
        current = int(getattr(self, "_segment_index", 0) or 0)
        setattr(self, "_segment_index", current + 1)

    monkeypatch.setattr(_StreamingTTSPart, "_submit_tts_task", _capture_submit)

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
    assert captured == [(0, "I'll create a diagram.")]

    list(
        processor.process_chunk(
            "<text>Hello</text></svg>\n\nHello after svg! This should be spoken."
        )
    )

    list(processor.finalize())

    assert any(pos == 1 and "Hello after svg!" in t for pos, t in captured)
    assert all("http://www.w3.org" not in t for _pos, t in captured)

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


def test_preprocess_for_tts_strips_incomplete_markdown_image_tail(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = "Before.\n\n![v2-image](https://picx.zhimg.com/v2-36cc97a3a8ec8942"
    cleaned = preprocess_for_tts(text)

    assert cleaned == "Before."
    assert "picx.zhimg.com" not in cleaned
    assert "![" not in cleaned


def test_preprocess_for_tts_strips_stray_svg_text_elements(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = "Before.\n<text>Hello</text>\nAfter."
    cleaned = preprocess_for_tts(text)

    assert cleaned == "Before.\n\nAfter."
    assert "Hello" not in cleaned


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


def test_streaming_tts_processor_skips_chunked_markdown_image(app, monkeypatch):
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
            "先看这张图：![v2-36cc97a3a8ec8942a57cd2052097b01a_r.jpg](https://picx.zhimg.com/"
        )
    )
    list(
        processor.process_chunk(
            "v2-36cc97a3a8ec8942a57cd2052097b01a_r.jpg?source=2c26e567)\n这是后续讲解。"
        )
    )
    list(processor.finalize())

    assert any("这是后续讲解。" in t for t in captured)
    assert all("picx.zhimg.com" not in t for t in captured)
    assert all("![" not in t for t in captured)


def test_preprocess_for_tts_removes_interaction_block(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    # Real production content: the interaction block leaked into the narrated
    # text element and its options were synthesized as if they were lesson text.
    text = (
        "好，咱们先不急着背，先看看你现在的底子在哪。你心里最没底的是哪一块？\n\n"
        "?[概念还含糊 | 会算但老错 | 几乎空白]"
    )
    cleaned = preprocess_for_tts(text)

    assert "你心里最没底的是哪一块？" in cleaned
    assert "?[" not in cleaned
    assert "概念还含糊" not in cleaned
    assert "几乎空白" not in cleaned


def test_preprocess_for_tts_removes_interaction_block_with_variable(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = "这节讲完了。\n\n?[%{{l04_check}} 概念清楚了 | 会做题了 | 还得再练]"
    cleaned = preprocess_for_tts(text)

    assert "这节讲完了。" in cleaned
    assert "?[" not in cleaned
    assert "l04_check" not in cleaned
    assert "概念清楚了" not in cleaned


def test_preprocess_for_tts_removes_interaction_block_variants(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    for block in (
        "?[下一节//_sys_next_chapter]",
        "?[...填写例子]",
        "?[填写形式]",
        "?[]",
    ):
        cleaned = preprocess_for_tts(f"讲解正文。\n\n{block}")

        assert "讲解正文。" in cleaned
        assert "?[" not in cleaned
        assert "_sys_next_chapter" not in cleaned


def test_preprocess_for_tts_strips_incomplete_interaction_tail(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    # A streaming chunk can end mid-block; half an option list must not be read.
    text = "先摸个底。\n\n?[概念还含糊 | 会算但"
    cleaned = preprocess_for_tts(text)

    assert cleaned == "先摸个底。"
    assert "?[" not in cleaned
    assert "概念还含糊" not in cleaned


def test_preprocess_for_tts_removes_unresolved_variable_placeholders(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    text = "同学 {{sys_user_nickname}} 你好，欢迎回来 %{{preserved}}。"
    cleaned = preprocess_for_tts(text)

    assert "你好" in cleaned
    assert "{{" not in cleaned
    assert "sys_user_nickname" not in cleaned
    assert "preserved" not in cleaned


def test_preprocess_for_tts_keeps_regular_markdown_links(app):
    _require_app(app)

    from flaskr.service.tts import preprocess_for_tts

    # `?[` is MarkdownFlow syntax; a plain markdown link must keep its label.
    text = "详见 [官方文档](https://example.com/docs)。"
    cleaned = preprocess_for_tts(text)

    assert "官方文档" in cleaned
    assert "example.com" not in cleaned

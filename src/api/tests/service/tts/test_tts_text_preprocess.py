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
    from flaskr.service.tts.models import LearnGeneratedAudio

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )

    captured: list[str] = []

    def _capture_submit(self, text: str, *, position: int):
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

    with app.app_context():
        LearnGeneratedAudio.query.delete()


def test_streaming_tts_finalize_persists_and_emits_positioned_audio_in_order(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor
    from flaskr.service.tts.models import LearnGeneratedAudio, AUDIO_STATUS_COMPLETED

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda chunks: b"".join(chunks),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda audio_bytes: len(audio_bytes) * 10,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.upload_audio_to_oss",
        lambda _app, _audio, audio_bid: (f"https://oss/{audio_bid}.mp3", "bucket"),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.record_tts_usage",
        lambda *args, **kwargs: None,
    )

    processor = StreamingTTSProcessor(
        app=app,
        generated_block_bid="generated-block-1",
        outline_bid="outline-1",
        progress_record_bid="progress-1",
        user_bid="user-1",
        shifu_bid="shifu-1",
        tts_provider="minimax",
    )
    processor._buffer = ""
    processor._pending_futures = []
    processor._all_audio_data = [
        (1, 3, b"pos1-a", 100),
        (0, 1, b"pos0-a", 100),
        (1, 4, b"pos1-b", 100),
    ]

    with app.app_context():
        LearnGeneratedAudio.query.delete()
        events = list(processor.finalize())

        emitted_positions = [
            event.content.position
            for event in events
            if event.type == GeneratedType.AUDIO_COMPLETE
        ]
        assert emitted_positions == [0, 1]

        db_rows = (
            LearnGeneratedAudio.query.filter_by(generated_block_bid="generated-block-1")
            .order_by(LearnGeneratedAudio.position.asc())
            .all()
        )
        assert [row.position for row in db_rows] == [0, 1]
        assert all(row.status == AUDIO_STATUS_COMPLETED for row in db_rows)

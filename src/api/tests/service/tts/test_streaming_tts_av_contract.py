import pytest


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_av_streaming_tts_processor_emits_av_contract_in_events(app, monkeypatch):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        AudioSegmentDTO,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.tts.streaming_tts import AVStreamingTTSProcessor

    class _FakeStreamingTTSProcessor:
        def __init__(self, **kwargs):
            self.generated_block_bid = kwargs.get("generated_block_bid", "")
            self.outline_bid = kwargs.get("outline_bid", "")
            self.position = int(kwargs.get("position", 0) or 0)
            self.av_contract = kwargs.get("av_contract")

        def process_chunk(self, chunk):
            if not (chunk or "").strip():
                return
            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    segment_index=0,
                    audio_data="ZmFrZS1hdWRpbw==",
                    duration_ms=100,
                    is_final=False,
                    position=self.position,
                    av_contract=self.av_contract,
                ),
            )

        def finalize(self, commit=True):
            _ = commit
            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=f"https://example.com/{self.position}.mp3",
                    audio_bid=f"audio-{self.position}",
                    duration_ms=100,
                    position=self.position,
                    av_contract=self.av_contract,
                ),
            )

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _FakeStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-1",
        outline_bid="outline-1",
        progress_record_bid="progress-1",
        user_bid="user-1",
        shifu_bid="shifu-1",
        tts_provider="minimax",
        tts_model="test-model",
    )

    events = list(processor.process_chunk("Before.<svg><text>v</text></svg>After."))
    events.extend(list(processor.finalize(commit=False)))

    audio_events = [
        event
        for event in events
        if event.type in (GeneratedType.AUDIO_SEGMENT, GeneratedType.AUDIO_COMPLETE)
    ]
    assert len(audio_events) >= 2
    assert all(getattr(event.content, "av_contract", None) for event in audio_events)

    first_contract = audio_events[0].content.av_contract
    assert first_contract["visual_boundaries"][0]["kind"] == "svg"
    assert [item["position"] for item in first_contract["speakable_segments"]] == [0, 1]


def test_av_streaming_tts_processor_skips_chunked_markdown_image(app, monkeypatch):
    _require_app(app)

    from flaskr.service.tts.streaming_tts import AVStreamingTTSProcessor

    captured_chunks: list[str] = []

    class _CaptureStreamingTTSProcessor:
        def __init__(self, **kwargs):
            _ = kwargs

        def process_chunk(self, chunk):
            if (chunk or "").strip():
                captured_chunks.append(chunk)
            return
            yield

        def finalize(self, commit=True):
            _ = commit
            return
            yield

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _CaptureStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-1",
        outline_bid="outline-1",
        progress_record_bid="progress-1",
        user_bid="user-1",
        shifu_bid="shifu-1",
        tts_provider="minimax",
        tts_model="test-model",
    )

    list(
        processor.process_chunk(
            "前言。![v2-36cc97a3a8ec8942a57cd2052097b01a_r.jpg](https://picx.zhimg.com/v2-36cc97"
        )
    )
    list(
        processor.process_chunk(
            "a3a8ec8942a57cd2052097b01a_r.jpg?source=2c26e567)\n后文。"
        )
    )
    list(processor.finalize(commit=False))

    joined = "\n".join(captured_chunks)
    assert "前言" in joined or "后文" in joined
    assert "picx.zhimg.com" not in joined
    assert "![" not in joined


def test_av_streaming_tts_processor_advances_position_when_segment_has_no_audio(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        AudioCompleteDTO,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.tts.streaming_tts import AVStreamingTTSProcessor

    class _LenGateStreamingTTSProcessor:
        def __init__(self, **kwargs):
            self.generated_block_bid = kwargs.get("generated_block_bid", "")
            self.outline_bid = kwargs.get("outline_bid", "")
            self.position = int(kwargs.get("position", 0) or 0)
            self._buffer = ""

        def process_chunk(self, chunk):
            self._buffer += chunk or ""
            return
            yield

        def finalize(self, commit=True):
            _ = commit
            # Simulate provider behavior: very short text produces no audio completion.
            if len((self._buffer or "").strip()) < 2:
                return
                yield
            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=f"https://example.com/{self.position}.mp3",
                    audio_bid=f"audio-{self.position}",
                    duration_ms=100,
                    position=self.position,
                ),
            )

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _LenGateStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-short-1",
        outline_bid="outline-short-1",
        progress_record_bid="progress-short-1",
        user_bid="user-short-1",
        shifu_bid="shifu-short-1",
        tts_provider="minimax",
        tts_model="test-model",
    )

    # First speakable segment is a single character ("A"), so it produces no audio.
    events = list(processor.process_chunk("A<svg><text>v</text></svg>After visual."))
    events.extend(list(processor.finalize(commit=False)))

    audio_complete = [
        event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
    ]
    assert len(audio_complete) == 1
    assert audio_complete[0].content.position == 1


def test_av_streaming_tts_processor_never_emits_new_slide_event(app, monkeypatch):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        AudioSegmentDTO,
        GeneratedType,
        RunMarkdownFlowDTO,
    )
    from flaskr.service.tts.streaming_tts import AVStreamingTTSProcessor

    class _FakeStreamingTTSProcessor:
        def __init__(self, **kwargs):
            self.generated_block_bid = kwargs.get("generated_block_bid", "")
            self.outline_bid = kwargs.get("outline_bid", "")
            self.position = int(kwargs.get("position", 0) or 0)

        def process_chunk(self, chunk):
            if not (chunk or "").strip():
                return
            yield RunMarkdownFlowDTO(
                outline_bid=self.outline_bid,
                generated_block_bid=self.generated_block_bid,
                type=GeneratedType.AUDIO_SEGMENT,
                content=AudioSegmentDTO(
                    segment_index=0,
                    audio_data="ZmFrZS1hdWRpbw==",
                    duration_ms=100,
                    is_final=False,
                    position=self.position,
                ),
            )

        def finalize(self, commit=True):
            _ = commit
            return
            yield

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _FakeStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-contract-1",
        outline_bid="outline-contract-1",
        progress_record_bid="progress-contract-1",
        user_bid="user-contract-1",
        shifu_bid="shifu-contract-1",
        tts_provider="minimax",
        tts_model="test-model",
    )

    events = list(
        processor.process_chunk(
            "Narration only. This sentence is intentionally longer than tail."
        )
    )
    events.extend(list(processor.finalize(commit=False)))

    assert "new_slide" not in {event.type.value for event in events}


def test_av_streaming_tts_processor_updates_next_slide_index_from_contract(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.service.tts.streaming_tts import AVStreamingTTSProcessor

    class _NoopStreamingTTSProcessor:
        def __init__(self, **kwargs):
            _ = kwargs

        def process_chunk(self, chunk):
            _ = chunk
            return
            yield

        def finalize(self, commit=True):
            _ = commit
            return
            yield

    class _SlideStub:
        def __init__(self, index: int):
            self.slide_index = index

    def _fake_build_listen_slides_for_block(**kwargs):
        _ = kwargs
        return [_SlideStub(7)], {1: "slide-1"}

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _NoopStreamingTTSProcessor,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_listen_slides_for_block",
        _fake_build_listen_slides_for_block,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-contract-2",
        outline_bid="outline-contract-2",
        progress_record_bid="progress-contract-2",
        user_bid="user-contract-2",
        shifu_bid="shifu-contract-2",
        tts_provider="minimax",
        tts_model="test-model",
    )

    list(processor.process_chunk("Only visual <svg><text>v</text></svg>"))
    list(processor.finalize(commit=False))

    assert processor.next_slide_index >= 8

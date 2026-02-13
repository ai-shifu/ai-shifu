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

        def finalize_preview(self):
            yield from self.finalize(commit=False)

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

        def finalize_preview(self):
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


def test_av_streaming_tts_processor_emits_new_slide_before_audio(app, monkeypatch):
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

        def finalize_preview(self):
            yield from self.finalize(commit=False)

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _FakeStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-2",
        outline_bid="outline-2",
        progress_record_bid="progress-2",
        user_bid="user-2",
        shifu_bid="shifu-2",
        tts_provider="minimax",
        tts_model="test-model",
    )

    events = list(processor.process_chunk("Before.<svg><text>v</text></svg>After."))
    events.extend(list(processor.finalize(commit=False)))

    emitted_slide_ids: set[str] = set()
    first_audio_index_by_slide: dict[str, int] = {}
    new_slide_index_by_slide: dict[str, int] = {}

    for idx, event in enumerate(events):
        if event.type == GeneratedType.NEW_SLIDE:
            slide_id = event.content.slide_id
            emitted_slide_ids.add(slide_id)
            new_slide_index_by_slide[slide_id] = idx
            continue
        if event.type not in (
            GeneratedType.AUDIO_SEGMENT,
            GeneratedType.AUDIO_COMPLETE,
        ):
            continue
        slide_id = getattr(event.content, "slide_id", None)
        assert slide_id
        first_audio_index_by_slide.setdefault(slide_id, idx)

    assert emitted_slide_ids
    assert emitted_slide_ids == set(first_audio_index_by_slide.keys())
    for slide_id, audio_idx in first_audio_index_by_slide.items():
        assert new_slide_index_by_slide[slide_id] < audio_idx

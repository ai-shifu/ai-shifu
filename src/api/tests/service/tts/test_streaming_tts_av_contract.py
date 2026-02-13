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

        def finalize_preview(self):
            yield from self.finalize(commit=False)

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

    emitted_slides = [
        event for event in events if event.type == GeneratedType.NEW_SLIDE
    ]
    assert len(emitted_slides) == 1
    assert emitted_slides[0].content.visual_kind == "svg"


def test_av_streaming_tts_processor_emits_run_start_slide_once(app, monkeypatch):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import GeneratedType
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

        def finalize_preview(self):
            return
            yield

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _NoopStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-start-1",
        outline_bid="outline-start-1",
        progress_record_bid="progress-start-1",
        user_bid="user-start-1",
        shifu_bid="shifu-start-1",
        tts_provider="minimax",
        tts_model="test-model",
    )

    first = list(processor.emit_run_start_slide())
    second = list(processor.emit_run_start_slide())

    assert len(first) == 1
    assert first[0].type == GeneratedType.NEW_SLIDE
    assert first[0].content.is_placeholder is True
    assert first[0].content.audio_position == 0
    assert second == []


def test_av_streaming_tts_processor_emits_visual_slide_on_boundary_without_audio(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import GeneratedType
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

        def finalize_preview(self):
            return
            yield

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _NoopStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-visual-1",
        outline_bid="outline-visual-1",
        progress_record_bid="progress-visual-1",
        user_bid="user-visual-1",
        shifu_bid="shifu-visual-1",
        tts_provider="minimax",
        tts_model="test-model",
    )

    events = list(processor.process_chunk("<svg><text>v</text></svg>"))
    events.extend(list(processor.finalize(commit=False)))

    emitted_slides = [
        event for event in events if event.type == GeneratedType.NEW_SLIDE
    ]
    assert len(emitted_slides) == 1
    assert emitted_slides[0].content.visual_kind == "svg"
    assert emitted_slides[0].content.is_placeholder is False
    assert emitted_slides[0].content.segment_content == ""


def test_av_streaming_tts_processor_emits_head_then_full_slide_for_incomplete_boundary(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import GeneratedType
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

        def finalize_preview(self):
            return
            yield

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _NoopStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-incomplete-1",
        outline_bid="outline-incomplete-1",
        progress_record_bid="progress-incomplete-1",
        user_bid="user-incomplete-1",
        shifu_bid="shifu-incomplete-1",
        tts_provider="minimax",
        tts_model="test-model",
    )

    first_events = list(processor.process_chunk("<svg"))
    first_slides = [
        event for event in first_events if event.type == GeneratedType.NEW_SLIDE
    ]
    assert len(first_slides) == 1
    assert first_slides[0].content.visual_kind == "svg"
    assert first_slides[0].content.is_placeholder is True
    assert first_slides[0].content.segment_content == ""

    second_events = list(processor.process_chunk("><text>v</text></svg>"))
    emitted_slides = [
        event for event in second_events if event.type == GeneratedType.NEW_SLIDE
    ]
    assert len(emitted_slides) == 1
    assert emitted_slides[0].content.visual_kind == "svg"
    assert emitted_slides[0].content.segment_content == ""
    assert emitted_slides[0].content.is_placeholder is False
    assert emitted_slides[0].content.slide_id == first_slides[0].content.slide_id


def test_av_streaming_tts_processor_detects_truncated_sandbox_start(app, monkeypatch):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import GeneratedType
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

        def finalize_preview(self):
            return
            yield

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _NoopStreamingTTSProcessor,
    )

    processor = AVStreamingTTSProcessor(
        app=app,
        generated_block_bid="gen-incomplete-sandbox-1",
        outline_bid="outline-incomplete-sandbox-1",
        progress_record_bid="progress-incomplete-sandbox-1",
        user_bid="user-incomplete-sandbox-1",
        shifu_bid="shifu-incomplete-sandbox-1",
        tts_provider="minimax",
        tts_model="test-model",
    )

    # First chunk contains only a truncated sandbox start token (`<div`).
    first_events = list(processor.process_chunk("<div"))
    first_slides = [
        event for event in first_events if event.type == GeneratedType.NEW_SLIDE
    ]
    assert len(first_slides) == 1
    assert first_slides[0].content.visual_kind == "sandbox"
    assert first_slides[0].content.is_placeholder is True
    assert first_slides[0].content.segment_content == ""

    second_events = list(processor.process_chunk(' style="x">X</div>'))
    emitted_slides = [
        event for event in second_events if event.type == GeneratedType.NEW_SLIDE
    ]
    assert len(emitted_slides) == 1
    assert emitted_slides[0].content.visual_kind == "sandbox"
    assert emitted_slides[0].content.segment_content == ""
    assert emitted_slides[0].content.is_placeholder is False
    assert emitted_slides[0].content.slide_id == first_slides[0].content.slide_id


def test_av_streaming_tts_processor_never_emits_full_segment_content_in_new_slide(
    app, monkeypatch
):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import (
        AudioSegmentDTO,
        GeneratedType,
        NewSlideDTO,
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

        def finalize_preview(self):
            return
            yield

    def _fake_build_listen_slides_for_block(**kwargs):
        generated_block_bid = kwargs.get("generated_block_bid", "")
        slide = NewSlideDTO(
            slide_id="slide-contract-1",
            generated_block_bid=generated_block_bid,
            slide_index=0,
            audio_position=0,
            visual_kind="svg",
            segment_type="markdown",
            segment_content="<svg><text>large payload</text></svg>",
            source_span=[0, 36],
            is_placeholder=False,
        )
        return [slide], {0: "slide-contract-1"}

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.StreamingTTSProcessor",
        _FakeStreamingTTSProcessor,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_listen_slides_for_block",
        _fake_build_listen_slides_for_block,
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
    slide_events = [event for event in events if event.type == GeneratedType.NEW_SLIDE]

    assert len(slide_events) == 1
    assert slide_events[0].content.slide_id == "slide-contract-1"
    assert slide_events[0].content.segment_content == ""

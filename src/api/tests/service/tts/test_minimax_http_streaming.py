import json
from types import SimpleNamespace

import pytest


class _FakeResponse:
    def __init__(self, lines, *, status_error=None):
        self._lines = lines
        self._status_error = status_error
        self.headers = {"content-type": "text/event-stream"}

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def iter_lines(self, decode_unicode=True):
        _ = decode_unicode
        yield from self._lines


def _sse_line(payload):
    return f"data: {json.dumps(payload)}"


def test_minimax_http_streaming_parses_audio_and_final_subtitles(monkeypatch):
    from flaskr.api.tts.base import AudioSettings, VoiceSettings
    from flaskr.api.tts.minimax_provider import MinimaxTTSProvider

    config = {
        "MINIMAX_API_KEY": "test-key",
        "MINIMAX_GROUP_ID": "test-group",
        "MINIMAX_TTS_RPM_LIMIT": 60,
        "MINIMAX_TTS_QUEUE_MAX_WAIT_SECONDS": 10,
    }
    gate_calls = []
    post_calls = []

    monkeypatch.setattr(
        "flaskr.api.tts.minimax_provider.get_config",
        lambda key: config.get(key, ""),
    )
    monkeypatch.setattr(
        "flaskr.api.tts.minimax_provider.acquire_tts_rpm_slot",
        lambda **kwargs: gate_calls.append(kwargs),
    )

    def _fake_post(url, **kwargs):
        post_calls.append((url, kwargs))
        return _FakeResponse(
            [
                _sse_line(
                    {
                        "data": {
                            "audio": "6161",
                            "status": 1,
                            "subtitle": {
                                "text": "First.",
                                "time_begin": 0,
                                "time_end": 500,
                            },
                        },
                        "trace_id": "trace-1",
                        "base_resp": {"status_code": 0, "status_msg": ""},
                    }
                ),
                _sse_line(
                    {
                        "data": {
                            "audio": "",
                            "status": 2,
                            "subtitles": [
                                {
                                    "text": "First.",
                                    "time_begin": 0,
                                    "time_end": 500,
                                }
                            ],
                        },
                        "extra_info": {
                            "audio_length": 500,
                            "audio_sample_rate": 32000,
                            "usage_characters": 6,
                            "audio_format": "mp3",
                        },
                        "trace_id": "trace-1",
                        "base_resp": {"status_code": 0, "status_msg": "success"},
                    }
                ),
            ]
        )

    monkeypatch.setattr("flaskr.api.tts.minimax_provider.requests.post", _fake_post)

    chunks = list(
        MinimaxTTSProvider().stream_synthesize(
            text="First.",
            voice_settings=VoiceSettings(voice_id="male-qn-qingse"),
            audio_settings=AudioSettings(format="mp3", sample_rate=32000),
            model="speech-2.8-turbo",
        )
    )

    assert [chunk.audio_data for chunk in chunks] == [b"aa", b""]
    assert chunks[0].subtitles[0]["text"] == "First."
    assert chunks[-1].is_final is True
    assert chunks[-1].duration_ms == 500
    assert chunks[-1].word_count == 6
    assert chunks[-1].subtitles[0]["text"] == "First."
    assert gate_calls[0]["rpm_limit"] == 60
    assert post_calls[0][0].endswith("GroupId=test-group")
    assert post_calls[0][1]["stream"] is True
    assert post_calls[0][1]["json"]["stream"] is True
    assert post_calls[0][1]["json"]["subtitle_enable"] is True
    assert post_calls[0][1]["json"]["stream_options"] == {
        "exclude_aggregated_audio": True
    }


def test_minimax_http_streaming_raises_on_business_error(monkeypatch):
    from flaskr.api.tts.minimax_provider import MinimaxTTSProvider

    monkeypatch.setattr(
        "flaskr.api.tts.minimax_provider.get_config",
        lambda key: "test-key" if key == "MINIMAX_API_KEY" else "",
    )
    monkeypatch.setattr(
        "flaskr.api.tts.minimax_provider.acquire_tts_rpm_slot",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.api.tts.minimax_provider.requests.post",
        lambda *args, **kwargs: _FakeResponse(
            [
                _sse_line(
                    {
                        "data": None,
                        "trace_id": "trace-err",
                        "base_resp": {
                            "status_code": 1002,
                            "status_msg": "rate limited",
                        },
                    }
                )
            ]
        ),
    )

    with pytest.raises(ValueError, match="1002"):
        list(MinimaxTTSProvider().stream_synthesize("hello"))


def test_streaming_tts_minimax_http_stream_sends_one_request_on_finalize(
    monkeypatch,
):
    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    calls = []

    class _FakeMinimaxProvider:
        def stream_synthesize(self, **kwargs):
            calls.append(kwargs["text"])
            yield SimpleNamespace(
                audio_data=b"fake-mp3",
                is_final=False,
                duration_ms=0,
                format="mp3",
                word_count=0,
                subtitles=[
                    {"text": "First sentence.", "time_begin": 0, "time_end": 400},
                    {"text": "Second sentence.", "time_begin": 500, "time_end": 1000},
                ],
            )
            yield SimpleNamespace(
                audio_data=b"",
                is_final=True,
                duration_ms=1000,
                format="mp3",
                word_count=10,
                subtitles=[],
            )

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
        lambda _provider: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.MinimaxTTSProvider", _FakeMinimaxProvider
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.export_audio_range_best_effort",
        lambda audio_data, **kwargs: (
            (audio_data, int(kwargs.get("end_ms") or 1000))
            if kwargs.get("end_ms") is not None
            else (b"", 0)
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda parts, output_format="mp3": b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda _audio, format="mp3": 1000,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_completed_audio_record",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.save_audio_record",
        lambda _record, commit=True: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_handler.upload_audio_to_oss",
        lambda _app, _audio, audio_bid: (f"https://example.com/{audio_bid}.mp3", "b"),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
        lambda **_kwargs: None,
    )

    app = SimpleNamespace()
    processor = StreamingTTSProcessor(
        app=app,
        generated_block_bid="generated-http-stream",
        outline_bid="outline",
        progress_record_bid="progress",
        user_bid="user",
        shifu_bid="shifu",
        tts_provider="minimax",
        tts_model="speech-2.8-turbo",
        stream_element_number=7,
        stream_element_type="text",
    )

    assert list(processor.process_chunk("First sentence. ")) == []
    assert calls == []
    assert list(processor.process_chunk("Second sentence.")) == []
    assert calls == []

    events = list(processor.finalize(commit=False))
    audio_segments = [
        event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
    ]
    audio_complete = [
        event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
    ]

    assert calls == ["First sentence.\nSecond sentence."]
    assert len(audio_segments) == 1
    assert audio_segments[0].content.stream_element_number == 7
    assert audio_segments[0].content.stream_element_type == "text"
    assert [cue.text for cue in audio_segments[0].content.subtitle_cues] == [
        "First sentence.",
        "Second sentence.",
    ]
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_segments[0].content.subtitle_cues
    ] == [
        (0, 400),
        (500, 1000),
    ]
    assert len(audio_complete) == 1
    assert [cue.text for cue in audio_complete[0].content.subtitle_cues] == [
        "First sentence.",
        "Second sentence.",
    ]
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_complete[0].content.subtitle_cues
    ] == [
        (0, 400),
        (500, 1000),
    ]


def test_streaming_tts_minimax_http_stream_falls_back_for_partial_subtitles(
    monkeypatch,
):
    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    class _FakeMinimaxProvider:
        def stream_synthesize(self, **_kwargs):
            yield SimpleNamespace(
                audio_data=b"fake-mp3",
                is_final=False,
                duration_ms=0,
                format="mp3",
                word_count=0,
                subtitles=[],
            )
            yield SimpleNamespace(
                audio_data=b"",
                is_final=True,
                duration_ms=1000,
                format="mp3",
                word_count=10,
                subtitles=[
                    {"text": "First sentence.", "time_begin": 0, "time_end": 400}
                ],
            )

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
        lambda _provider: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.MinimaxTTSProvider", _FakeMinimaxProvider
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.export_audio_range_best_effort",
        lambda audio_data, **kwargs: (
            (audio_data, int(kwargs.get("end_ms") or 1000))
            if kwargs.get("end_ms") is not None
            else (b"", 0)
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda parts, output_format="mp3": b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda _audio, format="mp3": 1000,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_completed_audio_record",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.save_audio_record",
        lambda _record, commit=True: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_handler.upload_audio_to_oss",
        lambda _app, _audio, audio_bid: (f"https://example.com/{audio_bid}.mp3", "b"),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
        lambda **_kwargs: None,
    )

    processor = StreamingTTSProcessor(
        app=SimpleNamespace(),
        generated_block_bid="generated-http-stream-fallback",
        outline_bid="outline",
        progress_record_bid="progress",
        user_bid="user",
        shifu_bid="shifu",
        tts_provider="minimax",
        tts_model="speech-2.8-turbo",
    )
    assert list(processor.process_chunk("First sentence. Second sentence.")) == []

    events = list(processor.finalize(commit=False))
    audio_segments = [
        event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
    ]
    audio_complete = [
        event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
    ]

    assert len(audio_segments) == 1
    assert [cue.text for cue in audio_segments[0].content.subtitle_cues] == [
        "First sentence.",
    ]
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_segments[0].content.subtitle_cues
    ] == [
        (0, 400),
    ]
    assert len(audio_complete) == 1
    assert [cue.text for cue in audio_complete[0].content.subtitle_cues] == [
        "First sentence.",
        "Second sentence.",
    ]
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_complete[0].content.subtitle_cues
    ] == [
        (0, 484),
        (484, 1000),
    ]


def test_streaming_tts_minimax_http_stream_buffers_audio_until_provider_subtitles(
    monkeypatch,
):
    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    class _FakeMinimaxProvider:
        def stream_synthesize(self, **_kwargs):
            yield SimpleNamespace(
                audio_data=b"fake-mp3-part-1",
                is_final=False,
                duration_ms=0,
                format="mp3",
                word_count=0,
                subtitles=[],
            )
            yield SimpleNamespace(
                audio_data=b"",
                is_final=True,
                duration_ms=3000,
                format="mp3",
                word_count=10,
                subtitles=[
                    {"text": "First sentence.", "time_begin": 0, "time_end": 1500},
                    {
                        "text": "Second sentence.",
                        "time_begin": 1500,
                        "time_end": 3000,
                    },
                ],
            )

    export_calls = []

    def _fake_export(_audio_data, **kwargs):
        export_calls.append(kwargs)
        end_ms = kwargs.get("end_ms")
        start_ms = int(kwargs.get("start_ms") or 0)
        if end_ms is None:
            return b"early-piece", 1500
        return b"final-piece", int(end_ms or 0) - start_ms

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
        lambda _provider: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.MinimaxTTSProvider", _FakeMinimaxProvider
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.export_audio_range_best_effort",
        _fake_export,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda parts, output_format="mp3": b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda _audio, format="mp3": 3000,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_completed_audio_record",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.save_audio_record",
        lambda _record, commit=True: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_handler.upload_audio_to_oss",
        lambda _app, _audio, audio_bid: (f"https://example.com/{audio_bid}.mp3", "b"),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
        lambda **_kwargs: None,
    )

    processor = StreamingTTSProcessor(
        app=SimpleNamespace(),
        generated_block_bid="generated-http-stream-progress-subtitles",
        outline_bid="outline",
        progress_record_bid="progress",
        user_bid="user",
        shifu_bid="shifu",
        tts_provider="minimax",
        tts_model="speech-2.8-turbo",
    )
    assert list(processor.process_chunk("First sentence. Second sentence.")) == []

    events = list(processor.finalize(commit=False))
    audio_segments = [
        event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
    ]
    audio_complete = [
        event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
    ]

    assert len(audio_segments) == 1
    assert [cue.text for cue in audio_segments[0].content.subtitle_cues] == [
        "First sentence.",
        "Second sentence.",
    ]
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_segments[0].content.subtitle_cues
    ] == [
        (0, 1500),
        (1500, 3000),
    ]
    assert len(export_calls) == 1
    assert export_calls[0]["end_ms"] == 3000
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_complete[0].content.subtitle_cues
    ] == [
        (0, 1500),
        (1500, 3000),
    ]


def test_streaming_tts_minimax_http_stream_offsets_later_requests_by_provider_end(
    monkeypatch,
):
    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    calls = []
    saved_records = []

    class _FakeMinimaxProvider:
        def stream_synthesize(self, **kwargs):
            calls.append(kwargs["text"])
            if kwargs["text"] == "First sentence.":
                yield SimpleNamespace(
                    audio_data=b"first-mp3",
                    is_final=True,
                    duration_ms=1000,
                    format="mp3",
                    word_count=2,
                    subtitles=[
                        {
                            "text": "First sentence.",
                            "time_begin": 0,
                            "time_end": 800,
                        }
                    ],
                )
                return
            yield SimpleNamespace(
                audio_data=b"second-mp3",
                is_final=True,
                duration_ms=1200,
                format="mp3",
                word_count=2,
                subtitles=[
                    {
                        "text": "Second sentence.",
                        "time_begin": 0,
                        "time_end": 900,
                    }
                ],
            )

    def _fake_export(audio_data, **kwargs):
        end_ms = int(kwargs.get("end_ms") or 0)
        start_ms = int(kwargs.get("start_ms") or 0)
        return audio_data, end_ms - start_ms

    def _fake_build_completed_audio_record(**kwargs):
        saved_records.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
        lambda _provider: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.MinimaxTTSProvider", _FakeMinimaxProvider
    )
    monkeypatch.setattr(
        StreamingTTSProcessor,
        "_split_minimax_http_stream_text",
        lambda _self, _text: ["First sentence.", "Second sentence."],
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.export_audio_range_best_effort",
        _fake_export,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda parts, output_format="mp3": b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda _audio, format="mp3": 2200,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_completed_audio_record",
        _fake_build_completed_audio_record,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.save_audio_record",
        lambda _record, commit=True: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_handler.upload_audio_to_oss",
        lambda _app, _audio, audio_bid: (f"https://example.com/{audio_bid}.mp3", "b"),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
        lambda **_kwargs: None,
    )

    processor = StreamingTTSProcessor(
        app=SimpleNamespace(),
        generated_block_bid="generated-http-stream-provider-offset",
        outline_bid="outline",
        progress_record_bid="progress",
        user_bid="user",
        shifu_bid="shifu",
        tts_provider="minimax",
        tts_model="speech-2.8-turbo",
    )
    assert list(processor.process_chunk("First sentence. Second sentence.")) == []

    events = list(processor.finalize(commit=False))
    audio_segments = [
        event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
    ]
    audio_complete = [
        event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
    ]

    assert calls == ["First sentence.", "Second sentence."]
    assert len(audio_segments) == 2
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_segments[0].content.subtitle_cues
    ] == [
        ("First sentence.", 0, 800),
    ]
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_segments[1].content.subtitle_cues
    ] == [
        ("First sentence.", 0, 800),
        ("Second sentence.", 800, 1700),
    ]
    assert len(audio_complete) == 1
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_complete[0].content.subtitle_cues
    ] == [
        ("First sentence.", 0, 800),
        ("Second sentence.", 800, 1700),
    ]
    assert [
        (cue["text"], cue["start_ms"], cue["end_ms"])
        for cue in saved_records[0]["subtitle_cues"]
    ] == [
        ("First sentence.", 0, 800),
        ("Second sentence.", 800, 1700),
    ]


def test_streaming_tts_minimax_http_stream_uses_provider_progress_cues_without_stretch(
    monkeypatch,
):
    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    class _FakeMinimaxProvider:
        def stream_synthesize(self, **_kwargs):
            yield SimpleNamespace(
                audio_data=b"fake-mp3-part-1",
                is_final=False,
                duration_ms=0,
                format="mp3",
                word_count=0,
                subtitles=[
                    {"text": "First sentence.", "time_begin": 0, "time_end": 600}
                ],
            )
            yield SimpleNamespace(
                audio_data=b"",
                is_final=True,
                duration_ms=2000,
                format="mp3",
                word_count=10,
                subtitles=[
                    {"text": "First sentence.", "time_begin": 0, "time_end": 700},
                    {
                        "text": "Second sentence.",
                        "time_begin": 900,
                        "time_end": 2000,
                    },
                ],
            )

    def _fake_export(_audio_data, **kwargs):
        end_ms = kwargs.get("end_ms")
        start_ms = int(kwargs.get("start_ms") or 0)
        if end_ms is None:
            return b"early-piece", 1600
        return b"final-piece", int(end_ms or 0) - start_ms

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
        lambda _provider: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.MinimaxTTSProvider", _FakeMinimaxProvider
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.export_audio_range_best_effort",
        _fake_export,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda parts, output_format="mp3": b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda _audio, format="mp3": 2000,
    )
    saved_records = []

    def _fake_build_completed_audio_record(**kwargs):
        saved_records.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_completed_audio_record",
        _fake_build_completed_audio_record,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.save_audio_record",
        lambda _record, commit=True: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_handler.upload_audio_to_oss",
        lambda _app, _audio, audio_bid: (f"https://example.com/{audio_bid}.mp3", "b"),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
        lambda **_kwargs: None,
    )

    processor = StreamingTTSProcessor(
        app=SimpleNamespace(),
        generated_block_bid="generated-http-stream-progress-fallback",
        outline_bid="outline",
        progress_record_bid="progress",
        user_bid="user",
        shifu_bid="shifu",
        tts_provider="minimax",
        tts_model="speech-2.8-turbo",
    )
    assert list(processor.process_chunk("First sentence. Second sentence.")) == []

    events = list(processor.finalize(commit=False))
    audio_segments = [
        event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
    ]
    audio_complete = [
        event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
    ]

    assert len(audio_segments) == 2
    assert [cue.text for cue in audio_segments[0].content.subtitle_cues] == [
        "First sentence.",
    ]
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_segments[0].content.subtitle_cues
    ] == [
        (0, 600),
    ]
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_segments[1].content.subtitle_cues
    ] == [
        (0, 700),
        (900, 2000),
    ]
    assert len(audio_complete) == 1
    assert [cue.text for cue in audio_complete[0].content.subtitle_cues] == [
        "First sentence.",
        "Second sentence.",
    ]
    assert [
        (cue.start_ms, cue.end_ms) for cue in audio_complete[0].content.subtitle_cues
    ] == [
        (0, 700),
        (900, 2000),
    ]
    assert len(saved_records) == 1
    assert [
        (cue["start_ms"], cue["end_ms"]) for cue in saved_records[0]["subtitle_cues"]
    ] == [
        (0, 700),
        (900, 2000),
    ]


def test_streaming_tts_minimax_http_stream_keeps_provider_middle_cue_timing(
    monkeypatch,
):
    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    saved_records = []

    class _FakeMinimaxProvider:
        def stream_synthesize(self, **_kwargs):
            yield SimpleNamespace(
                audio_data=b"fake-mp3-part-1",
                is_final=False,
                duration_ms=0,
                format="mp3",
                word_count=0,
                subtitles=[
                    {"text": "First sentence.", "time_begin": 0, "time_end": 700},
                    {
                        "text": "Second sentence.",
                        "time_begin": 900,
                        "time_end": 1900,
                    },
                ],
            )
            yield SimpleNamespace(
                audio_data=b"",
                is_final=True,
                duration_ms=5400,
                format="mp3",
                word_count=15,
                subtitles=[
                    {"text": "First sentence.", "time_begin": 0, "time_end": 700},
                    {
                        "text": "Second sentence.",
                        "time_begin": 900,
                        "time_end": 2100,
                    },
                    {
                        "text": "Third sentence.",
                        "time_begin": 2300,
                        "time_end": 5400,
                    },
                ],
            )

    def _fake_export(_audio_data, **kwargs):
        end_ms = kwargs.get("end_ms")
        start_ms = int(kwargs.get("start_ms") or 0)
        if end_ms is None:
            return b"early-piece", 1900
        return b"final-piece", int(end_ms or 0) - start_ms

    def _fake_build_completed_audio_record(**kwargs):
        saved_records.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
        lambda _provider: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.MinimaxTTSProvider", _FakeMinimaxProvider
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.export_audio_range_best_effort",
        _fake_export,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda parts, output_format="mp3": b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda _audio, format="mp3": 5400,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_completed_audio_record",
        _fake_build_completed_audio_record,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.save_audio_record",
        lambda _record, commit=True: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_handler.upload_audio_to_oss",
        lambda _app, _audio, audio_bid: (f"https://example.com/{audio_bid}.mp3", "b"),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
        lambda **_kwargs: None,
    )

    processor = StreamingTTSProcessor(
        app=SimpleNamespace(),
        generated_block_bid="generated-http-stream-middle-live-cue",
        outline_bid="outline",
        progress_record_bid="progress",
        user_bid="user",
        shifu_bid="shifu",
        tts_provider="minimax",
        tts_model="speech-2.8-turbo",
    )
    assert (
        list(
            processor.process_chunk("First sentence. Second sentence. Third sentence.")
        )
        == []
    )

    events = list(processor.finalize(commit=False))
    audio_segments = [
        event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
    ]
    audio_complete = [
        event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
    ]

    assert len(audio_segments) == 2
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_segments[0].content.subtitle_cues
    ] == [
        ("First sentence.", 0, 700),
        ("Second sentence.", 900, 1900),
    ]
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_segments[1].content.subtitle_cues
    ] == [
        ("First sentence.", 0, 700),
        ("Second sentence.", 900, 2100),
        ("Third sentence.", 2300, 5400),
    ]
    assert len(audio_complete) == 1
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_complete[0].content.subtitle_cues
    ] == [
        ("First sentence.", 0, 700),
        ("Second sentence.", 900, 2100),
        ("Third sentence.", 2300, 5400),
    ]
    assert len(saved_records) == 1
    assert [
        (cue["text"], cue["start_ms"], cue["end_ms"])
        for cue in saved_records[0]["subtitle_cues"]
    ] == [
        ("First sentence.", 0, 700),
        ("Second sentence.", 900, 2100),
        ("Third sentence.", 2300, 5400),
    ]


def test_streaming_tts_minimax_http_stream_updates_same_count_provider_cues(
    monkeypatch,
):
    from flaskr.service.learn.learn_dtos import GeneratedType
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    saved_records = []

    class _FakeMinimaxProvider:
        def stream_synthesize(self, **_kwargs):
            yield SimpleNamespace(
                audio_data=b"fake-mp3-part-1",
                is_final=False,
                duration_ms=0,
                format="mp3",
                word_count=0,
                subtitles=[
                    {"text": "Sentence one.", "time_begin": 0, "time_end": 251},
                    {"text": "Sentence two.", "time_begin": 251, "time_end": 847},
                    {"text": "Sentence three.", "time_begin": 847, "time_end": 1946},
                ],
            )
            yield SimpleNamespace(
                audio_data=b"",
                is_final=True,
                duration_ms=6364,
                format="mp3",
                word_count=20,
                subtitles=[
                    {"text": "Sentence one.", "time_begin": 0, "time_end": 913},
                    {"text": "Sentence two.", "time_begin": 913, "time_end": 2410},
                    {
                        "text": "Sentence three.",
                        "time_begin": 2410,
                        "time_end": 6364,
                    },
                ],
            )

    def _fake_export(_audio_data, **kwargs):
        end_ms = kwargs.get("end_ms")
        start_ms = int(kwargs.get("start_ms") or 0)
        if end_ms is None:
            return b"early-piece", 1946
        return b"final-piece", int(end_ms or 0) - start_ms

    def _fake_build_completed_audio_record(**kwargs):
        saved_records.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.is_tts_configured", lambda _provider: True
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.should_use_minimax_http_stream",
        lambda _provider: True,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.MinimaxTTSProvider", _FakeMinimaxProvider
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.export_audio_range_best_effort",
        _fake_export,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.concat_audio_best_effort",
        lambda parts, output_format="mp3": b"".join(parts),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.get_audio_duration_ms",
        lambda _audio, format="mp3": 6364,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.build_completed_audio_record",
        _fake_build_completed_audio_record,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.streaming_tts.save_audio_record",
        lambda _record, commit=True: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_handler.upload_audio_to_oss",
        lambda _app, _audio, audio_bid: (f"https://example.com/{audio_bid}.mp3", "b"),
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage",
        lambda **_kwargs: None,
    )

    processor = StreamingTTSProcessor(
        app=SimpleNamespace(),
        generated_block_bid="generated-http-stream-rebuild-same-count",
        outline_bid="outline",
        progress_record_bid="progress",
        user_bid="user",
        shifu_bid="shifu",
        tts_provider="minimax",
        tts_model="speech-2.8-turbo",
    )
    assert (
        list(processor.process_chunk("Sentence one. Sentence two. Sentence three."))
        == []
    )

    events = list(processor.finalize(commit=False))
    audio_segments = [
        event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
    ]
    audio_complete = [
        event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
    ]

    assert len(audio_segments) == 2
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_segments[0].content.subtitle_cues
    ] == [
        ("Sentence one.", 0, 251),
        ("Sentence two.", 251, 847),
        ("Sentence three.", 847, 1946),
    ]
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_segments[1].content.subtitle_cues
    ] == [
        ("Sentence one.", 0, 913),
        ("Sentence two.", 913, 2410),
        ("Sentence three.", 2410, 6364),
    ]
    assert audio_segments[1].content.subtitle_cues[0].end_ms > 251
    assert audio_segments[1].content.subtitle_cues[-1].end_ms == 6364

    assert len(audio_complete) == 1
    assert [
        (cue.text, cue.start_ms, cue.end_ms)
        for cue in audio_complete[0].content.subtitle_cues
    ] == [
        ("Sentence one.", 0, 913),
        ("Sentence two.", 913, 2410),
        ("Sentence three.", 2410, 6364),
    ]
    assert len(saved_records) == 1
    assert [
        (cue["text"], cue["start_ms"], cue["end_ms"])
        for cue in saved_records[0]["subtitle_cues"]
    ] == [
        ("Sentence one.", 0, 913),
        ("Sentence two.", 913, 2410),
        ("Sentence three.", 2410, 6364),
    ]

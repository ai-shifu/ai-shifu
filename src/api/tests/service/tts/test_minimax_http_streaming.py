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
                        "data": {"audio": "6161", "status": 1},
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
                subtitles=[],
            )
            yield SimpleNamespace(
                audio_data=b"",
                is_final=True,
                duration_ms=1000,
                format="mp3",
                word_count=10,
                subtitles=[
                    {"text": "First sentence.", "time_begin": 0, "time_end": 400},
                    {"text": "Second sentence.", "time_begin": 500, "time_end": 1000},
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

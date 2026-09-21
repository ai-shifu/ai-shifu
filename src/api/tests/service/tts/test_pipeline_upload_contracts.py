"""Verify long-text synthesis order, metering and upload failure boundaries."""

import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, has_app_context
from flaskr.api.tts.base import (
    AudioSettings,
    ProviderCapabilities,
    TTSResult,
    VoiceSettings,
)
from flaskr.service.metering import UsageContext
from flaskr.service.tts import pipeline


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    app = Flask(__name__)
    calls = []

    def synthesize(**kwargs: object) -> TTSResult:
        assert has_app_context()
        calls.append(kwargs.copy())
        text = kwargs["text"]
        return TTSResult(
            audio_data=text.encode(),
            duration_ms=100,
            sample_rate=24000,
            format="mp3",
            word_count=2,
            usage_characters=9 if text == "First." else 0,
        )

    def upload(app_arg: Flask, audio: bytes, bid: str) -> tuple[str, str]:
        assert app_arg is app
        assert has_app_context()
        assert audio == b"First.Second.Third."
        assert bid
        return "https://audio.invalid/lesson.mp3", "bucket"

    state = SimpleNamespace(
        app=app,
        calls=calls,
        synthesize=Mock(side_effect=synthesize),
        upload=Mock(side_effect=upload),
        usage=Mock(),
        sleep=Mock(),
    )
    monkeypatch.setattr(pipeline, "is_tts_configured", lambda _: True)
    monkeypatch.setattr(
        pipeline, "get_provider_capabilities", lambda _: ProviderCapabilities()
    )
    monkeypatch.setattr(pipeline, "get_config", lambda *_: 8)
    monkeypatch.setattr(
        pipeline,
        "get_default_voice_settings",
        lambda _: VoiceSettings(voice_id="default-voice"),
    )
    monkeypatch.setattr(
        pipeline, "get_default_audio_settings", lambda _: AudioSettings(format="wav")
    )
    monkeypatch.setattr(pipeline, "synthesize_text", state.synthesize)
    monkeypatch.setattr(pipeline, "upload_audio_to_oss", state.upload)
    monkeypatch.setattr(pipeline, "record_tts_usage", state.usage)
    monkeypatch.setattr(pipeline, "generate_id", lambda _: "generated-parent")
    monkeypatch.setattr(pipeline, "concat_audio_best_effort", b"".join)
    monkeypatch.setattr(pipeline, "get_audio_duration_ms", lambda *_a, **_k: 300)
    monkeypatch.setattr(
        pipeline, "time", SimpleNamespace(monotonic=time.monotonic, sleep=state.sleep)
    )
    return state


@pytest.mark.parametrize("workers", [1, 3])
def test_upload_preserves_sentence_order_and_records_each_segment_and_parent(
    transport: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, workers: int
) -> None:
    # Consume completed futures in reverse source order to catch append-on-completion bugs.
    monkeypatch.setattr(
        pipeline, "as_completed", lambda futures: reversed(list(futures))
    )
    context = UsageContext(user_bid="learner", shifu_bid="course")
    result = pipeline.synthesize_long_text_to_oss(
        transport.app,
        text="First. Second. Third.",
        provider_name=" TENCENT ",
        model=" model ",
        voice_id="selected-voice",
        language="en",
        max_workers=workers,
        sleep_between_segments=0.25,
        audio_bid=" clip ",
        usage_context=context,
        parent_usage_bid="parent",
    )
    assert result.provider == "tencent"
    assert result.model == "model"
    assert result.voice_id == "selected-voice"
    assert result.language == "en"
    assert result.segment_count == 3
    assert result.duration_ms == 300
    assert result.elapsed_seconds >= 0
    assert result.audio_url == "https://audio.invalid/lesson.mp3"
    transport.upload.assert_called_once_with(
        transport.app, b"First.Second.Third.", "clip"
    )
    assert sorted(call["text"] for call in transport.calls) == [
        "First.",
        "Second.",
        "Third.",
    ]
    assert all(call["audio_settings"].format == "mp3" for call in transport.calls)
    assert all(
        call["model"] == "model" and call["provider_name"] == "tencent"
        for call in transport.calls
    )
    records = [call.kwargs for call in transport.usage.call_args_list]
    assert len(records) == 4
    segments = sorted(records[:-1], key=lambda item: item["segment_index"])
    assert [row["input"] for row in segments] == [6, 7, 6]
    assert [row["output"] for row in segments] == [9, 7, 6]
    assert all(
        row["parent_usage_bid"] == "parent" and row["record_level"] == 1
        for row in segments
    )
    assert all(
        row["segment_count"] == 0 and row["duration_ms"] == 100 for row in segments
    )
    assert all(
        call.args == (transport.app, context) for call in transport.usage.call_args_list
    )
    parent = records[-1]
    assert {
        key: parent[key]
        for key in (
            "usage_bid",
            "record_level",
            "input",
            "output",
            "total",
            "word_count",
            "duration_ms",
            "segment_count",
            "parent_usage_bid",
        )
    } == {
        "usage_bid": "parent",
        "record_level": 0,
        "input": 21,
        "output": 22,
        "total": 22,
        "word_count": 6,
        "duration_ms": 300,
        "segment_count": 3,
        "parent_usage_bid": "",
    }
    assert parent["extra"]["voice_id"] == "selected-voice"
    assert parent["extra"]["format"] == "mp3"
    assert transport.sleep.call_count == (2 if workers == 1 else 0)


@pytest.mark.parametrize("workers", [0, 2])
def test_upload_without_usage_context_never_creates_metering_records(
    transport: SimpleNamespace, workers: int
) -> None:
    result = pipeline.synthesize_long_text_to_oss(
        transport.app,
        text="First. Second. Third.",
        provider_name="tencent",
        max_workers=workers,
    )
    assert result.voice_id == "default-voice"
    assert result.segment_count == 3
    transport.usage.assert_not_called()
    transport.sleep.assert_not_called()
    transport.upload.assert_called_once()


def test_parent_id_is_generated_and_explicit_voice_and_audio_settings_are_used(
    transport: SimpleNamespace,
) -> None:
    voice = VoiceSettings(
        voice_id="custom", speed=0.8, pitch=1, emotion="happy", volume=0.5
    )
    audio = AudioSettings(format="pcm", sample_rate=16000)
    result = pipeline.synthesize_long_text_to_oss(
        transport.app,
        text="First. Second. Third.",
        provider_name="tencent",
        max_workers=1,
        voice_settings=voice,
        audio_settings=audio,
        usage_context=UsageContext(),
    )
    assert result.voice_id == "custom"
    assert all(
        call["voice_settings"] is voice and call["audio_settings"] is audio
        for call in transport.calls
    )
    records = [call.kwargs for call in transport.usage.call_args_list]
    assert records[-1]["usage_bid"] == "generated-parent"
    assert records[-1]["extra"] == {
        "voice_id": "custom",
        "speed": 0.8,
        "pitch": 1,
        "emotion": "happy",
        "volume": 0.5,
        "format": "mp3",
        "sample_rate": 16000,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"provider_name": " "}, "provider is required"),
        ({"text": "```python\nprint(1)\n```"}, "No speakable text"),
        ({"sleep_between_segments": -0.1}, "must be >= 0"),
    ],
)
def test_invalid_requests_fail_before_synthesis_upload_or_metering(
    transport: SimpleNamespace, overrides: dict, message: str
) -> None:
    kwargs = {
        "text": "First. Second. Third.",
        "provider_name": "tencent",
        "usage_context": UsageContext(),
    } | overrides
    with pytest.raises(ValueError, match=message):
        pipeline.synthesize_long_text_to_oss(transport.app, **kwargs)
    transport.synthesize.assert_not_called()
    transport.upload.assert_not_called()
    transport.usage.assert_not_called()


def test_unconfigured_provider_is_rejected_before_synthesis(
    transport: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "is_tts_configured", lambda _: False)
    with pytest.raises(ValueError, match="not configured: tencent"):
        pipeline.synthesize_long_text_to_oss(
            transport.app, text="First.", provider_name="tencent"
        )
    transport.synthesize.assert_not_called()
    transport.upload.assert_not_called()


@pytest.mark.parametrize("workers", [1, 3])
def test_provider_failure_prevents_upload_and_parent_usage(
    transport: SimpleNamespace, workers: int
) -> None:
    transport.synthesize.side_effect = RuntimeError("provider unavailable")
    with pytest.raises(RuntimeError, match="provider unavailable"):
        pipeline.synthesize_long_text_to_oss(
            transport.app,
            text="First. Second. Third.",
            provider_name="tencent",
            max_workers=workers,
            usage_context=UsageContext(),
        )
    transport.upload.assert_not_called()
    transport.usage.assert_not_called()


def test_empty_combined_audio_is_rejected_before_upload(
    transport: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "concat_audio_best_effort", lambda _: b"")
    with pytest.raises(ValueError, match="No audio data produced"):
        pipeline.synthesize_long_text_to_oss(
            transport.app,
            text="First. Second. Third.",
            provider_name="tencent",
            max_workers=1,
            usage_context=UsageContext(),
        )
    assert transport.usage.call_count == 3
    assert all(
        call.kwargs["record_level"] == 1 for call in transport.usage.call_args_list
    )
    transport.upload.assert_not_called()


def test_upload_failure_keeps_segment_usage_without_reporting_completed_parent(
    transport: SimpleNamespace,
) -> None:
    transport.upload.side_effect = OSError("storage unavailable")
    with pytest.raises(OSError, match="storage unavailable"):
        pipeline.synthesize_long_text_to_oss(
            transport.app,
            text="First. Second. Third.",
            provider_name="tencent",
            max_workers=1,
            usage_context=UsageContext(),
        )
    assert transport.usage.call_count == 3
    assert all(
        call.kwargs["record_level"] == 1 for call in transport.usage.call_args_list
    )


def test_html_audio_escapes_url_attribute_content() -> None:
    result = pipeline.SynthesizeToOssResult(
        "tencent", "", "", "", 1, 10, 'https://audio.invalid/?x="quoted"&y=<tag>', 0.1
    )
    assert (
        result.to_html_audio()
        == '<audio controls preload="none" src="https://audio.invalid/?x=&quot;quoted&quot;&amp;y=&lt;tag&gt;"></audio>'
    )


@pytest.mark.parametrize(
    ("units", "size", "expected"),
    [
        (["", "ab", "c", "defghij"], 4, ["ab c", "defg", "hij"]),
        (["abcde", "xy"], 2, ["ab", "cd", "e", "xy"]),
    ],
)
def test_character_limit_splits_oversized_units_without_losing_text(
    units: list[str], size: int, expected: list[str]
) -> None:
    assert pipeline._split_text_by_max_chars(units, max_chars=size) == expected


@pytest.mark.parametrize("size", [0, -1])
def test_nonpositive_segment_limits_fail_explicitly(size: int) -> None:
    with pytest.raises(ValueError, match="max_chars must be > 0"):
        pipeline._split_text_by_max_chars(["hello"], max_chars=size)
    with pytest.raises(ValueError, match="max_bytes must be > 0"):
        pipeline._split_text_by_max_bytes(["hello"], max_bytes=size, encoding="utf-8")


def test_byte_limit_preserves_multibyte_characters_and_skips_empty_segments() -> None:
    result = pipeline._split_text_by_max_bytes(
        ["", " ", "你好世界", "abc"], max_bytes=6, encoding="utf-8"
    )
    assert result == ["你好", "世界", "abc"]
    assert all(len(segment.encode()) <= 6 for segment in result)


def test_unknown_encoding_preserves_text_for_provider_fallback() -> None:
    assert pipeline._split_text_by_max_bytes(
        ["hello"], max_bytes=2, encoding="missing-codec"
    ) == ["hello"]

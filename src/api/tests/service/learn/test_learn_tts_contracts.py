"""Verify preview audio accounting, completion and cache invalidation contracts."""

import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.api.tts import AudioSettings, VoiceSettings
from flaskr.service.learn import learn_funcs as learn
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)


@pytest.fixture
def tts(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    app = Flask("tts-contract")
    voice, audio = VoiceSettings(), AudioSettings(format="wav", sample_rate=24000)
    monkeypatch.setattr(
        learn,
        "_resolve_shifu_tts_settings",
        lambda *_a, **_k: ("provider", "model", voice, audio),
    )
    monkeypatch.setattr(learn, "is_tts_configured", lambda _provider: True)
    monkeypatch.setattr(
        learn, "split_text_for_tts", lambda _text, **_k: ["First", "Second"]
    )
    synthesize = Mock(
        side_effect=[
            SimpleNamespace(
                audio_data=b"first", duration_ms=120, word_count=1, usage_characters=5
            ),
            SimpleNamespace(
                audio_data=b"second", duration_ms=180, word_count=1, usage_characters=6
            ),
        ]
    )
    monkeypatch.setattr(learn, "synthesize_text", synthesize)
    monkeypatch.setattr(learn, "concat_audio_best_effort", b"".join)
    monkeypatch.setattr(learn, "get_audio_duration_ms", lambda *_a, **_k: 300)
    upload = Mock(return_value=("https://example.test/audio.mp3", "bucket"))
    monkeypatch.setattr(learn, "upload_audio_to_oss", upload)
    usage = Mock()
    monkeypatch.setattr(learn, "record_tts_usage", usage)
    save = Mock()
    monkeypatch.setattr(learn, "save_audio_record", save)
    monkeypatch.setattr(learn, "generate_id", lambda _app: "parent-usage")
    return SimpleNamespace(
        app=app,
        voice=voice,
        audio=audio,
        synthesize=synthesize,
        upload=upload,
        usage=usage,
        save=save,
    )


@pytest.mark.parametrize("preview", [True, False])
def test_preview_tts_streams_segments_then_complete_with_matching_usage(
    tts: SimpleNamespace, preview: bool
) -> None:
    stream = learn.stream_preview_tts_audio(
        tts.app,
        shifu_bid="course",
        user_bid="user",
        text="First Second",
        preview_mode=preview,
    )
    first = next(stream)
    assert first.type == GeneratedType.AUDIO_SEGMENT
    assert base64.b64decode(first.content.audio_data) == b"first"
    tts.upload.assert_not_called()
    events = [first, *stream]
    assert [event.type for event in events] == [
        GeneratedType.AUDIO_SEGMENT,
        GeneratedType.AUDIO_SEGMENT,
        GeneratedType.AUDIO_COMPLETE,
    ]
    assert [
        (cue.text, cue.start_ms, cue.end_ms) for cue in events[-1].content.subtitle_cues
    ] == [("First", 0, 120), ("Second", 120, 300)]
    assert events[-1].content.audio_url == "https://example.test/audio.mp3"
    assert events[-1].content.duration_ms == 300
    assert tts.upload.call_args.args[1] == b"firstsecond"
    assert tts.audio.format == "wav"
    assert all(
        call.kwargs["audio_settings"].format == "mp3"
        for call in tts.synthesize.call_args_list
    )
    assert len(tts.usage.call_args_list) == 3
    summary = tts.usage.call_args_list[-1]
    assert summary.kwargs["record_level"] == 0
    assert summary.kwargs["segment_count"] == 2
    assert summary.kwargs["output"] == 11
    assert summary.kwargs["duration_ms"] == 300
    assert summary.args[1].usage_scene == (
        BILL_USAGE_SCENE_PREVIEW if preview else BILL_USAGE_SCENE_PROD
    )
    assert summary.args[1].learning_mode == "listen"
    tts.save.assert_not_called()


def test_preview_disconnect_keeps_completed_segment_usage_without_uploading_partial_audio(
    tts: SimpleNamespace,
) -> None:
    stream = learn.stream_preview_tts_audio(
        tts.app,
        shifu_bid="course",
        user_bid="user",
        text="First Second",
        preview_mode=True,
    )
    assert next(stream).type == GeneratedType.AUDIO_SEGMENT
    stream.close()
    assert tts.usage.call_count == 1
    assert tts.usage.call_args.kwargs["record_level"] == 1
    tts.upload.assert_not_called()
    tts.save.assert_not_called()


@pytest.mark.parametrize(
    ("provider", "configured", "segments", "message"),
    [
        ("", True, ["text"], "provider is required"),
        ("provider", False, ["text"], "not configured"),
        ("provider", True, [], "No speakable text"),
    ],
)
def test_tts_rejects_unsynthesizable_requests_before_external_call(
    tts: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    configured: bool,
    segments: list[str],
    message: str,
) -> None:
    monkeypatch.setattr(learn, "is_tts_configured", lambda _provider: configured)
    monkeypatch.setattr(learn, "split_text_for_tts", lambda *_a, **_k: segments)
    with pytest.raises(ValueError, match=message):
        list(
            learn._yield_tts_segments(
                text="text",
                provider=provider,
                tts_model="model",
                voice_settings=tts.voice,
                audio_settings=tts.audio,
            )
        )
    tts.synthesize.assert_not_called()


def test_tts_finalize_refuses_empty_audio_without_uploading(
    tts: SimpleNamespace,
) -> None:
    with pytest.raises(ValueError, match="No audio data produced"):
        learn._finalize_tts_stream_audio(
            tts.app,
            audio_parts=[],
            subtitle_cues=[],
            audio_bid="audio",
            audio_settings=tts.audio,
            voice_settings=tts.voice,
            tts_model="model",
            cleaned_text="text",
            segment_count=0,
            persist_audio=False,
        )
    tts.upload.assert_not_called()


@pytest.mark.parametrize(
    ("record", "text", "expected"),
    [
        (None, "Hello", False),
        (SimpleNamespace(oss_url=""), "Hello", False),
        (
            SimpleNamespace(oss_url="url", subtitle_cues=[], text_length=5),
            "Hello",
            True,
        ),
        (
            SimpleNamespace(oss_url="url", subtitle_cues=[], text_length=4),
            "Hello",
            False,
        ),
        (
            SimpleNamespace(oss_url="url", subtitle_cues=[], text_length=0),
            "Hello",
            False,
        ),
        (SimpleNamespace(oss_url="url", subtitle_cues=[], text_length=5), "", False),
    ],
)
def test_audio_cache_requires_matching_speakable_text(
    record: object, text: str, expected: bool
) -> None:
    assert learn._audio_record_matches_speakable_text(record, text) is expected


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        ({}, True),
        ({"voice_id": "different"}, False),
        ({"model": "different"}, False),
        ({"voice_settings": {"speed": 2}}, False),
        ({"voice_settings": {"volume": 2}}, False),
        ({"voice_settings": {"pitch": 1}}, False),
        ({"voice_settings": {"emotion": "happy"}}, False),
        ({"voice_settings": {"speed": "bad"}}, False),
        ({"voice_settings": None}, True),
    ],
)
def test_audio_cache_rejects_stale_synthesis_settings(
    changed: dict, expected: bool
) -> None:
    voice = SimpleNamespace(voice_id="voice", speed=1, volume=1, pitch=0, emotion="")
    record = SimpleNamespace(
        **{"voice_id": "voice", "model": "model", "voice_settings": {}, **changed}
    )
    assert (
        learn._audio_record_matches_tts_settings(
            record, voice_settings=voice, tts_model="model"
        )
        is expected
    )
    assert (
        learn._audio_record_matches_tts_settings(
            None, voice_settings=voice, tts_model="model"
        )
        is False
    )


def test_audio_segment_message_keeps_stream_identity_and_contract() -> None:
    message = learn._build_audio_segment_message(
        outline_bid="outline",
        generated_block_bid="block",
        segment_index=3,
        audio_data=b"audio",
        duration_ms=100,
        position=2,
        stream_element_number=4,
        stream_element_type="text",
        av_contract={"version": 2},
    )
    assert message.content.__json__() == {
        "segment_index": 3,
        "audio_data": "YXVkaW8=",
        "duration_ms": 100,
        "is_final": False,
        "position": 2,
        "stream_element_number": 4,
        "stream_element_type": "text",
        "av_contract": {"version": 2},
    }

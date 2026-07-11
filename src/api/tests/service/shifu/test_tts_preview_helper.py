from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from flask import Flask

from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.shifu.tts_preview import build_tts_preview_response


@dataclass
class _FakeAudioSettings:
    format: str = "wav"
    sample_rate: int = 24000


def test_build_tts_preview_response_records_debug_usage_and_summary(
    monkeypatch,
) -> None:
    app = Flask(__name__)
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.validate_tts_settings_strict",
        lambda **_kwargs: SimpleNamespace(
            provider="fake",
            model="tts-model-1",
            voice_id="voice-1",
            speed=1.0,
            pitch=0,
            emotion="",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.is_tts_configured",
        lambda _provider: True,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.get_default_voice_settings",
        lambda _provider: SimpleNamespace(
            voice_id="",
            speed=0.0,
            pitch=0,
            emotion="",
            volume=1.0,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.get_default_audio_settings",
        lambda _provider: _FakeAudioSettings(),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.split_text_for_tts",
        lambda _text, provider_name="": ["hello", "world"],
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.preprocess_for_tts",
        lambda text: text.replace(" ", ""),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.generate_id",
        lambda _app: "usage-parent-1",
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.synthesize_text",
        lambda **_kwargs: SimpleNamespace(
            duration_ms=123,
            audio_data=b"abc",
            word_count=5,
            usage_characters=8,
        ),
        raising=False,
    )

    def _fake_record_tts_usage(app, context, **kwargs):
        captured.append(
            {
                "app": app,
                "context": context,
                "kwargs": kwargs,
            }
        )
        return kwargs.get("usage_bid") or "segment-usage"

    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.record_tts_usage",
        _fake_record_tts_usage,
        raising=False,
    )

    with app.test_request_context("/api/shifu/tts/preview", method="POST"):
        response = build_tts_preview_response(
            {
                "provider": "fake",
                "voice_id": "voice-1",
                "speed": 1.0,
                "pitch": 0,
                "text": "hello world",
            },
            request_user_id="creator-debug-tts-1",
            request_user_is_creator=True,
        )
        body = "".join(response.response)

    assert response.mimetype == "text/event-stream"
    assert '"type": "audio_segment"' in body
    assert '"type": "audio_complete"' in body
    assert len(captured) == 3

    segment_calls = captured[:2]
    summary_call = captured[2]

    for call in segment_calls:
        context = call["context"]
        assert context.user_bid == "creator-debug-tts-1"
        assert context.usage_scene == BILL_USAGE_SCENE_DEBUG
        assert context.billable == 1
        assert call["kwargs"]["record_level"] == 1
        assert call["kwargs"]["parent_usage_bid"] == "usage-parent-1"
        assert call["kwargs"]["output"] == 8
        assert call["kwargs"]["total"] == 8

    assert summary_call["kwargs"]["usage_bid"] == "usage-parent-1"
    assert summary_call["kwargs"]["record_level"] == 0
    assert summary_call["kwargs"]["segment_count"] == 2
    assert summary_call["kwargs"]["word_count"] == 10
    assert summary_call["kwargs"]["output"] == 16
    assert summary_call["kwargs"]["total"] == 16


def test_build_tts_preview_response_normalizes_removed_fields(monkeypatch) -> None:
    app = Flask(__name__)
    captured: dict[str, object] = {}

    def _fake_validate_tts_settings_strict(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            provider="fake",
            model="tts-model-1",
            voice_id="voice-1",
            speed=1.0,
            pitch=kwargs["pitch"],
            emotion=kwargs["emotion"],
        )

    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.validate_tts_settings_strict",
        _fake_validate_tts_settings_strict,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.is_tts_configured",
        lambda _provider: True,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.get_default_voice_settings",
        lambda _provider: SimpleNamespace(
            voice_id="",
            speed=0.0,
            pitch=0,
            emotion="",
            volume=1.0,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.get_default_audio_settings",
        lambda _provider: _FakeAudioSettings(),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.split_text_for_tts",
        lambda _text, provider_name="": ["hello"],
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.preprocess_for_tts",
        lambda text: text,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.generate_id",
        lambda _app: "usage-parent-1",
        raising=False,
    )

    with app.test_request_context("/api/shifu/tts/preview", method="POST"):
        build_tts_preview_response(
            {
                "provider": "fake",
                "model": "tts-model-1",
                "voice_id": "voice-1",
                "speed": 1.0,
                "pitch": 9,
                "emotion": "happy",
                "text": "hello",
            },
            request_user_id="creator-debug-tts-1",
            request_user_is_creator=True,
        )

    assert captured["pitch"] == 0
    assert captured["emotion"] == ""


def test_build_tts_preview_response_guards_minimax_custom_voice(monkeypatch) -> None:
    app = Flask(__name__)
    guard_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.validate_tts_settings_strict",
        lambda **_kwargs: SimpleNamespace(
            provider="minimax",
            model="speech-2.8-turbo",
            voice_id="AiShifu_missing_voice",
            speed=1.0,
            pitch=0,
            emotion="",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.is_tts_configured",
        lambda _provider: True,
        raising=False,
    )

    def _fake_guard(_app, *, voice_id, owner_user_bid):
        guard_calls.append({"voice_id": voice_id, "owner_user_bid": owner_user_bid})
        raise AppException("voice unavailable", ERROR_CODE["server.common.paramsError"])

    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.assert_minimax_preview_voice_available",
        _fake_guard,
        raising=False,
    )

    with app.test_request_context("/api/shifu/tts/preview", method="POST"):
        with pytest.raises(AppException) as exc_info:
            build_tts_preview_response(
                {
                    "provider": "minimax",
                    "model": "speech-2.8-turbo",
                    "voice_id": "AiShifu_missing_voice",
                    "speed": 1.0,
                    "text": "hello",
                },
                request_user_id="creator-debug-tts-1",
                request_user_is_creator=True,
            )

    # The guard runs before any streaming/synthesis and blocks the request.
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert guard_calls == [
        {
            "voice_id": "AiShifu_missing_voice",
            "owner_user_bid": "creator-debug-tts-1",
        }
    ]

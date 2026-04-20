from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from flask import Flask

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

    assert summary_call["kwargs"]["usage_bid"] == "usage-parent-1"
    assert summary_call["kwargs"]["record_level"] == 0
    assert summary_call["kwargs"]["segment_count"] == 2
    assert summary_call["kwargs"]["word_count"] == 10

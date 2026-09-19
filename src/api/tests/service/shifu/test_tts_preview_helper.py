"""Verify TTS preview helper behavior."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing.ownership import resolve_usage_creator_bid
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.shifu.models import DraftShifu
from flaskr.service.shifu.tts_preview import build_tts_preview_response


@dataclass
class _FakeAudioSettings:
    format: str = "wav"
    sample_rate: int = 24000


def _split_hello_world(text: str, provider_name: str = "") -> list[str]:
    del text, provider_name
    return ["hello", "world"]


def _split_hello(text: str, provider_name: str = "") -> list[str]:
    del text, provider_name
    return ["hello"]


@pytest.mark.parametrize("is_creator", [True, False])
def test_tts_preview_route_records_billable_debug_usage_and_summary(
    monkeypatch: object, test_client: object, is_creator: bool
) -> None:
    app = test_client.application
    captured: list[dict[str, object]] = []
    with app.app_context(), unit_of_work():
        DraftShifu.query.filter_by(shifu_bid="tts-preview-course").delete()
        db.session.add(
            DraftShifu(
                shifu_bid="tts-preview-course", created_user_bid="tts-course-owner"
            )
        )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.shifu_permission_verification", lambda *_args: True
    )
    admissions = []
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id="preview-tts-user", language="en-US", is_creator=is_creator
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.admit_creator_usage",
        lambda _app, **kwargs: admissions.append(kwargs),
    )

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
        _split_hello_world,
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

    def _fake_record_tts_usage(
        app: object, context: object, **kwargs: object
    ) -> object:
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

    response = test_client.post(
        "/api/shifu/tts/preview",
        headers={"Token": "preview-token", "X-Internal-Request": "true"},
        json={
            "provider": "fake",
            "voice_id": "voice-1",
            "speed": 1.0,
            "pitch": 0,
            "text": "hello world",
            "billable": 0,
            "internal": True,
            "request_user_is_creator": False,
            "user_bid": "unrelated-user",
            "creator_bid": "unrelated-owner",
            "shifu_bid": "tts-preview-course",
        },
    )
    body = response.get_data(as_text=True)

    assert admissions == [
        {
            "creator_bid": "tts-course-owner",
            "shifu_bid": "tts-preview-course",
            "usage_scene": BILL_USAGE_SCENE_DEBUG,
        }
    ]
    assert response.mimetype == "text/event-stream"
    assert '"type": "audio_segment"' in body
    assert '"type": "audio_complete"' in body
    assert len(captured) == 3

    segment_calls = captured[:2]
    summary_call = captured[2]

    for call in segment_calls:
        context = call["context"]
        assert context.user_bid == "preview-tts-user"
        assert context.usage_scene == BILL_USAGE_SCENE_DEBUG
        assert context.billable == 1
        assert call["kwargs"]["record_level"] == 1
        assert call["kwargs"]["parent_usage_bid"] == "usage-parent-1"
        assert call["kwargs"]["output"] == 8
        assert call["kwargs"]["total"] == 8

    assert summary_call["kwargs"]["usage_bid"] == "usage-parent-1"
    assert summary_call["context"].billable == 1
    assert summary_call["context"].shifu_bid == "tts-preview-course"
    assert resolve_usage_creator_bid(app, summary_call["context"]) == "tts-course-owner"
    assert summary_call["kwargs"]["record_level"] == 0
    assert summary_call["kwargs"]["segment_count"] == 2
    assert summary_call["kwargs"]["word_count"] == 10
    assert summary_call["kwargs"]["output"] == 16
    assert summary_call["kwargs"]["total"] == 16


def test_build_tts_preview_response_normalizes_removed_fields(
    monkeypatch: object,
) -> None:
    app = Flask(__name__)
    captured: dict[str, object] = {}

    def _fake_validate_tts_settings_strict(**kwargs: object) -> object:
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
        _split_hello,
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
            shifu_bid="tts-preview-course",
        )

    assert captured["pitch"] == 0
    assert captured["emotion"] == ""


def test_build_tts_preview_response_guards_minimax_custom_voice(
    monkeypatch: object,
) -> None:
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

    def _fake_guard(
        _app: object, *, provider: object, voice_id: object, owner_user_bid: object
    ) -> None:
        guard_calls.append(
            {
                "provider": provider,
                "voice_id": voice_id,
                "owner_user_bid": owner_user_bid,
            }
        )
        message = "voice unavailable"
        raise AppError(message, ERROR_CODE["server.common.paramsError"])

    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.assert_preview_cloned_voice_available",
        _fake_guard,
        raising=False,
    )

    with (
        app.test_request_context("/api/shifu/tts/preview", method="POST"),
        pytest.raises(AppError) as exc_info,
    ):
        build_tts_preview_response(
            {
                "provider": "minimax",
                "model": "speech-2.8-turbo",
                "voice_id": "AiShifu_missing_voice",
                "speed": 1.0,
                "text": "hello",
            },
            request_user_id="creator-debug-tts-1",
            shifu_bid="tts-preview-course",
        )

    # The guard runs before any streaming/synthesis and blocks the request.
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
    assert guard_calls == [
        {
            "provider": "minimax",
            "voice_id": "AiShifu_missing_voice",
            "owner_user_bid": "creator-debug-tts-1",
        }
    ]


def _stub_preview_pipeline(monkeypatch: object) -> None:
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
            voice_id="", speed=0.0, pitch=0, emotion="", volume=1.0
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
        _split_hello_world,
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
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.record_tts_usage",
        lambda *_args, **kwargs: kwargs.get("usage_bid") or "segment-usage",
        raising=False,
    )


def test_preview_stream_close_invalidates_session(monkeypatch: object) -> None:
    """A client walking away mid-preview may interrupt the usage-metering DB write; the GeneratorExit handler must discard the session connection."""
    app = Flask(__name__)
    _stub_preview_pipeline(monkeypatch)

    invalidations: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.shifu.tts_preview.invalidate_session",
        lambda *, source, _session=None: invalidations.append(source) or True,
        raising=False,
    )

    with app.test_request_context("/api/shifu/tts/preview", method="POST"):
        response = build_tts_preview_response(
            {"provider": "fake", "voice_id": "voice-1", "text": "hello world"},
            request_user_id="creator-1",
            shifu_bid="tts-preview-course",
        )
        stream = iter(response.response)
        next(stream)
        stream.close()

    assert invalidations == ["tts preview stream close"]

"""Strict-validation coverage for cloned (custom) voice ids."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.tts.models import (
    TTS_MINIMAX_CLONE_STATUS_READY,
    TTSMiniMaxClonedVoice,
)
from flaskr.service.tts.validation import validate_tts_settings_strict


@pytest.fixture(autouse=True)
def _fake_providers(monkeypatch: object):
    """Serve static voice/model lists without real provider credentials."""

    def _fake_get_tts_provider(name: object):
        if name == "volcengine":
            cfg = SimpleNamespace(
                voices=[{"value": "zh_female_vv_uranus_bigtts"}],
                models=[{"value": "seed-tts-2.0"}],
                speed=SimpleNamespace(min=0.5, max=2.0),
                pitch=SimpleNamespace(min=-12, max=12),
                supports_emotion=False,
                emotions=[],
            )
        else:
            cfg = SimpleNamespace(
                voices=[{"value": "female-shaonv"}],
                models=[{"value": "speech-2.8-turbo"}],
                speed=SimpleNamespace(min=0.5, max=2.0),
                pitch=SimpleNamespace(min=-12, max=12),
                supports_emotion=False,
                emotions=[],
            )
        return SimpleNamespace(get_provider_config=lambda: cfg)

    monkeypatch.setattr(
        "flaskr.service.tts.validation.get_tts_provider",
        _fake_get_tts_provider,
    )


def _prepare_tables(app: object) -> None:
    with app.app_context():
        TTSMiniMaxClonedVoice.__table__.create(db.engine, checkfirst=True)


def _seed_ready_clone(app: object, *, provider: str, voice_id: str) -> None:
    with app.app_context():
        db.session.add(
            TTSMiniMaxClonedVoice(
                voice_bid=f"vb-{uuid.uuid4().hex[:12]}",
                owner_user_bid="creator-1",
                shifu_bid="",
                display_name=voice_id,
                provider=provider,
                voice_id=voice_id,
                status=TTS_MINIMAX_CLONE_STATUS_READY,
            )
        )
        db.session.commit()


def _validate(provider: str, model: str, voice_id: str):
    return validate_tts_settings_strict(
        provider=provider,
        model=model,
        voice_id=voice_id,
        speed=1.0,
        pitch=0,
        emotion="",
    )


def test_volcengine_registered_clone_keeps_teacher_selected_model(app: object) -> None:
    """A registered cloned voice validates under the teacher's normal model.

    For example, seed-tts-2.0 remains the model; the clone resource id is inferred inside the
    provider and is never selected as a model.
    """
    _prepare_tables(app)
    _seed_ready_clone(app, provider="volcengine", voice_id="S_xxxxxxxxxx")
    with app.app_context():
        validated = _validate("volcengine", "seed-tts-2.0", "S_xxxxxxxxxx")
    assert validated.voice_id == "S_xxxxxxxxxx"
    assert validated.model == "seed-tts-2.0"


def test_volcengine_clone_with_unlisted_model_is_rejected(app: object) -> None:
    _prepare_tables(app)
    _seed_ready_clone(app, provider="volcengine", voice_id="S_xxxxxxxxxx")
    with app.app_context(), pytest.raises(AppError) as exc_info:
        _validate("volcengine", "seed-tts-9.9", "S_xxxxxxxxxx")
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_volcengine_unregistered_clone_is_rejected(app: object) -> None:
    _prepare_tables(app)
    with app.app_context(), pytest.raises(AppError) as exc_info:
        _validate("volcengine", "seed-tts-2.0", "S_xxxxxxxxxxxx")
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_volcengine_bad_shape_custom_voice_is_rejected(app: object) -> None:
    _prepare_tables(app)
    with app.app_context(), pytest.raises(AppError) as exc_info:
        _validate("volcengine", "seed-tts-2.0", "AiShifu_not_a_speaker")
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_minimax_format_bypass_does_not_require_db_row(app: object) -> None:
    """Regression: the historical MiniMax bypass stays format-only (no DB row needed), so stale-but-well-formed ids keep passing strict validation."""
    _prepare_tables(app)
    with app.app_context():
        validated = _validate("minimax", "speech-2.8-turbo", "AiShifu_no_row_here")
    assert validated.voice_id == "AiShifu_no_row_here"

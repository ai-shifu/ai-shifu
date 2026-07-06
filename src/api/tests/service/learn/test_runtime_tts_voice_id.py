from types import SimpleNamespace

import pytest
from flask import Flask

import flaskr.dao as dao
from flaskr.service.tts.models import (
    TTSMiniMaxClonedVoice,
    TTS_MINIMAX_CLONE_STATUS_FAILED,
    TTS_MINIMAX_CLONE_STATUS_READY,
)


@pytest.fixture
def voice_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _patch_provider(
    monkeypatch, built_in=("builtin-1",), default_voice_id="default-voice"
):
    provider_config = SimpleNamespace(voices=[{"value": value} for value in built_in])
    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.get_tts_provider",
        lambda _provider: SimpleNamespace(get_provider_config=lambda: provider_config),
    )
    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.get_default_voice_settings",
        lambda _provider: SimpleNamespace(voice_id=default_voice_id),
    )


def _add_clone(shifu_bid, voice_id, status, voice_bid):
    dao.db.session.add(
        TTSMiniMaxClonedVoice(
            voice_bid=voice_bid,
            shifu_bid=shifu_bid,
            voice_id=voice_id,
            status=status,
            deleted=0,
        )
    )
    dao.db.session.commit()


def test_non_minimax_provider_returns_voice_id_unchanged(voice_app):
    from flaskr.service.learn import learn_funcs

    with voice_app.app_context():
        # Non-MiniMax providers are trusted as-is; no provider/DB lookups happen.
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "tencent", "any-voice", shifu_bid="shifu-1"
            )
            == "any-voice"
        )


def test_minimax_empty_voice_id_returns_empty(voice_app):
    from flaskr.service.learn import learn_funcs

    with voice_app.app_context():
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "minimax", "", shifu_bid="shifu-1"
            )
            == ""
        )


def test_minimax_builtin_voice_is_kept(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "MiniMax", "builtin-1", shifu_bid="shifu-1"
            )
            == "builtin-1"
        )


def test_minimax_ready_clone_of_same_shifu_is_kept(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        _add_clone("shifu-1", "AiShifu_clone_1", TTS_MINIMAX_CLONE_STATUS_READY, "vb-1")
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "minimax", "AiShifu_clone_1", shifu_bid="shifu-1"
            )
            == "AiShifu_clone_1"
        )


def test_minimax_ready_clone_of_other_shifu_falls_back(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        # Ready clone exists but belongs to a different shifu -> must not leak.
        _add_clone("shifu-2", "AiShifu_clone_1", TTS_MINIMAX_CLONE_STATUS_READY, "vb-2")
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "minimax", "AiShifu_clone_1", shifu_bid="shifu-1"
            )
            == "default-voice"
        )


def test_minimax_non_ready_clone_of_same_shifu_falls_back(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        # Clone belongs to this shifu but is not ready -> fall back.
        _add_clone(
            "shifu-1", "AiShifu_clone_1", TTS_MINIMAX_CLONE_STATUS_FAILED, "vb-3"
        )
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "minimax", "AiShifu_clone_1", shifu_bid="shifu-1"
            )
            == "default-voice"
        )


def test_minimax_unknown_voice_falls_back_to_default(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        # Not a built-in voice and no clone tracked at all -> fall back.
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "minimax", "stale-voice", shifu_bid="shifu-1"
            )
            == "default-voice"
        )

from types import SimpleNamespace

import flaskr.dao as dao
import pytest
from flask import Flask
from flaskr.service.tts.models import (
    TTS_MINIMAX_CLONE_STATUS_FAILED,
    TTS_MINIMAX_CLONE_STATUS_READY,
    TTSMiniMaxClonedVoice,
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


def _add_clone(shifu_bid, voice_id, status, voice_bid, provider="minimax"):
    dao.db.session.add(
        TTSMiniMaxClonedVoice(
            voice_bid=voice_bid,
            shifu_bid=shifu_bid,
            provider=provider,
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


def test_minimax_ready_clone_of_other_shifu_is_kept_as_manual_custom_voice(
    voice_app, monkeypatch
):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        # Runtime preview should preserve MiniMax custom voice IDs only when
        # they are verified by an existing READY clone row.
        _add_clone("shifu-2", "AiShifu_clone_1", TTS_MINIMAX_CLONE_STATUS_READY, "vb-2")
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "minimax", "AiShifu_clone_1", shifu_bid="shifu-1"
            )
            == "AiShifu_clone_1"
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


def test_minimax_untracked_custom_voice_falls_back(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        # Shape-valid MiniMax custom voice ids can still be stale provider-side;
        # fallback unless we can verify them through a READY local clone row.
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "minimax", "AiShifu_xxxxxxxxxx", shifu_bid="shifu-1"
            )
            == "default-voice"
        )


def test_volcengine_builtin_voice_is_kept(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch, built_in=("zh_female_vv_uranus_bigtts",))
    with voice_app.app_context():
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app,
                "volcengine",
                "zh_female_vv_uranus_bigtts",
                shifu_bid="shifu-1",
            )
            == "zh_female_vv_uranus_bigtts"
        )


def test_volcengine_operator_registered_clone_is_kept(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        # Operator-registered rows carry an empty shifu_bid; the global ready
        # fallback is what makes them usable inside a course.
        _add_clone(
            "", "S_xxxxxxxxxx", TTS_MINIMAX_CLONE_STATUS_READY, "vb-v1", "volcengine"
        )
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "volcengine", "S_xxxxxxxxxx", shifu_bid="shifu-1"
            )
            == "S_xxxxxxxxxx"
        )


def test_volcengine_unregistered_clone_falls_back(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "volcengine", "S_xxxxxxxxxxxxxxxx", shifu_bid="shifu-1"
            )
            == "default-voice"
        )


def test_volcengine_does_not_accept_minimax_clone_row(voice_app, monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch)
    with voice_app.app_context():
        # A ready MiniMax row with the same id must not authorize the id under
        # volcengine — clone rows are provider-scoped.
        _add_clone("", "S_xxxxxxxxxx", TTS_MINIMAX_CLONE_STATUS_READY, "vb-m1")
        assert (
            learn_funcs._resolve_runtime_tts_voice_id(
                voice_app, "volcengine", "S_xxxxxxxxxx", shifu_bid="shifu-1"
            )
            == "default-voice"
        )

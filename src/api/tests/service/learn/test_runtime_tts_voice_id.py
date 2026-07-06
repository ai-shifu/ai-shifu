from types import SimpleNamespace

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

import flaskr.dao as dao

if dao.db is None:
    _test_app = Flask("test-runtime-tts-voice-id")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

if not hasattr(dao, "redis_client"):
    dao.redis_client = None


class _Col:
    """Stand-in for a SQLAlchemy column expression used in filter/order_by."""

    def desc(self):
        return self

    def __eq__(self, other):
        return False


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


def _make_fake_clone_model(first_result):
    return type(
        "_FakeCloneModel",
        (),
        {
            "voice_id": _Col(),
            "deleted": _Col(),
            "id": _Col(),
            "query": _FakeQuery(first_result),
        },
    )


def _fake_app():
    return SimpleNamespace(
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None)
    )


def _patch_provider(monkeypatch, built_in_values, default_voice_id="default-voice"):
    provider_config = SimpleNamespace(
        voices=[{"value": value} for value in built_in_values]
    )
    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.get_tts_provider",
        lambda _provider: SimpleNamespace(
            get_provider_config=lambda: provider_config
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.learn.learn_funcs.get_default_voice_settings",
        lambda _provider: SimpleNamespace(voice_id=default_voice_id),
    )


def test_non_minimax_provider_returns_voice_id_unchanged(monkeypatch):
    from flaskr.service.learn import learn_funcs

    # Non-MiniMax providers are trusted as-is; no provider/DB lookups happen.
    assert (
        learn_funcs._resolve_runtime_tts_voice_id(_fake_app(), "tencent", "any-voice")
        == "any-voice"
    )


def test_minimax_builtin_voice_is_kept(monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch, ["builtin-1", "builtin-2"])
    assert (
        learn_funcs._resolve_runtime_tts_voice_id(_fake_app(), "MiniMax", "builtin-1")
        == "builtin-1"
    )


def test_minimax_ready_cloned_voice_is_kept(monkeypatch):
    from flaskr.service.learn import learn_funcs
    from flaskr.service.tts.models import TTS_MINIMAX_CLONE_STATUS_READY

    _patch_provider(monkeypatch, ["builtin-1"])
    monkeypatch.setattr(
        learn_funcs,
        "TTSMiniMaxClonedVoice",
        _make_fake_clone_model(
            SimpleNamespace(status=TTS_MINIMAX_CLONE_STATUS_READY)
        ),
    )
    assert (
        learn_funcs._resolve_runtime_tts_voice_id(
            _fake_app(), "minimax", "clone-ready"
        )
        == "clone-ready"
    )


def test_minimax_stale_voice_falls_back_to_default(monkeypatch):
    from flaskr.service.learn import learn_funcs

    _patch_provider(monkeypatch, ["builtin-1"], default_voice_id="default-voice")
    # Not a built-in voice and no ready clone tracked -> fall back to default.
    monkeypatch.setattr(
        learn_funcs,
        "TTSMiniMaxClonedVoice",
        _make_fake_clone_model(None),
    )
    assert (
        learn_funcs._resolve_runtime_tts_voice_id(_fake_app(), "minimax", "stale-voice")
        == "default-voice"
    )


def test_minimax_empty_voice_id_returns_empty(monkeypatch):
    from flaskr.service.learn import learn_funcs

    assert learn_funcs._resolve_runtime_tts_voice_id(_fake_app(), "minimax", "") == ""

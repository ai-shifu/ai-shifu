from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaskr.dao import db
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.tts.validation import (
    assert_preview_cloned_voice_available,
)
from flaskr.service.tts.models import (
    TTSMiniMaxClonedVoice,
    TTS_MINIMAX_CLONE_STATUS_FAILED,
    TTS_MINIMAX_CLONE_STATUS_READY,
)


_BUILT_IN_VOICE_ID = "female-shaonv"


@pytest.fixture(autouse=True)
def _fake_minimax_provider(monkeypatch):
    """Isolate the guard from real provider config/credentials."""
    provider = SimpleNamespace(
        get_provider_config=lambda: SimpleNamespace(
            voices=[{"value": _BUILT_IN_VOICE_ID, "label": "少女音色"}]
        )
    )
    monkeypatch.setattr(
        "flaskr.service.tts.validation.get_tts_provider",
        lambda _name: provider,
        raising=False,
    )


def _prepare_tables(app) -> None:
    with app.app_context():
        TTSMiniMaxClonedVoice.__table__.create(db.engine, checkfirst=True)


def _seed_clone(
    app,
    *,
    voice_id: str,
    owner: str,
    status: str,
    deleted: int = 0,
    provider: str = "minimax",
):
    with app.app_context():
        db.session.add(
            TTSMiniMaxClonedVoice(
                voice_bid=f"vb-{voice_id}-{owner}-{provider}",
                owner_user_bid=owner,
                shifu_bid="",
                display_name=voice_id,
                provider=provider,
                voice_id=voice_id,
                status=status,
                deleted=deleted,
            )
        )
        db.session.commit()


def test_built_in_voice_is_always_allowed(app):
    _prepare_tables(app)
    with app.app_context():
        # No clone rows, unknown owner: a built-in voice must still pass.
        assert_preview_cloned_voice_available(
            app, provider="minimax", voice_id=_BUILT_IN_VOICE_ID, owner_user_bid=""
        )


def test_ready_clone_owned_by_requester_is_allowed(app):
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="AiShifu_ready_1",
        owner="creator-1",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
    )
    with app.app_context():
        assert_preview_cloned_voice_available(
            app,
            provider="minimax",
            voice_id="AiShifu_ready_1",
            owner_user_bid="creator-1",
        )


def test_ready_clone_owned_by_another_user_is_rejected(app):
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="AiShifu_ready_2",
        owner="other-creator",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
    )
    with app.app_context():
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app,
                provider="minimax",
                voice_id="AiShifu_ready_2",
                owner_user_bid="creator-1",
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_isolation_when_same_voice_id_has_different_owners(app):
    """Two clones share the same voice_id but differ by owner: the requester
    only matches their own row, never the foreign one."""
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="AiShifu_shared_id",
        owner="creator-1",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
    )
    _seed_clone(
        app,
        voice_id="AiShifu_shared_id",
        owner="creator-2",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
    )
    with app.app_context():
        # creator-1 owns a ready clone with this id -> allowed.
        assert_preview_cloned_voice_available(
            app,
            provider="minimax",
            voice_id="AiShifu_shared_id",
            owner_user_bid="creator-1",
        )
        # creator-3 owns none -> rejected even though the id exists for others.
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app,
                provider="minimax",
                voice_id="AiShifu_shared_id",
                owner_user_bid="creator-3",
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_custom_voice_with_empty_owner_is_rejected(app):
    """An empty owner must not bypass owner scoping and match any ready clone."""
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="AiShifu_ready_owned",
        owner="creator-1",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
    )
    with app.app_context():
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app,
                provider="minimax",
                voice_id="AiShifu_ready_owned",
                owner_user_bid="",
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_failed_clone_is_rejected(app):
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="AiShifu_failed_1",
        owner="creator-1",
        status=TTS_MINIMAX_CLONE_STATUS_FAILED,
    )
    with app.app_context():
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app,
                provider="minimax",
                voice_id="AiShifu_failed_1",
                owner_user_bid="creator-1",
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_deleted_clone_is_rejected(app):
    """A ready, owned clone that has been soft-deleted is rejected like an
    unknown voice."""
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="AiShifu_deleted_1",
        owner="creator-1",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
        deleted=1,
    )
    with app.app_context():
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app,
                provider="minimax",
                voice_id="AiShifu_deleted_1",
                owner_user_bid="creator-1",
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_unknown_custom_voice_is_rejected(app):
    _prepare_tables(app)
    with app.app_context():
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app,
                provider="minimax",
                voice_id="AiShifu_does_not_exist",
                owner_user_bid="creator-1",
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_empty_voice_id_is_rejected(app):
    _prepare_tables(app)
    with app.app_context():
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app, provider="minimax", voice_id="   ", owner_user_bid="creator-1"
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_volcengine_ready_clone_owned_by_requester_is_allowed(app):
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="S_v57vvPYM1",
        owner="creator-1",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
        provider="volcengine",
    )
    with app.app_context():
        assert_preview_cloned_voice_available(
            app,
            provider="volcengine",
            voice_id="S_v57vvPYM1",
            owner_user_bid="creator-1",
        )


def test_volcengine_ready_clone_of_another_owner_is_rejected(app):
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="S_w57vvPYM1",
        owner="other-creator",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
        provider="volcengine",
    )
    with app.app_context():
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app,
                provider="volcengine",
                voice_id="S_w57vvPYM1",
                owner_user_bid="creator-1",
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]


def test_volcengine_clone_row_does_not_leak_to_minimax_provider(app):
    """A ready volcengine row must not authorize the same id under minimax."""
    _prepare_tables(app)
    _seed_clone(
        app,
        voice_id="S_x57vvPYM1",
        owner="creator-1",
        status=TTS_MINIMAX_CLONE_STATUS_READY,
        provider="volcengine",
    )
    with app.app_context():
        with pytest.raises(AppException) as exc_info:
            assert_preview_cloned_voice_available(
                app,
                provider="minimax",
                voice_id="S_x57vvPYM1",
                owner_user_bid="creator-1",
            )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]

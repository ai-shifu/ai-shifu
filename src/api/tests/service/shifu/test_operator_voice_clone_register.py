from __future__ import annotations

from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.user.consts import USER_STATE_REGISTERED

REGISTER_PATH = "/api/shifu/admin/operations/voice-clones"
VOICES_PATH = "/api/shifu/tts/minimax/voices"


def _prepare_minimax_tables(app) -> None:
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    with app.app_context():
        TTSMiniMaxClonedVoice.__table__.create(db.engine, checkfirst=True)


def _seed_teacher(
    app,
    *,
    user_bid: str,
    nickname: str = "Teacher",
    identify: str = "13800000000",
    is_creator: bool = True,
) -> None:
    from flaskr.service.user.models import UserInfo as UserEntity

    with app.app_context():
        db.session.query(UserEntity).filter(UserEntity.user_bid == user_bid).delete(
            synchronize_session=False
        )
        db.session.add(
            UserEntity(
                user_bid=user_bid,
                user_identify=identify,
                nickname=nickname,
                state=USER_STATE_REGISTERED,
                is_creator=1 if is_creator else 0,
            )
        )
        db.session.commit()


def _mock_operator(
    monkeypatch, user_id: str = "operator-1", *, is_operator: bool = True
) -> None:
    dummy = SimpleNamespace(
        user_id=user_id,
        is_operator=is_operator,
        is_creator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda *_args, **_kwargs: dummy,
        raising=False,
    )


def _mock_creator(monkeypatch, user_id: str) -> None:
    dummy = SimpleNamespace(
        user_id=user_id,
        is_operator=False,
        is_creator=True,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda *_args, **_kwargs: dummy,
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.validate_user",
        lambda *_args, **_kwargs: dummy,
        raising=False,
    )


def _bypass_voice_verification(monkeypatch) -> None:
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.voice_clones.get_default_voice_settings",
        lambda *_args, **_kwargs: SimpleNamespace(voice_id=""),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.voice_clones.synthesize_text",
        lambda *_args, **_kwargs: SimpleNamespace(audio_data=b"audio"),
    )


def test_operator_voice_clone_register_requires_operator(app, test_client, monkeypatch):
    _prepare_minimax_tables(app)
    _mock_operator(monkeypatch, is_operator=False)

    resp = test_client.post(
        REGISTER_PATH,
        json={
            "owner_user_bid": "teacher-1",
            "display_name": "Voice",
            "voice_id": "AiShifu_teacher_1",
        },
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert payload["code"] == ERROR_CODE["server.shifu.noPermission"]


def test_operator_voice_clone_register_creates_ready_free_voice(
    app, test_client, monkeypatch
):
    from flaskr.service.tts.models import (
        TTSMiniMaxClonedVoice,
        TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED,
        TTS_MINIMAX_CLONE_STATUS_READY,
    )

    _prepare_minimax_tables(app)
    _seed_teacher(app, user_bid="teacher-1")
    _mock_operator(monkeypatch)
    _bypass_voice_verification(monkeypatch)

    resp = test_client.post(
        REGISTER_PATH,
        json={
            "owner_user_bid": "teacher-1",
            "display_name": "Teacher Voice",
            "voice_id": "AiShifu_teacher_voice",
        },
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert payload["code"] == 0
    data = payload["data"]
    assert data["owner_user_bid"] == "teacher-1"
    assert data["voice_id"] == "AiShifu_teacher_voice"
    assert data["status"] == TTS_MINIMAX_CLONE_STATUS_READY
    assert data["billing_status"] == TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED

    with app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(
            voice_id="AiShifu_teacher_voice"
        ).one()
        assert row.owner_user_bid == "teacher-1"
        assert row.shifu_bid == ""
        assert row.status == TTS_MINIMAX_CLONE_STATUS_READY
        assert row.billing_status == TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED
        assert row.charged_credits == 0
        assert row.source_capture_method == "operator_register"


def test_operator_voice_clone_register_rejects_non_teacher_owner(
    app, test_client, monkeypatch
):
    _prepare_minimax_tables(app)
    _seed_teacher(app, user_bid="not-a-teacher", is_creator=False)
    _mock_operator(monkeypatch)
    _bypass_voice_verification(monkeypatch)

    resp = test_client.post(
        REGISTER_PATH,
        json={
            "owner_user_bid": "not-a-teacher",
            "display_name": "Voice",
            "voice_id": "AiShifu_not_teacher",
        },
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert payload["code"] == ERROR_CODE["server.common.paramsError"]


def test_operator_registered_voice_visible_only_to_owner(app, test_client, monkeypatch):
    _prepare_minimax_tables(app)
    _seed_teacher(app, user_bid="teacher-a", identify="13800000001")
    _seed_teacher(app, user_bid="teacher-b", identify="13800000002")
    _mock_operator(monkeypatch)
    _bypass_voice_verification(monkeypatch)

    register_resp = test_client.post(
        REGISTER_PATH,
        json={
            "owner_user_bid": "teacher-a",
            "display_name": "Teacher A Voice",
            "voice_id": "AiShifu_teacher_a",
        },
        headers={"Token": "test-token"},
    )
    assert register_resp.get_json(force=True)["code"] == 0

    _mock_creator(monkeypatch, "teacher-a")
    owner_resp = test_client.get(VOICES_PATH, headers={"Token": "test-token"})
    owner_payload = owner_resp.get_json(force=True)
    assert owner_payload["code"] == 0
    assert "AiShifu_teacher_a" in [
        voice["voice_id"] for voice in owner_payload["data"]["voices"]
    ]

    _mock_creator(monkeypatch, "teacher-b")
    other_resp = test_client.get(VOICES_PATH, headers={"Token": "test-token"})
    other_payload = other_resp.get_json(force=True)
    assert other_payload["code"] == 0
    assert "AiShifu_teacher_a" not in [
        voice["voice_id"] for voice in other_payload["data"]["voices"]
    ]

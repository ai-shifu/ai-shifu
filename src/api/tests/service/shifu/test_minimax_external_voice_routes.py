"""Verify externally created MiniMax voice route behavior."""

from __future__ import annotations

from flaskr.dao import db
from flaskr.service.common.dtos import UserInfo
from flaskr.service.tts.models import TTS_MINIMAX_CLONE_STATUS_READY
from flaskr.service.user.consts import USER_STATE_REGISTERED


def _creator_user(user_bid: str = "creator-route") -> UserInfo:
    return UserInfo(
        user_id=user_bid,
        username=user_bid,
        name="Teacher",
        email="",
        mobile="",
        user_state=USER_STATE_REGISTERED,
        wx_openid="",
        language="en-US",
        is_creator=True,
    )


def _prepare_voice_table(app: object) -> None:
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    with app.app_context():
        TTSMiniMaxClonedVoice.__table__.create(db.engine, checkfirst=True)


def _auth(monkeypatch: object, user_bid: str = "creator-route") -> None:
    user = _creator_user(user_bid)
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda *_args: user)
    monkeypatch.setattr("flaskr.service.shifu.route.validate_user", lambda *_args: user)


def test_minimax_validate_custom_voice_id_route(
    app: object, test_client: object, monkeypatch: object
) -> None:
    _prepare_voice_table(app)
    _auth(monkeypatch)

    response = test_client.post(
        "/api/shifu/tts/minimax/voices/validate-id",
        json={"voice_id": "AiShifu_route_1"},
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["valid"] is True


def test_minimax_voice_list_returns_only_current_owners_registered_voices(
    app: object, test_client: object, monkeypatch: object
) -> None:
    from flaskr.service.tts.models import TTSMiniMaxClonedVoice

    _prepare_voice_table(app)
    _auth(monkeypatch)

    with app.app_context():
        db.session.add_all(
            [
                TTSMiniMaxClonedVoice(
                    voice_bid="owned-voice-bid",
                    owner_user_bid="creator-route",
                    shifu_bid="",
                    display_name="External voice",
                    provider="minimax",
                    voice_id="AiShifu_xxxxxxxxxx",
                    status=TTS_MINIMAX_CLONE_STATUS_READY,
                ),
                TTSMiniMaxClonedVoice(
                    voice_bid="other-voice-bid",
                    owner_user_bid="other-creator",
                    shifu_bid="",
                    display_name="Other voice",
                    provider="minimax",
                    voice_id="AiShifu_xxxxxxxxxx",
                    status=TTS_MINIMAX_CLONE_STATUS_READY,
                ),
            ]
        )
        db.session.commit()

    response = test_client.get(
        "/api/shifu/tts/minimax/voices",
        query_string={"provider": "minimax"},
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert payload["code"] == 0
    assert [voice["voice_id"] for voice in payload["data"]["voices"]] == [
        "AiShifu_xxxxxxxxxx"
    ]
    assert [voice["voice_bid"] for voice in payload["data"]["voices"]] == [
        "owned-voice-bid"
    ]
    assert [voice["owner_user_bid"] for voice in payload["data"]["voices"]] == [
        "creator-route"
    ]

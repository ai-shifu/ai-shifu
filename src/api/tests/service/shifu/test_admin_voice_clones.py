from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flaskr.dao import db
from flaskr.service.shifu.admin_operations.voice_clones import (
    list_operator_voice_clones,
)
from flaskr.service.shifu.models import DraftShifu
from flaskr.service.tts.models import TTSMiniMaxClonedVoice
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity


def _prepare_tables(app) -> None:
    with app.app_context():
        TTSMiniMaxClonedVoice.__table__.create(db.engine, checkfirst=True)


def _clear_rows() -> None:
    db.session.query(TTSMiniMaxClonedVoice).delete(synchronize_session=False)
    db.session.query(AuthCredential).filter(
        AuthCredential.user_bid.in_(["voice-owner", "other-owner"])
    ).delete(synchronize_session=False)
    db.session.query(UserEntity).filter(
        UserEntity.user_bid.in_(["voice-owner", "other-owner"])
    ).delete(synchronize_session=False)
    db.session.query(DraftShifu).filter(
        DraftShifu.shifu_bid.in_(["voice-course", "other-course"])
    ).delete(synchronize_session=False)
    db.session.commit()


def _seed_voice_clone_rows() -> None:
    user = UserEntity(
        user_bid="voice-owner",
        user_identify="voice-owner@example.com",
        nickname="Voice Owner",
        deleted=0,
    )
    credential = AuthCredential(
        credential_bid="cred-voice-owner",
        user_bid="voice-owner",
        provider_name="email",
        identifier="voice-owner@example.com",
        deleted=0,
    )
    course = DraftShifu(
        shifu_bid="voice-course",
        title="Voice Course",
        created_user_bid="voice-owner",
        updated_user_bid="voice-owner",
        deleted=0,
    )
    ready_voice = TTSMiniMaxClonedVoice(
        voice_bid="voice-ready",
        owner_user_bid="voice-owner",
        shifu_bid="voice-course",
        display_name="Ready Voice",
        voice_id="AiShifu_ready_1",
        status="ready",
        billing_status="charged",
        estimated_credits=Decimal("1.0000000000"),
        charged_credits=Decimal("1.0000000000"),
        created_at=datetime(2026, 6, 20, 8, 0, 0),
        updated_at=datetime(2026, 6, 20, 8, 1, 0),
        ready_at=datetime(2026, 6, 20, 8, 1, 0),
    )
    failed_voice = TTSMiniMaxClonedVoice(
        voice_bid="voice-failed",
        owner_user_bid="other-owner",
        shifu_bid="other-course",
        display_name="Failed Voice",
        voice_id="AiShifu_failed_1",
        status="failed",
        status_msg="MiniMax rejected the source audio",
        failure_reason="provider_rejected",
        minimax_status_code=1001,
        minimax_status_msg="invalid audio",
        billing_status="released",
        created_at=datetime(2026, 6, 21, 8, 0, 0),
        updated_at=datetime(2026, 6, 21, 8, 1, 0),
    )
    db.session.add_all([user, credential, course, ready_voice, failed_voice])
    db.session.commit()


def test_list_operator_voice_clones_returns_owner_course_and_status(app):
    _prepare_tables(app)
    with app.app_context():
        _clear_rows()
        _seed_voice_clone_rows()

        result = list_operator_voice_clones(
            app,
            page_index=1,
            page_size=20,
            filters={"status": "ready"},
        )

    assert result["total"] == 1
    assert result["page_count"] == 1
    item = result["items"][0]
    assert item["voice_bid"] == "voice-ready"
    assert item["owner_email"] == "voice-owner@example.com"
    assert item["owner_nickname"] == "Voice Owner"
    assert item["course_name"] == "Voice Course"
    assert item["billing_status"] == "charged"
    assert item["charged_credits"] == "1"


def test_list_operator_voice_clones_filters_failure_and_provider_code(app):
    _prepare_tables(app)
    with app.app_context():
        _clear_rows()
        _seed_voice_clone_rows()

        result = list_operator_voice_clones(
            app,
            page_index=1,
            page_size=20,
            filters={
                "failure_reason": "provider_rejected",
                "minimax_status_code": 1001,
            },
        )

    assert result["total"] == 1
    item = result["items"][0]
    assert item["voice_bid"] == "voice-failed"
    assert item["status"] == "failed"
    assert item["minimax_status_msg"] == "invalid audio"


def test_list_operator_voice_clones_filters_voice_name(app):
    _prepare_tables(app)
    with app.app_context():
        _clear_rows()
        _seed_voice_clone_rows()

        result = list_operator_voice_clones(
            app,
            page_index=1,
            page_size=20,
            filters={"voice_keyword": "Ready"},
        )

    assert result["total"] == 1
    assert result["items"][0]["voice_bid"] == "voice-ready"


def test_list_operator_voice_clones_filters_owner_nickname_without_user_bid(app):
    _prepare_tables(app)
    with app.app_context():
        _clear_rows()
        _seed_voice_clone_rows()

        nickname_result = list_operator_voice_clones(
            app,
            page_index=1,
            page_size=20,
            filters={"user_keyword": "Voice Ow"},
        )
        user_bid_result = list_operator_voice_clones(
            app,
            page_index=1,
            page_size=20,
            filters={"user_keyword": "voice-owner"},
        )

    assert nickname_result["total"] == 1
    assert nickname_result["items"][0]["voice_bid"] == "voice-ready"
    assert user_bid_result["total"] == 0


def test_list_operator_voice_clones_filters_course_keyword(app):
    _prepare_tables(app)
    with app.app_context():
        _clear_rows()
        _seed_voice_clone_rows()

        result = list_operator_voice_clones(
            app,
            page_index=1,
            page_size=20,
            filters={"course_keyword": "Voice Course"},
        )

    assert result["total"] == 1
    assert result["items"][0]["voice_bid"] == "voice-ready"

"""Verify voice deletion and retries preserve ownership and billing state."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.tts import minimax_voice_clone as clone
from flaskr.service.tts.models import TTSMiniMaxClonedVoice
from flaskr.util.datetime import now_utc

from tests.service.tts.test_minimax_voice_clone import minimax_clone_app as clone_app

__all__ = ["clone_app"]


def _voice(**fields: object) -> TTSMiniMaxClonedVoice:
    values = {
        "voice_bid": "voice",
        "owner_user_bid": "owner",
        "shifu_bid": "course",
        "voice_id": "AiShifu_voice_123",
        "status": clone.TTS_MINIMAX_CLONE_STATUS_FAILED,
        "billing_status": clone.TTS_MINIMAX_CLONE_BILLING_RESERVED,
        "billing_reservation_bid": "reservation",
        "billing_ledger_bid": "ledger",
        "estimated_credits": Decimal(3),
        "charged_credits": Decimal(2),
        "status_msg": "prior failure",
        "failure_reason": "provider_failure",
    }
    values.update(fields)
    voice = TTSMiniMaxClonedVoice(**values)
    db.session.add(voice)
    db.session.commit()
    return voice


def test_foreign_voice_lookup_is_forbidden_without_mutating_the_record(
    clone_app: object,
) -> None:
    _voice()
    with pytest.raises(AppError) as caught:
        clone.get_minimax_cloned_voice(
            clone_app, owner_user_bid="stranger", voice_bid="voice"
        )
    assert caught.value.code == ERROR_CODE["server.shifu.noPermission"]
    db.session.expire_all()
    row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid="voice").one()
    assert row.owner_user_bid == "owner"
    assert row.deleted == 0


def test_owner_deletion_is_persisted_and_default_catalog_hides_the_voice(
    clone_app: object,
) -> None:
    _voice()
    before = now_utc()
    clone.delete_minimax_cloned_voice(
        clone_app, owner_user_bid="owner", voice_bid="voice"
    )
    db.session.expire_all()
    row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid="voice").one()
    assert row.deleted == 1
    assert before <= row.deleted_at <= now_utc()
    assert clone.list_minimax_cloned_voices(clone_app, owner_user_bid="owner") == []
    history = clone.list_minimax_cloned_voices(
        clone_app, owner_user_bid="owner", include_deleted=True
    )
    assert len(history) == 1
    assert history[0]["voice_bid"] == "voice"


@pytest.mark.parametrize("billing_enabled", [False, True])
def test_retry_reuses_existing_reservation_or_clears_it_when_billing_is_disabled(
    clone_app: object,
    monkeypatch: pytest.MonkeyPatch,
    billing_enabled: bool,
) -> None:
    _voice(status=clone.TTS_MINIMAX_CLONE_STATUS_BILLING_PENDING)
    monkeypatch.setattr(clone, "is_billing_enabled", lambda: billing_enabled)
    monkeypatch.setattr(
        clone,
        "estimate_voice_clone_operation_credits",
        Mock(return_value=SimpleNamespace(consumed_credits=Decimal(3))),
    )
    admit, reserve, enqueue = Mock(), Mock(), Mock()
    monkeypatch.setattr(clone, "admit_creator_usage", admit)
    monkeypatch.setattr(clone, "reserve_operation_credits", reserve)
    monkeypatch.setattr(clone, "_enqueue_minimax_clone_task", enqueue)
    result = clone.retry_minimax_voice_clone(
        clone_app, owner_user_bid="owner", voice_bid="voice"
    )
    db.session.expire_all()
    row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid="voice").one()
    assert row.status == clone.TTS_MINIMAX_CLONE_STATUS_QUEUED
    assert result["status"] == row.status
    assert row.retry_count == 1
    assert row.status_msg == row.failure_reason == ""
    assert row.estimated_credits == Decimal(3)
    if billing_enabled:
        assert row.billing_reservation_bid == "reservation"
        assert row.billing_ledger_bid == "ledger"
        assert row.billing_status == clone.TTS_MINIMAX_CLONE_BILLING_RESERVED
    else:
        assert row.billing_reservation_bid == row.billing_ledger_bid == ""
        assert row.charged_credits == 0
        assert row.billing_status == clone.TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED
    admit.assert_not_called()
    reserve.assert_not_called()
    enqueue.assert_called_once_with(clone_app, voice_bid="voice")


def test_non_retryable_voice_keeps_its_state_and_never_touches_billing(
    clone_app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _voice(status=clone.TTS_MINIMAX_CLONE_STATUS_READY)
    estimate = Mock()
    monkeypatch.setattr(clone, "estimate_voice_clone_operation_credits", estimate)
    with pytest.raises(AppError) as caught:
        clone.retry_minimax_voice_clone(
            clone_app, owner_user_bid="owner", voice_bid="voice"
        )
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]
    db.session.expire_all()
    row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid="voice").one()
    assert row.status == clone.TTS_MINIMAX_CLONE_STATUS_READY
    assert row.retry_count == 0
    estimate.assert_not_called()

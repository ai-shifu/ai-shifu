"""Verify audit and metering writes survive a caller rollback."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flaskr import dao
from flaskr.dao.uow import unit_of_work

if TYPE_CHECKING:
    from flask import Flask


def test_risk_control_result_survives_caller_rollback(app: Flask) -> None:
    """The audit row remains when the surrounding unit of work fails."""
    from flaskr.service.check_risk.funcs import add_risk_control_result
    from flaskr.service.check_risk.models import RiskControlResult
    from flaskr.service.shifu.models import DraftShifu

    def caller_fails_after_audit_write() -> None:
        with unit_of_work():
            dao.db.session.add(
                DraftShifu(
                    shifu_bid="b7-risk-caller-1",
                    title="rolled back",
                    created_user_bid="user-1",
                    updated_user_bid="user-1",
                )
            )
            result_id = add_risk_control_result(
                app,
                "chat-b7",
                "user-1",
                "text",
                "vendor",
                "pass",
                "{}",
                1,
                "check_text",
            )
            assert result_id > 0
            raise RuntimeError

    with app.app_context():
        with pytest.raises(RuntimeError):
            caller_fails_after_audit_write()

        dao.db.session.expire_all()
        assert DraftShifu.query.filter_by(shifu_bid="b7-risk-caller-1").count() == 0
        assert RiskControlResult.query.filter_by(chat_id="chat-b7").count() == 1


def test_usage_record_survives_caller_rollback(app: Flask) -> None:
    """Metering rows remain when the surrounding unit of work fails."""
    from flaskr.service.metering import UsageContext, record_tts_usage
    from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW
    from flaskr.service.metering.models import BillUsageRecord
    from flaskr.service.shifu.models import DraftShifu

    usage_bids: list[str] = []

    def caller_fails_after_usage_write() -> None:
        with unit_of_work():
            dao.db.session.add(
                DraftShifu(
                    shifu_bid="b7-usage-caller-1",
                    title="rolled back",
                    created_user_bid="user-1",
                    updated_user_bid="user-1",
                )
            )
            usage_bid = record_tts_usage(
                app,
                UsageContext(
                    user_bid="user-1",
                    shifu_bid="shifu-b7",
                    usage_scene=BILL_USAGE_SCENE_PREVIEW,
                    billable=0,
                ),
                provider="minimax",
                model="speech-2.8-turbo",
                is_stream=False,
                input=1,
                output=0,
                total=1,
                word_count=0,
                duration_ms=0,
                latency_ms=0,
                enqueue_settlement=False,
            )
            assert usage_bid
            usage_bids.append(usage_bid)
            raise RuntimeError

    with app.app_context():
        with pytest.raises(RuntimeError):
            caller_fails_after_usage_write()

        dao.db.session.expire_all()
        assert DraftShifu.query.filter_by(shifu_bid="b7-usage-caller-1").count() == 0
        assert BillUsageRecord.query.filter_by(usage_bid=usage_bids[0]).count() == 1

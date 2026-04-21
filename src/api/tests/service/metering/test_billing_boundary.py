from __future__ import annotations

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.metering import UsageContext, record_llm_usage, record_tts_usage
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.metering.models import BillUsageRecord


@pytest.fixture
def metering_billing_boundary_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_record_llm_usage_only_persists_bill_usage(
    metering_billing_boundary_app: Flask,
) -> None:
    with metering_billing_boundary_app.app_context():
        usage_bid = record_llm_usage(
            metering_billing_boundary_app,
            UsageContext(
                user_bid="learner-1",
                shifu_bid="shifu-1",
                usage_scene=BILL_USAGE_SCENE_PROD,
            ),
            provider="openai",
            model="gpt-test",
            is_stream=False,
            input=12,
            output=8,
            total=20,
        )

        assert usage_bid
        assert BillUsageRecord.query.filter_by(usage_bid=usage_bid).count() == 1
        assert CreditWallet.query.count() == 0
        assert CreditWalletBucket.query.count() == 0
        assert CreditLedgerEntry.query.count() == 0


def test_record_tts_usage_only_persists_bill_usage(
    metering_billing_boundary_app: Flask,
) -> None:
    with metering_billing_boundary_app.app_context():
        usage_bid = record_tts_usage(
            metering_billing_boundary_app,
            UsageContext(
                user_bid="learner-2",
                shifu_bid="shifu-2",
                usage_scene=BILL_USAGE_SCENE_PREVIEW,
                audio_bid="audio-2",
            ),
            provider="minimax",
            model="speech-01",
            is_stream=True,
            input=15,
            output=15,
            total=15,
            word_count=15,
            duration_ms=1234,
            record_level=0,
            segment_count=1,
        )

        assert usage_bid
        assert BillUsageRecord.query.filter_by(usage_bid=usage_bid).count() == 1
        assert CreditWallet.query.count() == 0
        assert CreditWalletBucket.query.count() == 0
        assert CreditLedgerEntry.query.count() == 0

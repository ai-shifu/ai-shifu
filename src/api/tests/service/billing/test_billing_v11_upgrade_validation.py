from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.daily_aggregates import rebuild_daily_aggregates
from flaskr.service.billing.entitlements import (
    resolve_creator_entitlement_state,
    serialize_creator_entitlements,
)
from flaskr.service.billing.models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditUsageRate,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord
from tests.common.fixtures.bill_products import build_billing_product

_API_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def billing_v11_upgrade_app() -> Flask:
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


def test_billing_v11_upgrade_migration_chain_extends_v1_schema() -> None:
    source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "b114d7f5e2c1"' in source
    assert 'down_revision = "1c8f4b7a9d2e"' in source
    assert 'op.create_table(\n        "bill_entitlements",' in source
    assert 'op.create_table(\n        "bill_domain_bindings",' in source
    assert 'op.create_table(\n        "bill_daily_usage_metrics",' in source
    assert 'op.create_table(\n        "bill_daily_ledger_summary",' in source
    assert not (
        _API_ROOT / "migrations/versions/c225e8a6f3d2_add_billing_extension_phase.py"
    ).exists()


def test_billing_v11_upgrade_can_backfill_new_views_from_v1_source_rows(
    billing_v11_upgrade_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 4, 8, 12, 0, 0)
    monkeypatch.setattr(
        "flaskr.service.billing.daily_aggregates.resolve_usage_creator_bid",
        lambda app, usage: "creator-upgrade-1",
    )

    with billing_v11_upgrade_app.app_context():
        dao.db.session.add(_seed_yearly_plan_product())
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-upgrade-1",
                creator_bid="creator-upgrade-1",
                product_bid="bill-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=now - timedelta(days=5),
                current_period_end_at=now + timedelta(days=25),
            )
        )
        _add_rate()
        _add_usage(
            usage_bid="usage-upgrade-1",
            shifu_bid="shifu-upgrade-1",
            created_at=datetime(2026, 4, 8, 9, 0, 0),
            input_tokens=120,
        )
        _add_ledger(
            creator_bid="creator-upgrade-1",
            ledger_bid="ledger-upgrade-1",
            source_bid="usage-upgrade-1",
            amount=Decimal("-1.2000000000"),
            created_at=datetime(2026, 4, 8, 9, 1, 0),
        )
        dao.db.session.commit()

        entitlement_state = resolve_creator_entitlement_state(
            "creator-upgrade-1",
            as_of=now,
        )
        rebuild_payload = rebuild_daily_aggregates(
            billing_v11_upgrade_app,
            creator_bid="creator-upgrade-1",
            date_from="2026-04-08",
            date_to="2026-04-08",
        )

        usage_row = BillingDailyUsageMetric.query.filter_by(
            creator_bid="creator-upgrade-1",
            stat_date="2026-04-08",
            shifu_bid="shifu-upgrade-1",
        ).one()
        ledger_row = BillingDailyLedgerSummary.query.filter_by(
            creator_bid="creator-upgrade-1",
            stat_date="2026-04-08",
            source_type=CREDIT_SOURCE_TYPE_USAGE,
        ).one()

    assert entitlement_state["source_kind"] == "product_payload"
    assert entitlement_state["source_type"] == "subscription"
    assert entitlement_state["source_bid"] == "sub-upgrade-1"
    assert serialize_creator_entitlements(entitlement_state) == {
        "branding_enabled": True,
        "custom_domain_enabled": False,
        "priority_class": "priority",
        "analytics_tier": "advanced",
        "support_tier": "business_hours",
    }

    assert rebuild_payload["status"] == "rebuilt"
    assert rebuild_payload["day_count"] == 1
    assert rebuild_payload["usage"]["processed_days"] == 1
    assert rebuild_payload["ledger"]["processed_days"] == 1
    assert int(usage_row.raw_amount or 0) == 120
    assert usage_row.creator_bid == "creator-upgrade-1"
    assert str(usage_row.consumed_credits) == "1.2000000000"
    assert ledger_row.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME
    assert str(ledger_row.amount) == "-1.2000000000"
    assert ledger_row.entry_count == 1


def _seed_yearly_plan_product() -> BillingProduct:
    return build_billing_product(
        "bill-product-plan-yearly",
        overrides={
            "entitlement_payload": {
                "branding_enabled": True,
                "custom_domain_enabled": False,
                "priority_class": "priority",
                "analytics_tier": "advanced",
                "support_tier": "business_hours",
                "feature_payload": {"report_export": True},
            }
        },
    )


def _add_rate() -> None:
    dao.db.session.add(
        CreditUsageRate(
            rate_bid="rate-upgrade-input",
            usage_type=BILL_USAGE_TYPE_LLM,
            provider="openai",
            model="gpt-4o-mini",
            usage_scene=BILL_USAGE_SCENE_PROD,
            billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
            unit_size=60,
            credits_per_unit=Decimal("1.0000000000"),
            rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
            effective_from=datetime(2026, 1, 1, 0, 0, 0),
            status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
        )
    )
    dao.db.session.flush()


def _add_usage(
    *,
    usage_bid: str,
    shifu_bid: str,
    created_at: datetime,
    input_tokens: int,
) -> None:
    dao.db.session.add(
        BillUsageRecord(
            usage_bid=usage_bid,
            user_bid="user-upgrade-1",
            shifu_bid=shifu_bid,
            usage_type=BILL_USAGE_TYPE_LLM,
            usage_scene=BILL_USAGE_SCENE_PROD,
            provider="openai",
            model="gpt-4o-mini",
            input=input_tokens,
            output=0,
            total=input_tokens,
            billable=1,
            status=0,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    dao.db.session.flush()


def _add_ledger(
    *,
    creator_bid: str,
    ledger_bid: str,
    source_bid: str,
    amount: Decimal,
    created_at: datetime,
) -> None:
    dao.db.session.add(
        CreditLedgerEntry(
            ledger_bid=ledger_bid,
            creator_bid=creator_bid,
            wallet_bid=f"wallet-{creator_bid}",
            wallet_bucket_bid=f"bucket-{ledger_bid}",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid=source_bid,
            idempotency_key=f"idempotency-{ledger_bid}",
            amount=amount,
            balance_after=Decimal("0"),
            metadata_json={
                "metric_breakdown": [
                    {
                        "billing_metric_code": BILLING_METRIC_LLM_INPUT_TOKENS,
                        "consumed_credits": str(-amount),
                    }
                ]
            },
            created_at=created_at,
            updated_at=created_at,
        )
    )
    dao.db.session.flush()

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.billing.referral_plan_rewards import (
    ReferralPlanRewardRequest,
    grant_referral_plan_reward,
)
from tests.common.fixtures.bill_products import build_bill_products


@pytest.fixture
def referral_billing_app() -> Flask:
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
        dao.db.session.add_all(
            build_bill_products(
                product_bids=["bill-product-plan-monthly-pro"],
                overrides_by_bid={
                    "bill-product-plan-monthly-pro": {
                        "credit_amount": Decimal("1000.0000000000"),
                    }
                },
            )
        )
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _request(reward_bid: str = "ref-reward-billing-1") -> ReferralPlanRewardRequest:
    return ReferralPlanRewardRequest(
        reward_bid=reward_bid,
        inviter_user_bid="creator-ref-billing-1",
        campaign_bid="ref-campaign-billing",
        reward_rule_bid="ref-rule-billing",
        product_code="creator-plan-monthly-pro",
        cycle_count=1,
        credit_amount=Decimal("1000.0000000000"),
        credit_validity_days=30,
        timing_policy="immediate_extend_or_defer",
        rule_snapshot={
            "reward_product_code": "creator-plan-monthly-pro",
            "reward_cycle_count": 1,
            "reward_credit_amount": "1000.0000000000",
            "reward_credit_validity_days": 30,
            "reward_cap_scope": "per_inviter",
            "reward_cap_count": 12,
        },
    )


def test_referral_plan_reward_creates_manual_paid_order_and_credits(
    referral_billing_app: Flask,
) -> None:
    result = grant_referral_plan_reward(referral_billing_app, request=_request())
    second = grant_referral_plan_reward(referral_billing_app, request=_request())

    assert result.reused_existing_reward is False
    assert second.reused_existing_reward is True
    assert second.bill_order_bid == result.bill_order_bid

    with referral_billing_app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=result.bill_order_bid).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=result.subscription_bid
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            source_bid=order.bill_order_bid
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(
            source_bid=order.bill_order_bid
        ).one()

        assert order.status == BILLING_ORDER_STATUS_PAID
        assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START
        assert order.payment_provider == "manual"
        assert order.provider_reference_id == "referral-reward:ref-reward-billing-1"
        assert order.metadata_json["checkout_type"] == "referral_invitation_reward"
        assert order.metadata_json["campaign_bid"] == "ref-campaign-billing"
        assert order.metadata_json["reward_rule_bid"] == "ref-rule-billing"

        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert subscription.product_bid == "bill-product-plan-monthly-pro"
        assert subscription.current_period_start_at == order.paid_at
        assert (
            subscription.current_period_end_at.isoformat()
            == order.metadata_json["applied_cycle_end_at"]
        )

        assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
        assert bucket.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
        assert bucket.original_credits == Decimal("1000.0000000000")
        assert bucket.effective_to == subscription.current_period_end_at
        assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT


def test_referral_plan_reward_extends_same_manual_plan_subscription(
    referral_billing_app: Flask,
) -> None:
    first = grant_referral_plan_reward(
        referral_billing_app,
        request=_request("ref-reward-billing-extend-1"),
    )
    second = grant_referral_plan_reward(
        referral_billing_app,
        request=_request("ref-reward-billing-extend-2"),
    )

    with referral_billing_app.app_context():
        first_order = BillingOrder.query.filter_by(
            bill_order_bid=first.bill_order_bid
        ).one()
        second_order = BillingOrder.query.filter_by(
            bill_order_bid=second.bill_order_bid
        ).one()
        assert second_order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        assert second_order.subscription_bid == first_order.subscription_bid
        assert (
            second_order.metadata_json["renewal_cycle_start_at"]
            == first_order.metadata_json["applied_cycle_end_at"]
        )


def test_referral_plan_reward_defers_after_higher_paid_subscription(
    referral_billing_app: Flask,
) -> None:
    now = datetime.now()
    current_end = now + timedelta(days=90)
    with referral_billing_app.app_context():
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-higher-paid",
                creator_bid="creator-ref-billing-1",
                product_bid="bill-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="stripe-sub-higher",
                provider_customer_id="stripe-cus-higher",
                billing_anchor_at=now - timedelta(days=10),
                current_period_start_at=now - timedelta(days=10),
                current_period_end_at=current_end,
                grace_period_end_at=None,
                cancel_at_period_end=0,
                next_product_bid="",
                last_renewed_at=now - timedelta(days=10),
                last_failed_at=None,
                metadata_json={},
            )
        )
        dao.db.session.commit()

    result = grant_referral_plan_reward(
        referral_billing_app,
        request=_request("ref-reward-billing-deferred"),
    )

    with referral_billing_app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=result.bill_order_bid).one()
        assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        assert order.metadata_json["deferred_after_subscription_bid"] == (
            "sub-higher-paid"
        )
        assert order.metadata_json["renewal_cycle_start_at"] == current_end.isoformat()

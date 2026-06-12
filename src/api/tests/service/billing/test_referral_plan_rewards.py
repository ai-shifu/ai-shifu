from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_TRIAL_PRODUCT_BID,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.referral_plan_rewards import (
    ReferralPlanRewardRequest,
    grant_referral_plan_reward,
)
from flaskr.service.billing.queries import (
    calculate_self_managed_billing_cycle_end_after_boundary,
)
from flaskr.service.billing.renewal import run_billing_renewal_event
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
                product_bids=[
                    BILLING_TRIAL_PRODUCT_BID,
                    "bill-product-plan-monthly-pro",
                ],
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


def test_referral_plan_reward_defers_active_trial_subscription_until_boundary(
    referral_billing_app: Flask,
) -> None:
    trial_started_at = datetime.now() - timedelta(minutes=5)
    trial_ends_at = trial_started_at + timedelta(days=15)

    with referral_billing_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-referral-trial-upgrade",
            creator_bid="creator-ref-billing-1",
            available_credits=Decimal("100.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("100.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="sub-referral-trial-upgrade",
            creator_bid="creator-ref-billing-1",
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=trial_started_at,
            current_period_start_at=trial_started_at,
            current_period_end_at=trial_ends_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=trial_started_at,
            last_failed_at=None,
            metadata_json={"trial_bootstrap": True},
        )
        trial_order = BillingOrder(
            bill_order_bid="bill-referral-trial-start",
            creator_bid="creator-ref-billing-1",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=trial_started_at,
            metadata_json={
                "checkout_type": "trial_bootstrap",
                "trial_bootstrap": True,
                "applied_cycle_start_at": trial_started_at.isoformat(),
                "applied_cycle_end_at": trial_ends_at.isoformat(),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-referral-trial-upgrade",
            wallet_bid=wallet.wallet_bid,
            creator_bid="creator-ref-billing-1",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=trial_order.bill_order_bid,
            priority=20,
            original_credits=Decimal("100.0000000000"),
            available_credits=Decimal("100.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=trial_started_at,
            effective_to=trial_ends_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": trial_order.bill_order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-referral-trial-start",
            creator_bid="creator-ref-billing-1",
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=trial_order.bill_order_bid,
            idempotency_key=f"grant:{trial_order.bill_order_bid}",
            amount=Decimal("100.0000000000"),
            balance_after=Decimal("100.0000000000"),
            expires_at=trial_ends_at,
            consumable_from=trial_started_at,
            metadata_json={
                "bill_order_bid": trial_order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "product_bid": trial_order.product_bid,
                "payment_provider": trial_order.payment_provider,
                "grant_reason": "subscription",
                "bucket_credit_state": "available",
            },
        )
        canceled_expire_event = BillingRenewalEvent(
            renewal_event_bid="renewal-referral-trial-upgrade-canceled",
            subscription_bid=subscription.subscription_bid,
            creator_bid=subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=trial_ends_at,
            status=BILLING_RENEWAL_EVENT_STATUS_CANCELED,
            attempt_count=0,
            last_error="",
            payload_json={"source": "pytest"},
            processed_at=trial_started_at,
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                trial_order,
                bucket,
                ledger,
                canceled_expire_event,
            ]
        )
        dao.db.session.commit()

    result = grant_referral_plan_reward(
        referral_billing_app,
        request=_request("ref-reward-billing-trial-upgrade"),
    )

    with referral_billing_app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=result.bill_order_bid).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-referral-trial-upgrade"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-ref-billing-1").one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-referral-trial-upgrade",
        ).one()
        reward_ledger = CreditLedgerEntry.query.filter_by(
            source_bid=order.bill_order_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        ).one()
        expire_event = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=trial_ends_at,
        ).one()
        reward_product = BillingProduct.query.filter_by(
            product_bid="bill-product-plan-monthly-pro"
        ).one()
        expected_reward_end = calculate_self_managed_billing_cycle_end_after_boundary(
            reward_product,
            cycle_boundary_at=trial_ends_at,
        )

        assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        assert order.subscription_bid == "sub-referral-trial-upgrade"
        assert order.metadata_json["deferred_after_product_bid"] == (
            BILLING_TRIAL_PRODUCT_BID
        )
        assert order.metadata_json["deferred_after_subscription_bid"] == (
            "sub-referral-trial-upgrade"
        )
        assert order.metadata_json["deferred_after_entitlement"] == "trial"
        assert order.metadata_json["renewal_cycle_start_at"] == (
            trial_ends_at.isoformat()
        )
        assert (
            order.metadata_json["renewal_cycle_end_at"]
            == expected_reward_end.isoformat()
        )
        assert subscription.product_bid == BILLING_TRIAL_PRODUCT_BID
        assert subscription.current_period_start_at == trial_started_at
        assert subscription.current_period_end_at == trial_ends_at
        assert wallet.available_credits == Decimal("100.0000000000")
        assert wallet.reserved_credits == Decimal("1000.0000000000")
        assert bucket.source_bid == order.bill_order_bid
        assert bucket.available_credits == Decimal("100.0000000000")
        assert bucket.reserved_credits == Decimal("1000.0000000000")
        assert reward_ledger.balance_after == Decimal("100.0000000000")
        assert reward_ledger.consumable_from == trial_ends_at
        assert reward_ledger.expires_at == expected_reward_end
        assert reward_ledger.metadata_json["bucket_credit_state"] == "reserved"
        assert reward_ledger.metadata_json["reserved_until"] == (
            trial_ends_at.isoformat()
        )
        assert expire_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
        assert expire_event.processed_at is None


def test_referral_plan_reward_queues_multiple_trial_rewards_in_order(
    referral_billing_app: Flask,
) -> None:
    trial_started_at = datetime.now() - timedelta(minutes=5)
    trial_ends_at = trial_started_at + timedelta(days=15)

    with referral_billing_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-referral-trial-queue",
            creator_bid="creator-ref-billing-1",
            available_credits=Decimal("100.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("100.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="sub-referral-trial-queue",
            creator_bid="creator-ref-billing-1",
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=trial_started_at,
            current_period_start_at=trial_started_at,
            current_period_end_at=trial_ends_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=trial_started_at,
            last_failed_at=None,
            metadata_json={"trial_bootstrap": True},
        )
        trial_order = BillingOrder(
            bill_order_bid="bill-referral-trial-queue-start",
            creator_bid="creator-ref-billing-1",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=trial_started_at,
            metadata_json={
                "checkout_type": "trial_bootstrap",
                "trial_bootstrap": True,
                "applied_cycle_start_at": trial_started_at.isoformat(),
                "applied_cycle_end_at": trial_ends_at.isoformat(),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-referral-trial-queue",
            wallet_bid=wallet.wallet_bid,
            creator_bid="creator-ref-billing-1",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=trial_order.bill_order_bid,
            priority=20,
            original_credits=Decimal("100.0000000000"),
            available_credits=Decimal("100.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=trial_started_at,
            effective_to=trial_ends_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": trial_order.bill_order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-referral-trial-queue-start",
            creator_bid="creator-ref-billing-1",
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=trial_order.bill_order_bid,
            idempotency_key=f"grant:{trial_order.bill_order_bid}",
            amount=Decimal("100.0000000000"),
            balance_after=Decimal("100.0000000000"),
            expires_at=trial_ends_at,
            consumable_from=trial_started_at,
            metadata_json={
                "bill_order_bid": trial_order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "product_bid": trial_order.product_bid,
                "payment_provider": trial_order.payment_provider,
                "grant_reason": "subscription",
                "bucket_credit_state": "available",
            },
        )
        dao.db.session.add_all([wallet, subscription, trial_order, bucket, ledger])
        dao.db.session.commit()

    first = grant_referral_plan_reward(
        referral_billing_app,
        request=_request("ref-reward-billing-trial-queue-1"),
    )
    second = grant_referral_plan_reward(
        referral_billing_app,
        request=_request("ref-reward-billing-trial-queue-2"),
    )

    with referral_billing_app.app_context():
        first_order = BillingOrder.query.filter_by(
            bill_order_bid=first.bill_order_bid
        ).one()
        second_order = BillingOrder.query.filter_by(
            bill_order_bid=second.bill_order_bid
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-referral-trial-queue"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-ref-billing-1").one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-referral-trial-queue",
        ).one()
        second_ledger = CreditLedgerEntry.query.filter_by(
            source_bid=second_order.bill_order_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        ).one()

        assert first_order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        assert second_order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        assert first_order.metadata_json["renewal_cycle_start_at"] == (
            trial_ends_at.isoformat()
        )
        assert (
            second_order.metadata_json["renewal_cycle_start_at"]
            == (first_order.metadata_json["renewal_cycle_end_at"])
        )
        assert subscription.product_bid == BILLING_TRIAL_PRODUCT_BID
        assert subscription.current_period_end_at == trial_ends_at
        assert wallet.available_credits == Decimal("100.0000000000")
        assert wallet.reserved_credits == Decimal("2000.0000000000")
        assert bucket.available_credits == Decimal("100.0000000000")
        assert bucket.reserved_credits == Decimal("2000.0000000000")
        assert second_ledger.metadata_json["bucket_credit_state"] == "reserved"
        assert (
            second_ledger.consumable_from.isoformat()
            == (first_order.metadata_json["renewal_cycle_end_at"])
        )


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


def test_referral_plan_reward_reserves_future_manual_renewal_credits(
    referral_billing_app: Flask,
) -> None:
    first = grant_referral_plan_reward(
        referral_billing_app,
        request=_request("ref-reward-billing-reserved-1"),
    )
    second = grant_referral_plan_reward(
        referral_billing_app,
        request=_request("ref-reward-billing-reserved-2"),
    )

    with referral_billing_app.app_context():
        first_order = BillingOrder.query.filter_by(
            bill_order_bid=first.bill_order_bid
        ).one()
        second_order = BillingOrder.query.filter_by(
            bill_order_bid=second.bill_order_bid
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=first.subscription_bid
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-ref-billing-1").one()
        bucket = CreditWalletBucket.query.filter_by(
            creator_bid="creator-ref-billing-1",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        ).one()
        renewal_ledger = CreditLedgerEntry.query.filter_by(
            source_bid=second.bill_order_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        ).one()
        expire_ledgers = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-ref-billing-1",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

        assert second_order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        assert second_order.payment_provider == "manual"
        assert second_order.metadata_json["referral_invitation_reward"] is True
        assert (
            second_order.metadata_json["renewal_cycle_start_at"]
            == first_order.metadata_json["applied_cycle_end_at"]
        )
        assert subscription.current_period_start_at == first_order.paid_at
        assert (
            subscription.current_period_end_at.isoformat()
            == first_order.metadata_json["applied_cycle_end_at"]
        )
        assert wallet.available_credits == Decimal("1000.0000000000")
        assert wallet.reserved_credits == Decimal("1000.0000000000")
        assert bucket.original_credits == Decimal("2000.0000000000")
        assert bucket.available_credits == Decimal("1000.0000000000")
        assert bucket.reserved_credits == Decimal("1000.0000000000")
        assert renewal_ledger.balance_after == Decimal("1000.0000000000")
        assert (
            renewal_ledger.consumable_from.isoformat()
            == (second_order.metadata_json["renewal_cycle_start_at"])
        )
        assert renewal_ledger.metadata_json["bucket_credit_state"] == "reserved"
        assert (
            renewal_ledger.metadata_json["reserved_until"]
            == (second_order.metadata_json["renewal_cycle_start_at"])
        )
        assert expire_ledgers == []


def test_referral_plan_reward_releases_reserved_manual_renewal_at_boundary(
    referral_billing_app: Flask,
) -> None:
    boundary_at = datetime.now() - timedelta(minutes=1)
    current_cycle_start = boundary_at - timedelta(days=30)
    next_cycle_end = boundary_at + timedelta(days=30)

    with referral_billing_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-referral-boundary",
            creator_bid="creator-ref-billing-1",
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("2000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="sub-referral-boundary",
            creator_bid="creator-ref-billing-1",
            product_bid="bill-product-plan-monthly-pro",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=current_cycle_start,
            current_period_start_at=current_cycle_start,
            current_period_end_at=boundary_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=current_cycle_start,
            last_failed_at=None,
            metadata_json={"referral_invitation_reward": True},
        )
        order = BillingOrder(
            bill_order_bid="bill-referral-boundary-renewal",
            creator_bid="creator-ref-billing-1",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid="bill-product-plan-monthly-pro",
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="referral-reward:ref-reward-boundary",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=boundary_at - timedelta(days=1),
            metadata_json={
                "checkout_type": "referral_invitation_reward",
                "referral_invitation_reward": True,
                "reward_bid": "ref-reward-boundary",
                "campaign_bid": "ref-campaign-billing",
                "reward_rule_bid": "ref-rule-billing",
                "renewal_cycle_start_at": boundary_at.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-referral-boundary",
            wallet_bid=wallet.wallet_bid,
            creator_bid="creator-ref-billing-1",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="bill-referral-current",
            priority=20,
            original_credits=Decimal("2000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=current_cycle_start,
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "bill-referral-current"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-referral-boundary-renewal",
            creator_bid="creator-ref-billing-1",
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": "subscription",
                "bucket_credit_state": "reserved",
                "reserved_until": boundary_at.isoformat(),
            },
        )
        event = BillingRenewalEvent(
            renewal_event_bid="renewal-referral-boundary",
            subscription_bid=subscription.subscription_bid,
            creator_bid=subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=boundary_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json={"source": "pytest"},
            processed_at=None,
        )
        dao.db.session.add_all([wallet, subscription, order, bucket, ledger, event])
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        referral_billing_app,
        renewal_event_bid="renewal-referral-boundary",
    )

    assert payload.status == "applied"
    assert payload.bill_order_bid == "bill-referral-boundary-renewal"

    with referral_billing_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid="creator-ref-billing-1").one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-referral-boundary",
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-referral-boundary-renewal",
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-referral-boundary",
        ).one()

        assert subscription.current_period_start_at == boundary_at
        assert subscription.current_period_end_at == next_cycle_end
        assert wallet.available_credits == Decimal("1000.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert bucket.source_bid == "bill-referral-boundary-renewal"
        assert bucket.available_credits == Decimal("1000.0000000000")
        assert bucket.reserved_credits == Decimal("0E-10")
        assert bucket.effective_from == boundary_at
        assert bucket.effective_to == next_cycle_end
        assert ledger.metadata_json["bucket_credit_state"] == "available"


def test_referral_plan_reward_releases_reserved_trial_reward_at_boundary(
    referral_billing_app: Flask,
) -> None:
    boundary_at = datetime.now() - timedelta(minutes=1)
    trial_started_at = boundary_at - timedelta(days=15)
    reward_cycle_end = boundary_at + timedelta(days=30)

    with referral_billing_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-referral-trial-boundary",
            creator_bid="creator-ref-billing-1",
            available_credits=Decimal("100.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1100.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="sub-referral-trial-boundary",
            creator_bid="creator-ref-billing-1",
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=trial_started_at,
            current_period_start_at=trial_started_at,
            current_period_end_at=boundary_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=trial_started_at,
            last_failed_at=None,
            metadata_json={"trial_bootstrap": True},
        )
        order = BillingOrder(
            bill_order_bid="bill-referral-trial-boundary-renewal",
            creator_bid="creator-ref-billing-1",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid="bill-product-plan-monthly-pro",
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="referral-reward:ref-reward-trial-boundary",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=boundary_at - timedelta(days=1),
            metadata_json={
                "checkout_type": "referral_invitation_reward",
                "referral_invitation_reward": True,
                "reward_bid": "ref-reward-trial-boundary",
                "campaign_bid": "ref-campaign-billing",
                "reward_rule_bid": "ref-rule-billing",
                "deferred_after_entitlement": "trial",
                "deferred_after_subscription_bid": subscription.subscription_bid,
                "deferred_after_product_bid": BILLING_TRIAL_PRODUCT_BID,
                "renewal_cycle_start_at": boundary_at.isoformat(),
                "renewal_cycle_end_at": reward_cycle_end.isoformat(),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-referral-trial-boundary",
            wallet_bid=wallet.wallet_bid,
            creator_bid="creator-ref-billing-1",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            priority=20,
            original_credits=Decimal("1100.0000000000"),
            available_credits=Decimal("100.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=trial_started_at,
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order.bill_order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-referral-trial-boundary-renewal",
            creator_bid="creator-ref-billing-1",
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("100.0000000000"),
            expires_at=reward_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": "subscription",
                "bucket_credit_state": "reserved",
                "reserved_until": boundary_at.isoformat(),
            },
        )
        event = BillingRenewalEvent(
            renewal_event_bid="renewal-referral-trial-boundary",
            subscription_bid=subscription.subscription_bid,
            creator_bid=subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=boundary_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json={"source": "pytest"},
            processed_at=None,
        )
        dao.db.session.add_all([wallet, subscription, order, bucket, ledger, event])
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        referral_billing_app,
        renewal_event_bid="renewal-referral-trial-boundary",
    )

    assert payload.status == "applied"
    assert payload.bill_order_bid == "bill-referral-trial-boundary-renewal"

    with referral_billing_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid="creator-ref-billing-1").one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-referral-trial-boundary",
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-referral-trial-boundary-renewal",
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-referral-trial-boundary",
        ).one()

        assert subscription.product_bid == "bill-product-plan-monthly-pro"
        assert subscription.current_period_start_at == boundary_at
        assert subscription.current_period_end_at == reward_cycle_end
        assert wallet.available_credits == Decimal("1000.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert bucket.available_credits == Decimal("1000.0000000000")
        assert bucket.reserved_credits == Decimal("0E-10")
        assert bucket.effective_from == boundary_at
        assert bucket.effective_to == reward_cycle_end
        assert ledger.balance_after == Decimal("1000.0000000000")
        assert ledger.metadata_json["bucket_credit_state"] == "available"


def test_referral_plan_reward_defers_after_higher_paid_subscription(
    referral_billing_app: Flask,
) -> None:
    now = datetime.now()
    current_end = now + timedelta(days=90)
    with referral_billing_app.app_context():
        dao.db.session.add_all(
            build_bill_products(product_bids=["bill-product-plan-yearly"])
        )
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
        expire_event = BillingRenewalEvent.query.filter_by(
            subscription_bid="sub-higher-paid",
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=current_end,
        ).one()
        assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        assert order.metadata_json["deferred_after_subscription_bid"] == (
            "sub-higher-paid"
        )
        assert order.metadata_json["renewal_cycle_start_at"] == current_end.isoformat()
        assert expire_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING

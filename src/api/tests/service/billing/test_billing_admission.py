from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.admission import admit_creator_usage
from flaskr.service.billing.consts import (
    BILLING_ENTITLEMENT_PRIORITY_CLASS_VIP,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.models import (
    BillingEntitlement,
    BillingOrder,
    BillingSubscription,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.subscriptions import repair_subscription_cycle_mismatches
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
)
from flaskr.service.shifu.models import PublishedShifu
from tests.common.fixtures.bill_products import build_bill_products


@pytest.fixture
def billing_admission_app(monkeypatch):
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REDIS_KEY_PREFIX="billing-admission-test",
        TZ="UTC",
    )
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled",
        lambda: True,
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _create_wallet(creator_bid: str, available_credits: str) -> CreditWallet:
    return CreditWallet(
        wallet_bid=f"wallet-{creator_bid}",
        creator_bid=creator_bid,
        available_credits=Decimal(available_credits),
        reserved_credits=Decimal("0"),
        lifetime_granted_credits=Decimal("0"),
        lifetime_consumed_credits=Decimal("0"),
    )


def _create_bucket(
    creator_bid: str,
    *,
    category: int,
    available_credits: str,
    effective_from=None,
    effective_to=None,
    source_type: int = 0,
    source_bid: str | None = None,
) -> CreditWalletBucket:
    return CreditWalletBucket(
        wallet_bucket_bid=f"bucket-{creator_bid}-{category}",
        wallet_bid=f"wallet-{creator_bid}",
        creator_bid=creator_bid,
        bucket_category=category,
        source_type=source_type,
        source_bid=source_bid or f"source-{creator_bid}-{category}",
        priority=10,
        original_credits=Decimal(available_credits),
        available_credits=Decimal(available_credits),
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=effective_from or dao.db.func.now(),
        effective_to=effective_to,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
    )


def _create_active_subscription(
    creator_bid: str,
    *,
    status: int = BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    current_period_start_at=None,
    current_period_end_at=None,
) -> BillingSubscription:
    now = datetime.now()
    return BillingSubscription(
        subscription_bid=f"subscription-{creator_bid}",
        creator_bid=creator_bid,
        status=status,
        current_period_start_at=current_period_start_at or now - timedelta(days=1),
        current_period_end_at=current_period_end_at or now + timedelta(days=29),
    )


def test_admit_creator_usage_allows_topup_credits_during_active_subscription(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-topup-1",
                created_user_bid="creator-topup-1",
            )
        )
        dao.db.session.add(_create_wallet("creator-topup-1", "25.0000000000"))
        dao.db.session.add(_create_active_subscription("creator-topup-1"))
        dao.db.session.add(
            _create_bucket(
                "creator-topup-1",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                available_credits="25.0000000000",
            )
        )
        dao.db.session.commit()

    payload = admit_creator_usage(
        billing_admission_app,
        shifu_bid="shifu-topup-1",
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
    )

    assert payload["allowed"] is True
    assert payload["creator_bid"] == "creator-topup-1"
    assert payload["usage_scene"] == BILL_USAGE_SCENE_PREVIEW
    assert payload["wallet_available_credits"] == Decimal("25.0000000000")


def test_admit_creator_usage_rejects_topup_credits_without_active_subscription(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-topup-no-sub-1",
                created_user_bid="creator-topup-no-sub-1",
            )
        )
        dao.db.session.add(_create_wallet("creator-topup-no-sub-1", "25.0000000000"))
        dao.db.session.add(
            _create_bucket(
                "creator-topup-no-sub-1",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                available_credits="25.0000000000",
            )
        )
        dao.db.session.commit()

    with pytest.raises(AppException) as exc_info:
        admit_creator_usage(
            billing_admission_app,
            shifu_bid="shifu-topup-no-sub-1",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.subscriptionInactive"]


def test_admit_creator_usage_allows_manual_grant_without_active_subscription(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-manual-no-sub-1",
                created_user_bid="creator-manual-no-sub-1",
            )
        )
        dao.db.session.add(_create_wallet("creator-manual-no-sub-1", "6.0000000000"))
        dao.db.session.add(
            _create_bucket(
                "creator-manual-no-sub-1",
                category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                available_credits="6.0000000000",
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
            )
        )
        dao.db.session.commit()

    payload = admit_creator_usage(
        billing_admission_app,
        shifu_bid="shifu-manual-no-sub-1",
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
    )

    assert payload["allowed"] is True
    assert payload["creator_bid"] == "creator-manual-no-sub-1"
    assert payload["wallet_available_credits"] == Decimal("6.0000000000")


def test_admit_creator_usage_prefers_manual_grant_balance_when_topup_exists_without_subscription(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-manual-topup-no-sub-1",
                created_user_bid="creator-manual-topup-no-sub-1",
            )
        )
        dao.db.session.add(
            _create_wallet("creator-manual-topup-no-sub-1", "10.0000000000")
        )
        dao.db.session.add(
            _create_bucket(
                "creator-manual-topup-no-sub-1",
                category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                available_credits="4.0000000000",
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
            )
        )
        dao.db.session.add(
            _create_bucket(
                "creator-manual-topup-no-sub-1",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                available_credits="6.0000000000",
            )
        )
        dao.db.session.commit()

    payload = admit_creator_usage(
        billing_admission_app,
        shifu_bid="shifu-manual-topup-no-sub-1",
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
    )

    assert payload["allowed"] is True
    assert payload["wallet_available_credits"] == Decimal("4.0000000000")


def test_admit_creator_usage_rejects_missing_credits(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-empty-1",
                created_user_bid="creator-empty-1",
            )
        )
        dao.db.session.commit()

    with pytest.raises(AppException) as exc_info:
        admit_creator_usage(
            billing_admission_app,
            shifu_bid="shifu-empty-1",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.creditInsufficient"]


def test_admit_creator_usage_skips_credit_checks_when_billing_disabled(
    billing_admission_app: Flask,
    monkeypatch,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-disabled-1",
                created_user_bid="creator-disabled-1",
            )
        )
        dao.db.session.commit()

    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled", lambda: False
    )

    payload = admit_creator_usage(
        billing_admission_app,
        shifu_bid="shifu-disabled-1",
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
    )

    assert payload["allowed"] is True
    assert payload["creator_bid"] == "creator-disabled-1"
    assert payload["wallet_available_credits"] == Decimal("0")
    assert payload["priority_class"] == "standard"


def test_admit_creator_usage_rejects_inactive_subscription_only_balance(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-subscription-1",
                created_user_bid="creator-subscription-1",
            )
        )
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="subscription-1",
                creator_bid="creator-subscription-1",
                status=BILLING_SUBSCRIPTION_STATUS_CANCELED,
            )
        )
        dao.db.session.add(_create_wallet("creator-subscription-1", "50.0000000000"))
        dao.db.session.add(
            _create_bucket(
                "creator-subscription-1",
                category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                available_credits="50.0000000000",
            )
        )
        dao.db.session.commit()

    with pytest.raises(AppException) as exc_info:
        admit_creator_usage(
            billing_admission_app,
            shifu_bid="shifu-subscription-1",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.subscriptionInactive"]


def test_admit_creator_usage_accepts_direct_creator_bid_for_debug(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(_create_wallet("creator-debug-1", "12.5000000000"))
        dao.db.session.add(_create_active_subscription("creator-debug-1"))
        dao.db.session.add(
            _create_bucket(
                "creator-debug-1",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                available_credits="12.5000000000",
            )
        )
        dao.db.session.commit()

    payload = admit_creator_usage(
        billing_admission_app,
        creator_bid="creator-debug-1",
        usage_scene=BILL_USAGE_SCENE_DEBUG,
    )

    assert payload["allowed"] is True
    assert payload["creator_bid"] == "creator-debug-1"
    assert payload["usage_scene"] == BILL_USAGE_SCENE_DEBUG


def test_admit_creator_usage_resolves_priority_class(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(_create_wallet("creator-priority-1", "12.5000000000"))
        dao.db.session.add(_create_active_subscription("creator-priority-1"))
        dao.db.session.add(
            _create_bucket(
                "creator-priority-1",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                available_credits="12.5000000000",
            )
        )
        dao.db.session.add(
            BillingEntitlement(
                entitlement_bid="entitlement-priority-1",
                creator_bid="creator-priority-1",
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid="manual-priority-1",
                priority_class=BILLING_ENTITLEMENT_PRIORITY_CLASS_VIP,
                effective_from=datetime.now() - timedelta(minutes=5),
                effective_to=None,
            )
        )
        dao.db.session.commit()

    payload = admit_creator_usage(
        billing_admission_app,
        creator_bid="creator-priority-1",
        usage_scene=BILL_USAGE_SCENE_DEBUG,
    )

    assert payload["priority_class"] == "vip"


def test_admit_creator_usage_rejects_expired_topup_bucket_even_if_wallet_snapshot_positive(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-expired-topup-1",
                created_user_bid="creator-expired-topup-1",
            )
        )
        dao.db.session.add(_create_wallet("creator-expired-topup-1", "15.0000000000"))
        dao.db.session.add(
            _create_bucket(
                "creator-expired-topup-1",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                available_credits="15.0000000000",
                effective_from=datetime.now() - timedelta(days=7),
                effective_to=datetime.now() - timedelta(minutes=1),
            )
        )
        dao.db.session.commit()

    with pytest.raises(AppException) as exc_info:
        admit_creator_usage(
            billing_admission_app,
            shifu_bid="shifu-expired-topup-1",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.creditInsufficient"]


def test_admit_creator_usage_rejects_future_bucket_before_effective_time(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-future-bucket-1",
                created_user_bid="creator-future-bucket-1",
            )
        )
        dao.db.session.add(_create_wallet("creator-future-bucket-1", "18.0000000000"))
        dao.db.session.add(
            _create_bucket(
                "creator-future-bucket-1",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                available_credits="18.0000000000",
                effective_from=datetime.now() + timedelta(minutes=30),
                effective_to=None,
            )
        )
        dao.db.session.commit()

    with pytest.raises(AppException) as exc_info:
        admit_creator_usage(
            billing_admission_app,
            shifu_bid="shifu-future-bucket-1",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.creditInsufficient"]


def test_repair_subscription_cycle_mismatches_restores_admission_for_current_bucket(
    billing_admission_app: Flask,
) -> None:
    paid_at = datetime(2026, 4, 15, 13, 10, 37)
    cycle_end_at = datetime(2026, 5, 15, 13, 10, 37)
    corrupted_start_at = datetime.now() + timedelta(hours=2)
    corrupted_end_at = corrupted_start_at + timedelta(days=1)

    with billing_admission_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-repair-cycle-1",
                created_user_bid="creator-repair-cycle-1",
            )
        )
        dao.db.session.add(_create_wallet("creator-repair-cycle-1", "5.0000000000"))
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="subscription-repair-cycle-1",
                creator_bid="creator-repair-cycle-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=corrupted_start_at,
                current_period_end_at=corrupted_end_at,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=paid_at,
                updated_at=corrupted_start_at,
            )
        )
        dao.db.session.add(
            BillingOrder(
                bill_order_bid="bill-order-repair-cycle-1",
                creator_bid="creator-repair-cycle-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                product_bid="bill-product-plan-monthly",
                subscription_bid="subscription-repair-cycle-1",
                currency="CNY",
                payable_amount=990,
                paid_amount=990,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_repair_cycle_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=paid_at,
                metadata_json={},
            )
        )
        dao.db.session.add(
            _create_bucket(
                "creator-repair-cycle-1",
                category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                available_credits="5.0000000000",
                effective_from=paid_at,
                effective_to=cycle_end_at,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-order-repair-cycle-1",
            )
        )
        dao.db.session.commit()

    with pytest.raises(AppException) as exc_info:
        admit_creator_usage(
            billing_admission_app,
            shifu_bid="shifu-repair-cycle-1",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.subscriptionInactive"]

    repair_payload = repair_subscription_cycle_mismatches(
        billing_admission_app,
        creator_bid="creator-repair-cycle-1",
    )

    assert repair_payload["status"] == "repaired"
    assert repair_payload["repaired_subscription_count"] == 1
    assert repair_payload["repaired_records"][0]["subscription_bid"] == (
        "subscription-repair-cycle-1"
    )
    assert repair_payload["repaired_records"][0]["current_period_start_at"] == paid_at
    assert (
        repair_payload["repaired_records"][0]["current_period_end_at"] == cycle_end_at
    )

    payload = admit_creator_usage(
        billing_admission_app,
        shifu_bid="shifu-repair-cycle-1",
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
    )

    assert payload["allowed"] is True
    assert payload["creator_bid"] == "creator-repair-cycle-1"

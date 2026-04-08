from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.service.billing.admission import (
    admit_creator_usage,
    reserve_creator_runtime_slot,
)
from flaskr.service.billing.consts import (
    BILLING_ENTITLEMENT_PRIORITY_CLASS_VIP,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.models import (
    BillingEntitlement,
    BillingSubscription,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
)
from flaskr.service.shifu.models import PublishedShifu


@pytest.fixture
def billing_admission_app():
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
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
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
) -> CreditWalletBucket:
    return CreditWalletBucket(
        wallet_bucket_bid=f"bucket-{creator_bid}-{category}",
        wallet_bid=f"wallet-{creator_bid}",
        creator_bid=creator_bid,
        bucket_category=category,
        source_type=0,
        source_bid=f"source-{creator_bid}-{category}",
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


def test_admit_creator_usage_allows_topup_credits_without_subscription(
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


def test_admit_creator_usage_resolves_priority_class_and_max_concurrency(
    billing_admission_app: Flask,
) -> None:
    with billing_admission_app.app_context():
        dao.db.session.add(_create_wallet("creator-priority-1", "12.5000000000"))
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
                max_concurrency=6,
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
    assert payload["max_concurrency"] == 6


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


def test_reserve_creator_runtime_slot_enforces_entitlement_concurrency(
    billing_admission_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.admission.cache_provider",
        InMemoryCacheProvider(),
    )
    with billing_admission_app.app_context():
        dao.db.session.add(_create_wallet("creator-runtime-1", "8.0000000000"))
        dao.db.session.add(
            _create_bucket(
                "creator-runtime-1",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                available_credits="8.0000000000",
            )
        )
        dao.db.session.add(
            BillingEntitlement(
                entitlement_bid="entitlement-runtime-1",
                creator_bid="creator-runtime-1",
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid="manual-runtime-1",
                max_concurrency=1,
                effective_from=datetime.now() - timedelta(minutes=5),
                effective_to=None,
            )
        )
        dao.db.session.commit()

    admission_payload = admit_creator_usage(
        billing_admission_app,
        creator_bid="creator-runtime-1",
        usage_scene=BILL_USAGE_SCENE_DEBUG,
    )
    runtime_lease = reserve_creator_runtime_slot(
        billing_admission_app,
        admission_payload=admission_payload,
    )

    assert runtime_lease.active_runtime_count == 1

    with pytest.raises(AppException) as exc_info:
        reserve_creator_runtime_slot(
            billing_admission_app,
            admission_payload=admission_payload,
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.concurrencyExceeded"]

    runtime_lease.release()

    next_lease = reserve_creator_runtime_slot(
        billing_admission_app,
        admission_payload=admission_payload,
    )
    assert next_lease.active_runtime_count == 1
    next_lease.release()

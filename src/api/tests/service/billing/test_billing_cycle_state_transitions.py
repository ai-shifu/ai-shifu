from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing import subscriptions as subscriptions_mod
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_INTERVAL_MONTH,
    BILLING_MODE_RECURRING,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.cycle_state_transitions import (
    apply_paid_subscription_cycle_state,
    realign_active_topup_bucket_effective_to,
    resolve_effective_subscription_cycle_window,
    subscription_has_effective_cycle,
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


_UNSET = object()


def _build_app() -> Flask:
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
    return app


def _renewal_order(
    *,
    bill_order_bid: str = "order-renewal-activation-boundary",
    subscription_bid: str = "subscription-renewal-activation-boundary",
    creator_bid: str = "creator-renewal-activation-boundary",
    metadata_json: dict | None = None,
    payment_provider: str = "pingxx",
    paid_at: datetime | None | object = _UNSET,
    order_type: int = BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
) -> BillingOrder:
    return BillingOrder(
        bill_order_bid=bill_order_bid,
        creator_bid=creator_bid,
        order_type=order_type,
        product_bid="bill-product-renewal-boundary",
        subscription_bid=subscription_bid,
        currency="CNY",
        payable_amount=0,
        paid_amount=0,
        payment_provider=payment_provider,
        channel="manual",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=(datetime(2026, 4, 10, 0, 0, 0) if paid_at is _UNSET else paid_at),
        metadata_json=metadata_json or {},
    )


def _renewal_product() -> BillingProduct:
    return BillingProduct(
        product_bid="bill-product-renewal-boundary",
        product_code="renewal-boundary",
        product_type=BILLING_PRODUCT_TYPE_PLAN,
        billing_mode=BILLING_MODE_RECURRING,
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
        display_name_i18n_key="billing.product.renewal_boundary",
        description_i18n_key="billing.product.renewal_boundary.description",
        currency="CNY",
        price_amount=0,
        credit_amount=Decimal("1000.0000000000"),
        allocation_interval=ALLOCATION_INTERVAL_PER_CYCLE,
        auto_renew_enabled=1,
        status=BILLING_PRODUCT_STATUS_ACTIVE,
    )


def _add_reserved_renewal_activation_state(
    *,
    product: BillingProduct,
    subscription: BillingSubscription,
    order: BillingOrder,
    current_cycle_start: datetime,
    current_cycle_end: datetime,
    next_cycle_end: datetime,
) -> tuple[CreditWallet, CreditWalletBucket, CreditLedgerEntry]:
    wallet = CreditWallet(
        wallet_bid=f"wallet-{order.creator_bid}",
        creator_bid=order.creator_bid,
        available_credits=Decimal("3.0000000000"),
        reserved_credits=Decimal("1000.0000000000"),
        lifetime_granted_credits=Decimal("1003.0000000000"),
        lifetime_consumed_credits=Decimal("0"),
        last_settled_usage_id=0,
        version=0,
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=f"bucket-{order.bill_order_bid}",
        wallet_bid=wallet.wallet_bid,
        creator_bid=order.creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid="order-current-cycle",
        priority=20,
        original_credits=Decimal("1003.0000000000"),
        available_credits=Decimal("3.0000000000"),
        reserved_credits=Decimal("1000.0000000000"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=current_cycle_start,
        effective_to=current_cycle_end,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json={"bill_order_bid": "order-current-cycle"},
        created_at=current_cycle_start,
        updated_at=current_cycle_start,
    )
    grant_entry = CreditLedgerEntry(
        ledger_bid=f"ledger-{order.bill_order_bid}",
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid=order.bill_order_bid,
        idempotency_key=f"grant:{order.bill_order_bid}",
        amount=Decimal("1000.0000000000"),
        balance_after=Decimal("3.0000000000"),
        expires_at=next_cycle_end,
        consumable_from=current_cycle_end,
        metadata_json={
            "bill_order_bid": order.bill_order_bid,
            "subscription_bid": subscription.subscription_bid,
            "product_bid": product.product_bid,
            "payment_provider": order.payment_provider,
            "grant_reason": "subscription_renewal",
            "bucket_credit_state": "reserved",
            "reserved_until": current_cycle_end.isoformat(),
        },
        created_at=current_cycle_end - timedelta(days=5),
        updated_at=current_cycle_end - timedelta(days=5),
    )
    dao.db.session.add_all([wallet, bucket, grant_entry])
    return wallet, bucket, grant_entry


def test_subscription_has_effective_cycle_uses_current_period_window() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-state",
        creator_bid="creator-cycle-state",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=current_at - timedelta(days=1),
        current_period_end_at=current_at + timedelta(days=1),
    )

    assert subscription_has_effective_cycle(subscription, as_of=current_at) is True

    subscription.current_period_end_at = current_at

    assert subscription_has_effective_cycle(subscription, as_of=current_at) is False
    assert subscription_has_effective_cycle(None, as_of=current_at) is False


def test_resolve_effective_subscription_cycle_window_returns_current_window() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    cycle_start = current_at
    cycle_end = current_at + timedelta(days=30)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-window",
        creator_bid="creator-cycle-window",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=cycle_start,
        current_period_end_at=cycle_end,
    )

    window = resolve_effective_subscription_cycle_window(
        subscription,
        as_of=current_at,
    )

    assert window is not None
    assert window.start_at == cycle_start
    assert window.end_at == cycle_end


def test_resolve_effective_subscription_cycle_window_rejects_invalid_windows() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-window-invalid",
        creator_bid="creator-cycle-window-invalid",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=current_at - timedelta(days=1),
        current_period_end_at=current_at + timedelta(days=1),
    )

    subscription.current_period_start_at = None
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at - timedelta(days=1)
    subscription.current_period_end_at = None
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at
    subscription.current_period_end_at = current_at
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at + timedelta(days=1)
    subscription.current_period_end_at = current_at
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at + timedelta(seconds=1)
    subscription.current_period_end_at = current_at + timedelta(days=1)
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at - timedelta(days=1)
    subscription.current_period_end_at = current_at
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )


def test_pingxx_renewal_activation_defers_before_cycle_start() -> None:
    paid_at = datetime(2026, 4, 10, 0, 0, 0)
    renewal_cycle_start = datetime(2026, 5, 1, 0, 0, 0)
    order = _renewal_order(
        paid_at=paid_at,
        metadata_json={"renewal_cycle_start_at": renewal_cycle_start.isoformat()},
    )

    assert subscriptions_mod._should_defer_pingxx_renewal_activation(order) is True


@pytest.mark.parametrize(
    "order",
    [
        _renewal_order(
            metadata_json={
                "applied_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
                "renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
            },
        ),
        _renewal_order(
            payment_provider="stripe",
            metadata_json={
                "renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
            },
        ),
        _renewal_order(
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            metadata_json={
                "renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
            },
        ),
        _renewal_order(
            paid_at=None,
            metadata_json={
                "renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
            },
        ),
    ],
    ids=("applied", "non_pingxx", "non_renewal", "unpaid"),
)
def test_pingxx_renewal_activation_does_not_defer_when_guard_fails(
    order: BillingOrder,
) -> None:
    assert subscriptions_mod._should_defer_pingxx_renewal_activation(order) is False


@pytest.mark.parametrize(
    ("metadata_json", "payment_provider"),
    [
        (
            {"renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat()},
            "pingxx",
        ),
        (
            {
                "checkout_type": "subscription_preorder",
                "preorder_state": "pending_effective",
            },
            "pingxx",
        ),
        (
            {
                "checkout_type": "referral_invitation_reward",
                "referral_invitation_reward": True,
            },
            "manual",
        ),
    ],
    ids=("pingxx", "preorder", "referral"),
)
def test_subscription_renewal_activation_defers_future_boundary(
    monkeypatch: pytest.MonkeyPatch,
    metadata_json: dict,
    payment_provider: str,
) -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    effective_from = datetime(2026, 5, 1, 0, 0, 0)
    monkeypatch.setattr(subscriptions_mod, "now_utc", lambda: current_at)
    order = _renewal_order(
        paid_at=current_at,
        payment_provider=payment_provider,
        metadata_json=metadata_json,
    )

    assert (
        subscriptions_mod._should_defer_subscription_renewal_activation(
            order,
            effective_from=effective_from,
        )
        is True
    )


@pytest.mark.parametrize(
    ("metadata_json", "effective_from"),
    [
        (
            {
                "checkout_type": "referral_invitation_reward",
                "referral_invitation_reward": True,
            },
            datetime(2026, 4, 10, 0, 0, 0),
        ),
        (
            {
                "applied_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
                "checkout_type": "referral_invitation_reward",
                "referral_invitation_reward": True,
            },
            datetime(2026, 5, 1, 0, 0, 0),
        ),
    ],
    ids=("effective_now", "applied_cycle"),
)
def test_subscription_renewal_activation_does_not_defer_when_guard_fails(
    monkeypatch: pytest.MonkeyPatch,
    metadata_json: dict,
    effective_from: datetime,
) -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    monkeypatch.setattr(subscriptions_mod, "now_utc", lambda: current_at)
    order = _renewal_order(
        payment_provider="manual",
        metadata_json=metadata_json,
    )

    assert (
        subscriptions_mod._should_defer_subscription_renewal_activation(
            order,
            effective_from=effective_from,
        )
        is False
    )


def test_force_activation_advances_future_deferred_renewal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app()
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
    current_cycle_end = datetime(2026, 5, 1, 0, 0, 0)
    next_cycle_end = datetime(2026, 6, 1, 0, 0, 0)
    monkeypatch.setattr(subscriptions_mod, "now_utc", lambda: current_at)

    with app.app_context():
        dao.db.create_all()
        product = BillingProduct(
            product_bid="bill-product-renewal-boundary",
            product_code="renewal-boundary",
            product_type=BILLING_PRODUCT_TYPE_PLAN,
            billing_mode=BILLING_MODE_RECURRING,
            billing_interval=BILLING_INTERVAL_MONTH,
            billing_interval_count=1,
            display_name_i18n_key="billing.product.renewal_boundary",
            description_i18n_key="billing.product.renewal_boundary.description",
            currency="CNY",
            price_amount=0,
            credit_amount=Decimal("1000.0000000000"),
            allocation_interval=ALLOCATION_INTERVAL_PER_CYCLE,
            auto_renew_enabled=1,
            status=BILLING_PRODUCT_STATUS_ACTIVE,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-activation-boundary",
            creator_bid="creator-renewal-activation-boundary",
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
        )
        forced_subscription = BillingSubscription(
            subscription_bid="subscription-renewal-activation-force",
            creator_bid="creator-renewal-activation-boundary",
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
        )
        order_metadata = {
            "checkout_type": "referral_invitation_reward",
            "referral_invitation_reward": True,
            "renewal_cycle_start_at": current_cycle_end.isoformat(),
            "renewal_cycle_end_at": next_cycle_end.isoformat(),
        }
        deferred_order = _renewal_order(
            bill_order_bid="order-renewal-activation-defer",
            payment_provider="manual",
            metadata_json=order_metadata.copy(),
        )
        forced_order = _renewal_order(
            bill_order_bid="order-renewal-activation-force",
            subscription_bid=forced_subscription.subscription_bid,
            payment_provider="manual",
            metadata_json=order_metadata.copy(),
        )
        dao.db.session.add_all(
            [product, subscription, forced_subscription, deferred_order, forced_order]
        )
        dao.db.session.commit()

        deferred = subscriptions_mod._activate_subscription_for_paid_order(
            app,
            deferred_order,
            force=False,
        )
        activated = subscriptions_mod._activate_subscription_for_paid_order(
            app,
            forced_order,
            force=True,
        )
        dao.db.session.flush()

    assert deferred is False
    assert activated is True
    assert subscription.current_period_start_at == current_cycle_start
    assert subscription.current_period_end_at == current_cycle_end
    assert forced_subscription.current_period_start_at == current_cycle_end
    assert forced_subscription.current_period_end_at == next_cycle_end


def test_pingxx_renewal_activation_applies_at_exact_cycle_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app()
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
    current_cycle_end = datetime(2026, 5, 1, 0, 0, 0)
    next_cycle_end = datetime(2026, 6, 1, 0, 0, 0)
    monkeypatch.setattr(subscriptions_mod, "now_utc", lambda: current_at)

    with app.app_context():
        dao.db.create_all()
        product = BillingProduct(
            product_bid="bill-product-renewal-boundary",
            product_code="renewal-boundary",
            product_type=BILLING_PRODUCT_TYPE_PLAN,
            billing_mode=BILLING_MODE_RECURRING,
            billing_interval=BILLING_INTERVAL_MONTH,
            billing_interval_count=1,
            display_name_i18n_key="billing.product.renewal_boundary",
            description_i18n_key="billing.product.renewal_boundary.description",
            currency="CNY",
            price_amount=0,
            credit_amount=Decimal("1000.0000000000"),
            allocation_interval=ALLOCATION_INTERVAL_PER_CYCLE,
            auto_renew_enabled=1,
            status=BILLING_PRODUCT_STATUS_ACTIVE,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-activation-boundary",
            creator_bid="creator-renewal-activation-boundary",
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
        )
        order = _renewal_order(
            paid_at=current_cycle_end,
            metadata_json={
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        dao.db.session.add_all([product, subscription, order])
        dao.db.session.commit()

        activated = subscriptions_mod._activate_subscription_for_paid_order(
            app,
            order,
            force=False,
        )
        dao.db.session.flush()

    assert activated is True
    assert subscription.current_period_start_at == current_cycle_end
    assert subscription.current_period_end_at == next_cycle_end


def test_force_activation_does_not_bypass_preorder_state_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app()
    current_at = datetime(2026, 5, 1, 0, 0, 0)
    current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
    current_cycle_end = datetime(2026, 5, 1, 0, 0, 0)
    next_cycle_end = datetime(2026, 6, 1, 0, 0, 0)
    monkeypatch.setattr(subscriptions_mod, "now_utc", lambda: current_at)

    with app.app_context():
        dao.db.create_all()
        product = _renewal_product()
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-activation-boundary",
            creator_bid="creator-renewal-activation-boundary",
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
        )
        order = _renewal_order(
            metadata_json={
                "checkout_type": "subscription_preorder",
                "preorder_state": "effective_applied",
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        wallet, bucket, grant_entry = _add_reserved_renewal_activation_state(
            product=product,
            subscription=subscription,
            order=order,
            current_cycle_start=current_cycle_start,
            current_cycle_end=current_cycle_end,
            next_cycle_end=next_cycle_end,
        )
        dao.db.session.add_all([product, subscription, order])
        dao.db.session.commit()

        activated = subscriptions_mod._activate_subscription_for_paid_order(
            app,
            order,
            force=True,
        )
        dao.db.session.flush()

        assert activated is False
        assert subscription.current_period_start_at == current_cycle_start
        assert subscription.current_period_end_at == current_cycle_end
        assert order.metadata_json["preorder_state"] == "effective_applied"
        assert wallet.available_credits == Decimal("3.0000000000")
        assert wallet.reserved_credits == Decimal("1000.0000000000")
        assert bucket.available_credits == Decimal("3.0000000000")
        assert bucket.reserved_credits == Decimal("1000.0000000000")
        assert bucket.expired_credits == Decimal("0E-10")
        assert grant_entry.metadata_json["bucket_credit_state"] == "reserved"
        assert (
            CreditLedgerEntry.query.filter_by(
                creator_bid=order.creator_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            ).count()
            == 0
        )


def test_force_activation_is_idempotent_for_reserved_renewal_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app()
    current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
    current_cycle_end = datetime(2026, 5, 1, 0, 0, 0)
    next_cycle_end = datetime(2026, 6, 1, 0, 0, 0)
    monkeypatch.setattr(subscriptions_mod, "now_utc", lambda: current_cycle_end)

    with app.app_context():
        dao.db.create_all()
        product = _renewal_product()
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-activation-boundary",
            creator_bid="creator-renewal-activation-boundary",
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
        )
        order = _renewal_order(
            bill_order_bid="order-renewal-activation-idempotent",
            metadata_json={
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        wallet, bucket, grant_entry = _add_reserved_renewal_activation_state(
            product=product,
            subscription=subscription,
            order=order,
            current_cycle_start=current_cycle_start,
            current_cycle_end=current_cycle_end,
            next_cycle_end=next_cycle_end,
        )
        dao.db.session.add_all([product, subscription, order])
        dao.db.session.commit()

        first_activated = subscriptions_mod._activate_subscription_for_paid_order(
            app,
            order,
            force=True,
        )
        dao.db.session.commit()

    assert first_activated is True

    with app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="subscription-renewal-activation-boundary"
        ).one()
        order = BillingOrder.query.filter_by(
            bill_order_bid="order-renewal-activation-idempotent"
        ).one()
        wallet = CreditWallet.query.filter_by(
            wallet_bid=f"wallet-{order.creator_bid}"
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid=f"bucket-{order.bill_order_bid}"
        ).one()
        grant_entry = CreditLedgerEntry.query.filter_by(
            idempotency_key=f"grant:{order.bill_order_bid}"
        ).one()
        expire_entries = CreditLedgerEntry.query.filter_by(
            creator_bid=order.creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            idempotency_key=f"cycle_expire:{order.bill_order_bid}",
        ).all()
        renewal_event_count = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
        ).count()

        assert subscription.current_period_start_at == current_cycle_end
        assert subscription.current_period_end_at == next_cycle_end
        assert bucket.source_bid == order.bill_order_bid
        assert bucket.available_credits == Decimal("1000.0000000000")
        assert bucket.reserved_credits == Decimal("0E-10")
        assert bucket.expired_credits == Decimal("3.0000000000")
        assert wallet.available_credits == Decimal("1000.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert grant_entry.metadata_json["bucket_credit_state"] == "available"
        assert grant_entry.consumable_from == current_cycle_end
        assert grant_entry.expires_at == next_cycle_end
        assert len(expire_entries) == 1
        assert expire_entries[0].amount == Decimal("-3.0000000000")
        first_snapshot = {
            "subscription_start": subscription.current_period_start_at,
            "subscription_end": subscription.current_period_end_at,
            "wallet_available": wallet.available_credits,
            "wallet_reserved": wallet.reserved_credits,
            "bucket_source": bucket.source_bid,
            "bucket_available": bucket.available_credits,
            "bucket_reserved": bucket.reserved_credits,
            "bucket_expired": bucket.expired_credits,
            "grant_state": grant_entry.metadata_json["bucket_credit_state"],
            "grant_consumable_from": grant_entry.consumable_from,
            "grant_expires_at": grant_entry.expires_at,
            "expire_count": len(expire_entries),
            "renewal_event_count": renewal_event_count,
        }

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="order-renewal-activation-idempotent"
        ).one()
        second_activated = subscriptions_mod._activate_subscription_for_paid_order(
            app,
            order,
            force=True,
        )
        dao.db.session.commit()

    assert second_activated is True

    with app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="subscription-renewal-activation-boundary"
        ).one()
        order = BillingOrder.query.filter_by(
            bill_order_bid="order-renewal-activation-idempotent"
        ).one()
        wallet = CreditWallet.query.filter_by(
            wallet_bid=f"wallet-{order.creator_bid}"
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid=f"bucket-{order.bill_order_bid}"
        ).one()
        grant_entry = CreditLedgerEntry.query.filter_by(
            idempotency_key=f"grant:{order.bill_order_bid}"
        ).one()
        expire_entries = CreditLedgerEntry.query.filter_by(
            creator_bid=order.creator_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            idempotency_key=f"cycle_expire:{order.bill_order_bid}",
        ).all()
        renewal_event_count = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
        ).count()

        assert (
            subscription.current_period_start_at == first_snapshot["subscription_start"]
        )
        assert subscription.current_period_end_at == first_snapshot["subscription_end"]
        assert wallet.available_credits == first_snapshot["wallet_available"]
        assert wallet.reserved_credits == first_snapshot["wallet_reserved"]
        assert bucket.source_bid == first_snapshot["bucket_source"]
        assert bucket.available_credits == first_snapshot["bucket_available"]
        assert bucket.reserved_credits == first_snapshot["bucket_reserved"]
        assert bucket.expired_credits == first_snapshot["bucket_expired"]
        assert (
            grant_entry.metadata_json["bucket_credit_state"]
            == first_snapshot["grant_state"]
        )
        assert grant_entry.consumable_from == first_snapshot["grant_consumable_from"]
        assert grant_entry.expires_at == first_snapshot["grant_expires_at"]
        assert len(expire_entries) == first_snapshot["expire_count"]
        assert renewal_event_count == first_snapshot["renewal_event_count"]


@pytest.mark.parametrize(
    (
        "case_id",
        "current_period_start_at",
        "current_period_end_at",
        "initial_bucket_start",
        "initial_bucket_end",
        "expected_changed",
        "expected_bucket_start",
        "expected_bucket_end",
    ),
    [
        (
            "nostart",
            None,
            datetime(2026, 5, 10, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
        ),
        (
            "noend",
            datetime(2026, 4, 1, 0, 0, 0),
            None,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "zero",
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "rev",
            datetime(2026, 4, 11, 0, 0, 0),
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "expired",
            datetime(2026, 4, 1, 0, 0, 0),
            datetime(2026, 4, 9, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "future",
            datetime(2026, 4, 11, 0, 0, 0),
            datetime(2026, 5, 11, 0, 0, 0),
            datetime(2026, 4, 12, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
            False,
            datetime(2026, 4, 12, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
        ),
        (
            "endat",
            datetime(2026, 4, 1, 0, 0, 0),
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "startat",
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 5, 10, 0, 0, 0),
            datetime(2026, 4, 11, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
            True,
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 5, 10, 0, 0, 0),
        ),
    ],
    ids=(
        "missing_start",
        "missing_end",
        "zero_length",
        "reversed",
        "expired",
        "future",
        "end_at_as_of",
        "start_at_as_of",
    ),
)
def test_repair_paid_reserved_grant_handles_cycle_window_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    current_period_start_at: datetime | None,
    current_period_end_at: datetime | None,
    initial_bucket_start: datetime,
    initial_bucket_end: datetime,
    expected_changed: bool,
    expected_bucket_start: datetime,
    expected_bucket_end: datetime,
) -> None:
    app = _build_app()
    repair_at = datetime(2026, 4, 10, 0, 0, 0)
    creator_bid = "creator-invalid-cycle-caller"
    subscription_bid = "subscription-invalid-cycle-caller"
    order_bid = f"order-inv-cycle-{case_id}"

    monkeypatch.setattr(subscriptions_mod, "now_utc", lambda: repair_at)

    with app.app_context():
        dao.db.create_all()
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-invalid-cycle-caller",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=current_period_start_at,
            current_period_end_at=current_period_end_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=repair_at - timedelta(days=1),
            metadata_json={},
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid=f"bucket-inv-cycle-{case_id}",
            wallet_bid="wallet-invalid-cycle-caller",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=initial_bucket_start,
            effective_to=initial_bucket_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        ledger = CreditLedgerEntry(
            ledger_bid=f"ledger-inv-cycle-{case_id}",
            creator_bid=creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=datetime(2026, 6, 1, 0, 0, 0),
            consumable_from=repair_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all([subscription, order, bucket, ledger])
        dao.db.session.commit()

        changed = subscriptions_mod._repair_existing_paid_order_grant_bucket(
            app,
            order=order,
            grant_entry=ledger,
        )
        dao.db.session.refresh(bucket)

    assert changed is expected_changed
    assert bucket.effective_from == expected_bucket_start
    assert bucket.effective_to == expected_bucket_end


def test_realign_active_topup_bucket_effective_to_updates_bucket_and_grant_ledgers() -> (
    None
):
    app = _build_app()
    creator_bid = "creator-cycle-state-topup"
    cycle_start = datetime(2026, 4, 10, 0, 0, 0)
    cycle_end = datetime(2026, 5, 10, 0, 0, 0)
    old_topup_end = datetime(2026, 4, 9, 0, 0, 0)

    with app.app_context():
        dao.db.create_all()
        topup_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-cycle-state-topup",
            wallet_bid="wallet-cycle-state-topup",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-cycle-state-topup",
            priority=30,
            original_credits=Decimal("20.0000000000"),
            available_credits=Decimal("20.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=old_topup_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        future_topup_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-cycle-state-future-topup",
            wallet_bid="wallet-cycle-state-topup",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-cycle-state-future-topup",
            priority=30,
            original_credits=Decimal("5.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=cycle_start + timedelta(days=1),
            effective_to=old_topup_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        subscription_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-cycle-state-subscription",
            wallet_bid="wallet-cycle-state-topup",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-cycle-state-subscription",
            priority=20,
            original_credits=Decimal("50.0000000000"),
            available_credits=Decimal("50.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=old_topup_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        topup_ledger = CreditLedgerEntry(
            ledger_bid="ledger-cycle-state-topup",
            creator_bid=creator_bid,
            wallet_bid="wallet-cycle-state-topup",
            wallet_bucket_bid=topup_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=topup_bucket.source_bid,
            idempotency_key="grant:order-cycle-state-topup",
            amount=Decimal("20.0000000000"),
            balance_after=Decimal("20.0000000000"),
            expires_at=old_topup_end,
            consumable_from=topup_bucket.effective_from,
        )
        future_topup_ledger = CreditLedgerEntry(
            ledger_bid="ledger-cycle-state-future-topup",
            creator_bid=creator_bid,
            wallet_bid="wallet-cycle-state-topup",
            wallet_bucket_bid=future_topup_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=future_topup_bucket.source_bid,
            idempotency_key="grant:order-cycle-state-future-topup",
            amount=Decimal("5.0000000000"),
            balance_after=Decimal("25.0000000000"),
            expires_at=old_topup_end,
            consumable_from=future_topup_bucket.effective_from,
        )
        dao.db.session.add_all(
            [
                topup_bucket,
                future_topup_bucket,
                subscription_bucket,
                topup_ledger,
                future_topup_ledger,
            ]
        )
        dao.db.session.commit()

        realign_active_topup_bucket_effective_to(
            creator_bid=creator_bid,
            effective_from=cycle_start,
            effective_to=cycle_end,
        )
        dao.db.session.flush()

        assert topup_bucket.effective_to == cycle_end
        assert topup_ledger.expires_at == cycle_end
        assert future_topup_bucket.effective_to == old_topup_end
        assert future_topup_ledger.expires_at == old_topup_end
        assert subscription_bucket.effective_to == old_topup_end


def test_apply_paid_subscription_cycle_state_advances_renewal_and_realigns_topup() -> (
    None
):
    app = _build_app()
    creator_bid = "creator-cycle-state-renewal"
    cycle_start = datetime(2026, 6, 1, 0, 0, 0)
    cycle_end = datetime(2026, 7, 1, 0, 0, 0)
    old_topup_end = datetime(2026, 5, 31, 0, 0, 0)

    with app.app_context():
        dao.db.create_all()
        subscription = BillingSubscription(
            subscription_bid="subscription-cycle-state-renewal",
            creator_bid=creator_bid,
            product_bid="bill-product-old",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            cancel_at_period_end=1,
            next_product_bid="bill-product-downgrade",
            current_period_start_at=datetime(2026, 5, 1, 0, 0, 0),
            current_period_end_at=cycle_start,
        )
        topup_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-cycle-state-renewal-topup",
            wallet_bid="wallet-cycle-state-renewal",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-cycle-state-renewal-topup",
            priority=30,
            original_credits=Decimal("20.0000000000"),
            available_credits=Decimal("20.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 5, 1, 0, 0, 0),
            effective_to=old_topup_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        topup_ledger = CreditLedgerEntry(
            ledger_bid="ledger-cycle-state-renewal-topup",
            creator_bid=creator_bid,
            wallet_bid="wallet-cycle-state-renewal",
            wallet_bucket_bid=topup_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=topup_bucket.source_bid,
            idempotency_key="grant:order-cycle-state-renewal-topup",
            amount=Decimal("20.0000000000"),
            balance_after=Decimal("20.0000000000"),
            expires_at=old_topup_end,
            consumable_from=topup_bucket.effective_from,
        )
        dao.db.session.add_all([subscription, topup_bucket, topup_ledger])
        dao.db.session.commit()

        apply_paid_subscription_cycle_state(
            subscription,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            order_product_bid="bill-product-renewal-order",
            effective_from=cycle_start,
            effective_to=cycle_end,
        )
        dao.db.session.flush()

        assert subscription.product_bid == "bill-product-downgrade"
        assert subscription.next_product_bid == ""
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        assert subscription.current_period_start_at == cycle_start
        assert subscription.current_period_end_at == cycle_end
        assert subscription.last_renewed_at == cycle_start
        assert topup_bucket.effective_to == cycle_end
        assert topup_ledger.expires_at == cycle_end

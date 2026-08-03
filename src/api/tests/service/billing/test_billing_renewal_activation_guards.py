from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

import flaskr.dao as dao
from flaskr.service.billing import subscriptions as subscriptions_mod
from flaskr.service.billing.consts import (
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from tests.service.billing.cycle_state_test_helpers import (
    _add_reserved_renewal_activation_state,
    _build_app,
    _renewal_order,
    _renewal_product,
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
    "order_kwargs",
    [
        {
            "metadata_json": {
                "applied_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
                "renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
            },
        },
        {
            "payment_provider": "stripe",
            "metadata_json": {
                "renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
            },
        },
        {
            "order_type": BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            "metadata_json": {
                "renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
            },
        },
        {
            "paid_at": None,
            "metadata_json": {
                "renewal_cycle_start_at": datetime(2026, 5, 1, 0, 0, 0).isoformat(),
            },
        },
    ],
    ids=("applied", "non_pingxx", "non_renewal", "unpaid"),
)
def test_pingxx_renewal_activation_does_not_defer_when_guard_fails(
    order_kwargs: dict,
) -> None:
    order = _renewal_order(**order_kwargs)

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
        product = _renewal_product()
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

"""Verify subscription repair evidence, renewal idempotency, and grant rollback."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import subscriptions
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppError
from flaskr.util.datetime import now_utc

from tests.service.billing.test_checkout_state_transition_contracts import _seed

if TYPE_CHECKING:
    from flask import Flask


def _grant(app: Flask, order: BillingOrder) -> bool:
    with unit_of_work():
        return subscriptions.grant_paid_order_credits(app, order)


@pytest.mark.parametrize("operation", ["cancel", "resume"])
@pytest.mark.parametrize(
    "gate", ["manual", "status", "owner", "provider-error", "late-error"]
)
def test_subscription_lifecycle_rejects_invalid_actions_and_preserves_state_on_failure(
    operation: str, gate: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock(
        cancel_subscription=Mock(
            return_value=SimpleNamespace(raw_response={"cancel_at_period_end": True})
        ),
        resume_subscription=Mock(
            return_value=SimpleNamespace(raw_response={"cancel_at_period_end": False})
        ),
    )
    monkeypatch.setattr(
        subscriptions, "get_payment_provider", Mock(return_value=provider)
    )
    callback = (
        subscriptions.cancel_billing_subscription
        if operation == "cancel"
        else subscriptions.resume_billing_subscription
    )
    with app.app_context():
        _, _, plan = _seed(
            subscription=True, provider="manual" if gate == "manual" else "stripe"
        )
        plan.status = (
            BILLING_SUBSCRIPTION_STATUS_CANCELED
            if gate == "status"
            else BILLING_SUBSCRIPTION_STATUS_ACTIVE
            if operation == "cancel"
            else BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        )
        plan.cancel_at_period_end = int(operation == "resume")
        plan.provider_subscription_id = "sub_test"
        plan.metadata_json = {"preserved": True}
        original_status = plan.status
        db.session.commit()
        if gate == "provider-error":
            getattr(provider, f"{operation}_subscription").side_effect = RuntimeError(
                "provider unavailable"
            )
        if gate == "late-error":
            monkeypatch.setattr(
                subscriptions,
                "_serialize_subscription",
                Mock(side_effect=RuntimeError("response serialization failed")),
            )
        with pytest.raises(
            RuntimeError if gate in {"provider-error", "late-error"} else AppError
        ):
            callback(
                app,
                "other" if gate == "owner" else plan.creator_bid,
                {"subscription_bid": plan.subscription_bid},
            )
        db.session.expire_all()
        assert plan.status == original_status
        assert plan.cancel_at_period_end == int(operation == "resume")
        assert plan.metadata_json == {"preserved": True}
        if gate in {"manual", "status", "owner"}:
            provider.cancel_subscription.assert_not_called()
            provider.resume_subscription.assert_not_called()


@pytest.mark.parametrize(
    "gate",
    [
        "missing-boundary",
        "unsupported-provider",
        "missing-reference",
        "missing-product",
        "missing-cycle",
    ],
)
def test_renewal_does_not_create_unchargeable_orders(gate: str, app: Flask) -> None:
    with app.app_context():
        order, product, plan = _seed(subscription=True)
        plan.provider_subscription_id = "sub_test"
        if gate == "missing-boundary":
            plan.current_period_end_at = None
        elif gate == "unsupported-provider":
            plan.billing_provider = "manual"
        elif gate == "missing-reference":
            plan.provider_subscription_id = ""
        elif gate == "missing-product":
            product.deleted = 1
        else:
            product.billing_interval_count = 0
        db.session.commit()
        with unit_of_work():
            assert subscriptions.ensure_subscription_renewal_order(app, plan) is None
        assert BillingOrder.query.filter_by(creator_bid=order.creator_bid).count() == 1


@pytest.mark.parametrize("provider", ["stripe", "pingxx"])
def test_renewal_reuses_same_cycle_order_and_refreshes_only_current_contract(
    provider: str, app: Flask
) -> None:
    with app.app_context():
        _, product, plan = _seed(subscription=True, provider=provider)
        plan.provider_subscription_id = "sub_current" if provider == "stripe" else ""
        db.session.commit()
        with unit_of_work():
            first = subscriptions.ensure_subscription_renewal_order(
                app, plan, renewal_event_bid="event-initial"
            )
        first_bid = first.bill_order_bid
        first.channel = ""
        first.currency = "OLD"
        first.payable_amount = 1
        first.creator_bid = "outdated"
        if provider == "stripe":
            first.provider_reference_id = "sub_old"
        product.price_amount = 4567
        db.session.commit()
        with unit_of_work():
            second = subscriptions.ensure_subscription_renewal_order(
                app, plan, renewal_event_bid="event-retry"
            )
        assert second.bill_order_bid == first_bid
        db.session.expire_all()
        assert second.currency == product.currency
        assert second.payable_amount == 4567
        assert second.creator_bid == plan.creator_bid
        assert second.channel == (
            "subscription" if provider == "stripe" else "alipay_qr"
        )
        assert second.metadata_json["renewal_event_bid"] == "event-retry"
        assert (
            BillingOrder.query.filter_by(
                subscription_bid=plan.subscription_bid,
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            ).count()
            == 1
        )
        if provider == "stripe":
            assert second.provider_reference_id == "sub_current"


@pytest.mark.parametrize("gate", ["missing-product", "zero-credit"])
def test_credit_grant_requires_existing_product_with_positive_credits(
    gate: str, app: Flask
) -> None:
    with app.app_context():
        order, product, _ = _seed(status=BILLING_ORDER_STATUS_PAID)
        if gate == "missing-product":
            product.deleted = 1
        else:
            product.credit_amount = 0
        db.session.commit()
        assert _grant(app, order) is False
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid=order.creator_bid).count()
            == 0
        )


@pytest.mark.parametrize("reserved", [False, True])
def test_campaign_bonus_grant_preserves_reservation_and_cannot_duplicate_on_replay(
    reserved: bool, app: Flask
) -> None:
    with app.app_context():
        order, _, plan = _seed(
            subscription=reserved,
            status=BILLING_ORDER_STATUS_PAID,
            provider="pingxx" if reserved else "stripe",
        )
        order.campaign_bid = uuid4().hex
        order.campaign_bonus_credit_amount = Decimal("2.5")
        order.paid_at = now_utc()
        if reserved:
            order.order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
            order.metadata_json = {
                "renewal_cycle_start_at": plan.current_period_end_at.isoformat(),
                "renewal_cycle_end_at": (
                    plan.current_period_end_at + timedelta(days=30)
                ).isoformat(),
            }
        db.session.commit()
        assert _grant(app, order) is True
        assert _grant(app, order) is False
        db.session.expire_all()
        bonus = CreditWalletBucket.query.filter_by(
            creator_bid=order.creator_bid, source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS
        ).one()
        assert bonus.original_credits == Decimal("2.5")
        assert bonus.available_credits == (0 if reserved else Decimal("2.5"))
        assert bonus.reserved_credits == (Decimal("2.5") if reserved else 0)
        assert bonus.metadata_json["bucket_credit_state"] == (
            "reserved" if reserved else "available"
        )
        ledger = CreditLedgerEntry.query.filter_by(
            creator_bid=order.creator_bid, source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS
        ).one()
        assert ledger.wallet_bucket_bid == bonus.wallet_bucket_bid
        assert ledger.amount == Decimal("2.5")
        wallet = CreditWallet.query.filter_by(creator_bid=order.creator_bid).one()
        assert wallet.lifetime_granted_credits == Decimal("7.5")
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid=order.creator_bid).count()
            == 2
        )


def test_campaign_bonus_snapshot_failure_rolls_back_base_grant_and_bonus_together(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        order, _, _ = _seed(status=BILLING_ORDER_STATUS_PAID)
        order.campaign_bid = uuid4().hex
        order.campaign_bonus_credit_amount = Decimal("2.5")
        db.session.commit()
        original = subscriptions.persist_credit_wallet_snapshot
        writes: list[str] = []

        def persist_then_fail(*args: object, **kwargs: object) -> object:
            result = original(*args, **kwargs)
            writes.append("snapshot")
            if len(writes) == 2:
                db.session.flush()
                assert (
                    CreditWalletBucket.query.filter_by(
                        creator_bid=order.creator_bid
                    ).count()
                    == 2
                )
                message = "bonus snapshot failed"
                raise RuntimeError(message)
            return result

        monkeypatch.setattr(
            subscriptions, "persist_credit_wallet_snapshot", persist_then_fail
        )
        with pytest.raises(RuntimeError, match="bonus snapshot failed"):
            _grant(app, order)
        assert writes == ["snapshot", "snapshot"]
        assert (
            CreditWalletBucket.query.filter_by(creator_bid=order.creator_bid).count()
            == 0
        )
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid=order.creator_bid).count()
            == 0
        )
        assert CreditWallet.query.filter_by(creator_bid=order.creator_bid).count() == 0


@pytest.mark.parametrize(
    "gate",
    [
        "missing-creator",
        "no-buckets",
        "spent",
        "missing-subscription",
        "already-correct",
    ],
)
def test_topup_expiry_repair_skips_unsupported_or_unchanged_evidence(
    gate: str, app: Flask
) -> None:
    with app.app_context():
        order, _, _ = _seed(status=BILLING_ORDER_STATUS_PAID)
        if gate not in {"missing-creator", "no-buckets"}:
            assert _grant(app, order)
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid=order.creator_bid
            ).one()
            if gate == "spent":
                bucket.available_credits = 0
            if gate == "already-correct":
                from flaskr.service.billing.models import BillingSubscription

                expiry = bucket.effective_to or now_utc() + timedelta(days=30)
                db.session.add(
                    BillingSubscription(
                        subscription_bid=uuid4().hex,
                        creator_bid=order.creator_bid,
                        product_bid=order.product_bid,
                        billing_provider="manual",
                        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                        current_period_start_at=bucket.effective_from,
                        current_period_end_at=expiry,
                    )
                )
                bucket.effective_to = expiry
                CreditLedgerEntry.query.filter_by(
                    creator_bid=order.creator_bid
                ).one().expires_at = bucket.effective_to
            db.session.commit()
        result = subscriptions.repair_topup_grant_expiries(
            app, creator_bid=" " if gate == "missing-creator" else order.creator_bid
        )
        assert result["status"] == "noop"
        assert result["repaired_bucket_count"] == 0
        assert result["repaired_ledger_count"] == 0


@pytest.mark.parametrize(
    "evidence",
    [
        "no-paid-order",
        "missing-product",
        "paid-order",
        "expired-bucket",
        "already-matching",
    ],
)
def test_subscription_cycle_repair_requires_evidence_and_replays_idempotently(
    evidence: str, app: Flask
) -> None:
    with app.app_context():
        order, product, plan = _seed(
            subscription=True,
            status=BILLING_ORDER_STATUS_PAID
            if evidence != "no-paid-order"
            else BILLING_ORDER_STATUS_PENDING,
        )
        start = now_utc() - timedelta(days=2)
        end = start + timedelta(days=30)
        order.paid_at = start
        order.metadata_json = {
            "applied_cycle_start_at": start.isoformat(),
            "applied_cycle_end_at": end.isoformat(),
        }
        plan.current_period_start_at = (
            start if evidence == "already-matching" else now_utc() + timedelta(days=4)
        )
        plan.current_period_end_at = (
            end if evidence == "already-matching" else now_utc() + timedelta(days=5)
        )
        if evidence == "missing-product":
            product.deleted = 1
        if evidence == "expired-bucket":
            start, end = now_utc() - timedelta(days=35), now_utc() - timedelta(days=5)
            db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid=uuid4().hex,
                    wallet_bid=uuid4().hex,
                    creator_bid=order.creator_bid,
                    source_bid=order.bill_order_bid,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    priority=10,
                    original_credits=5,
                    available_credits=0,
                    effective_from=start,
                    effective_to=end,
                    status=CREDIT_BUCKET_STATUS_EXPIRED,
                )
            )
        db.session.commit()
        result = subscriptions.repair_subscription_cycle_mismatches(
            app, creator_bid=order.creator_bid, subscription_bid=plan.subscription_bid
        )
        should_repair = evidence in {"paid-order", "expired-bucket"}
        assert result.to_payload()["repaired_subscription_count"] == int(should_repair)
        db.session.expire_all()
        if should_repair:
            assert plan.current_period_start_at == start
            assert plan.current_period_end_at == end
            assert result.to_payload()["repaired_records"][0]["reason"] == (
                "latest_subscription_bucket"
                if evidence == "expired-bucket"
                else "latest_paid_subscription_order"
            )
            repeat = subscriptions.repair_subscription_cycle_mismatches(
                app, subscription_bid=plan.subscription_bid
            )
            assert repeat.status == "noop"
        else:
            assert plan.subscription_bid in result.skipped_subscription_bids

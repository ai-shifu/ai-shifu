"""Verify paid subscription refunds persist serializable metadata atomically."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.billing import checkout
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.order.models import StripeOrder
from flaskr.service.order.payment_providers.base import PaymentRefundResult
from flaskr.util.datetime import now_utc

from tests.common.fixtures.bill_products import build_billing_product

if TYPE_CHECKING:
    from flask import Flask


def _seed(
    *,
    provider: str = "stripe",
    status: int = BILLING_ORDER_STATUS_PENDING,
    subscription: bool = False,
) -> tuple[BillingOrder, BillingProduct, BillingSubscription | None]:
    product = build_billing_product(
        "bill-product-plan-monthly" if subscription else "bill-product-topup-small",
        overrides={
            "product_bid": uuid4().hex,
            "product_code": uuid4().hex,
            "credit_amount": Decimal(5),
        },
    )
    creator = uuid4().hex
    plan = (
        BillingSubscription(
            subscription_bid=uuid4().hex,
            creator_bid=creator,
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider=provider,
            metadata_json={},
            current_period_start_at=now_utc(),
            current_period_end_at=now_utc() + timedelta(days=30),
        )
        if subscription
        else None
    )
    order = BillingOrder(
        bill_order_bid=uuid4().hex,
        creator_bid=creator,
        product_bid=product.product_bid,
        subscription_bid=plan.subscription_bid if plan else "",
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START
        if plan
        else BILLING_ORDER_TYPE_TOPUP,
        payment_provider=provider,
        status=status,
        payable_amount=1000,
        paid_amount=1000 if status == BILLING_ORDER_STATUS_PAID else 0,
        provider_reference_id=f"ref-{uuid4().hex}",
        expires_at=now_utc() + timedelta(minutes=30),
        metadata_json={},
    )
    db.session.add_all([product, order] + ([plan] if plan else []))
    db.session.commit()
    return order, product, plan


@pytest.mark.parametrize("late_failure", [False, True])
def test_subscription_refund_commits_order_subscription_and_return_credits_atomically(
    late_failure: bool, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = f"re-{uuid4().hex}"
    provider = Mock(
        refund_payment=Mock(
            return_value=PaymentRefundResult(
                reference, {"id": reference, "status": "succeeded"}, "succeeded"
            )
        )
    )
    monkeypatch.setattr(checkout, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order, _, plan = _seed(status=BILLING_ORDER_STATUS_PAID, subscription=True)
        original_metadata = {
            "provider_extra": {
                "payment_intent_id": "pi_refund",
                "charge_id": "ch_refund",
            }
        }
        order.metadata_json = original_metadata
        snapshot = StripeOrder(
            stripe_order_bid=uuid4().hex,
            biz_domain="billing",
            bill_order_bid=order.bill_order_bid,
            order_bid="",
            payment_intent_id="pi_refund",
            latest_charge_id="ch_refund",
            metadata_json="{}",
            status=1,
        )
        db.session.add(snapshot)
        db.session.commit()
        original_grant = checkout.grant_refund_return_credits
        observed: list[str] = []

        def grant_then_fail(*args: object, **kwargs: object) -> object:
            result = original_grant(*args, **kwargs)
            db.session.flush()
            assert (
                CreditLedgerEntry.query.filter_by(creator_bid=order.creator_bid).count()
                == 1
            )
            observed.append(order.bill_order_bid)
            if late_failure:
                message = "failure after credit grant"
                raise RuntimeError(message)
            return result

        monkeypatch.setattr(checkout, "grant_refund_return_credits", grant_then_fail)
        if late_failure:
            with pytest.raises(RuntimeError, match="failure after credit grant"):
                checkout.refund_billing_order(
                    app,
                    order.creator_bid,
                    order.bill_order_bid,
                    {"amount": "1000", "reason": " requested "},
                )
        else:
            result = checkout.refund_billing_order(
                app,
                order.creator_bid,
                order.bill_order_bid,
                {"amount": "1000", "reason": " requested "},
            )
            assert result.refund_reference_id == reference
        assert observed == [order.bill_order_bid]
        request = provider.refund_payment.call_args.kwargs["request"]
        assert request.amount == 1000
        assert request.reason == "requested"
        assert request.metadata["payment_intent_id"] == "pi_refund"
        assert request.metadata["charge_id"] == "ch_refund"
        db.session.expire_all()
        assert order.status == (
            BILLING_ORDER_STATUS_PAID if late_failure else BILLING_ORDER_STATUS_REFUNDED
        )
        assert plan.status == (
            BILLING_SUBSCRIPTION_STATUS_ACTIVE
            if late_failure
            else BILLING_SUBSCRIPTION_STATUS_CANCELED
        )
        assert plan.cancel_at_period_end == int(not late_failure)
        entries = CreditLedgerEntry.query.filter_by(creator_bid=order.creator_bid).all()
        assert len(entries) == int(not late_failure)
        wallets = CreditWallet.query.filter_by(creator_bid=order.creator_bid).all()
        buckets = CreditWalletBucket.query.filter_by(
            creator_bid=order.creator_bid
        ).all()
        assert len(wallets) == len(buckets) == int(not late_failure)
        if not late_failure:
            assert entries[0].amount == Decimal(5)
            assert buckets[0].available_credits == 5
            # Subscription credits remain in the bucket after cancellation,
            # but the wallet exposes only credits that can currently be used.
            assert wallets[0].available_credits == 0
            assert wallets[0].reserved_credits == buckets[0].reserved_credits == 0
            assert entries[0].wallet_bucket_bid == buckets[0].wallet_bucket_bid
            assert entries[0].balance_after == 0
            assert order.refunded_at is not None
            assert order.metadata_json["refund_reference_id"] == reference
            assert plan.metadata_json["latest_source"] == "api_refund"
            assert plan.metadata_json["latest_provider_payload"] == {
                "id": reference,
                "status": "succeeded",
            }
            assert json.loads(snapshot.metadata_json)["last_refund_id"] == reference
            first_balance = wallets[0].available_credits
            checkout.refund_billing_order(
                app, order.creator_bid, order.bill_order_bid, {}
            )
            provider.refund_payment.assert_called_once()
            db.session.expire_all()
            assert wallets[0].available_credits == first_balance
            assert (
                CreditLedgerEntry.query.filter_by(creator_bid=order.creator_bid).count()
                == 1
            )
        else:
            assert order.refunded_at is None
            assert order.metadata_json == original_metadata
            assert plan.metadata_json == {}
            assert snapshot.metadata_json == "{}"
            assert snapshot.status == 1

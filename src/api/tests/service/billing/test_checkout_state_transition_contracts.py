"""Verify billing refunds, native reconciliation, and checkout transition guards."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_TYPE_PLAN,
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
from flaskr.service.common.models import AppError
from flaskr.service.order.models import AlipayOrder, StripeOrder, WechatPayOrder
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
    PaymentRefundResult,
)
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


@pytest.mark.parametrize(
    "gate", ["owner", "missing", "unpaid", "refunded", "pingxx", "alipay", "wechatpay"]
)
def test_refund_requires_owned_paid_supported_order_before_provider_call(
    gate: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    monkeypatch.setattr(checkout, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order, _, _ = _seed(
            provider=gate if gate in {"pingxx", "alipay", "wechatpay"} else "stripe",
            status=BILLING_ORDER_STATUS_PENDING
            if gate == "unpaid"
            else BILLING_ORDER_STATUS_REFUNDED
            if gate == "refunded"
            else BILLING_ORDER_STATUS_PAID,
        )
        if gate in {"owner", "missing", "unpaid"}:
            with pytest.raises(AppError):
                checkout.refund_billing_order(
                    app,
                    "other" if gate == "owner" else order.creator_bid,
                    "absent" if gate == "missing" else order.bill_order_bid,
                    {},
                )
        else:
            result = checkout.refund_billing_order(
                app, order.creator_bid, order.bill_order_bid, {}
            )
            assert result.status == (
                "refunded" if gate == "refunded" else "unsupported"
            )
        provider.refund_payment.assert_not_called()


@pytest.mark.parametrize("failure", ["failed", "canceled", "transport"])
def test_refund_failure_leaves_subscription_and_credits_unchanged(
    failure: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock(
        refund_payment=Mock(return_value=PaymentRefundResult("re-test", {}, failure))
    )
    if failure == "transport":
        provider.refund_payment.side_effect = RuntimeError("provider unavailable")
    monkeypatch.setattr(checkout, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order, _, plan = _seed(status=BILLING_ORDER_STATUS_PAID, subscription=True)
        with pytest.raises(RuntimeError if failure == "transport" else AppError):
            checkout.refund_billing_order(
                app, order.creator_bid, order.bill_order_bid, {"amount": "400"}
            )
        db.session.expire_all()
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert order.refunded_at is None
        assert plan.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid=order.creator_bid).count()
            == 0
        )


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


@pytest.mark.parametrize("provider_name", ["alipay", "wechatpay"])
@pytest.mark.parametrize("state", ["uncreated", "paid", "closed", "failed", "pending"])
def test_native_sync_persists_provider_evidence_and_expires_uncreated_orders(
    provider_name: str, state: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        order, _, _ = _seed(provider=provider_name)
        model = AlipayOrder if provider_name == "alipay" else WechatPayOrder
        snapshot = model(
            **{f"{provider_name}_order_bid": order.bill_order_bid},
            biz_domain="billing",
            bill_order_bid=order.bill_order_bid,
            order_bid="",
            provider_attempt_id=order.provider_reference_id,
            status=0,
        )
        db.session.add(snapshot)
        if state == "uncreated":
            order.provider_reference_id = ""
            order.expires_at = now_utc() - timedelta(minutes=1)
        db.session.commit()
        raw_status = (
            {
                "paid": "TRADE_SUCCESS",
                "closed": "TRADE_CLOSED",
                "failed": "PAYERROR",
                "pending": "WAIT_BUYER_PAY",
                "uncreated": "WAIT_BUYER_PAY",
            }[state]
            if provider_name == "alipay"
            else {
                "paid": "SUCCESS",
                "closed": "CLOSED",
                "failed": "PAYERROR",
                "pending": "NOTPAY",
                "uncreated": "NOTPAY",
            }[state]
        )
        payload = {
            "trade_status" if provider_name == "alipay" else "trade_state": raw_status,
            "out_trade_no": order.provider_reference_id,
            "trade_no"
            if provider_name == "alipay"
            else "transaction_id": "transaction-test",
        }
        provider = Mock(
            sync_reference=Mock(
                return_value=PaymentNotificationResult(
                    order.provider_reference_id, raw_status, payload, "transaction-test"
                )
            )
        )
        monkeypatch.setattr(
            checkout, "get_payment_provider", Mock(return_value=provider)
        )
        # Keep dispatch external; state transitions and wallet writes remain real.
        from flaskr.service.billing import provider_state

        dispatch = Mock()
        monkeypatch.setattr(
            provider_state.BillingOrderProviderUpdateResult,
            "dispatch_after_commit",
            dispatch,
        )
        result = checkout.sync_billing_order(
            app, order.creator_bid, order.bill_order_bid, {}
        )
        db.session.expire_all()
        expected = {
            "uncreated": "timeout",
            "paid": "paid",
            "closed": "canceled",
            "failed": "pending" if provider_name == "alipay" else "failed",
            "pending": "pending",
        }[state]
        assert result.status == expected
        if state == "uncreated":
            provider.sync_reference.assert_not_called()
            assert order.status == BILLING_ORDER_STATUS_TIMEOUT
        else:
            provider.sync_reference.assert_called_once_with(
                provider_reference=order.provider_reference_id,
                reference_type="payment",
                app=app,
            )
            assert snapshot.transaction_id == "transaction-test"
            assert snapshot.raw_status == raw_status
            assert snapshot.raw_response != "{}"
        if state == "paid":
            assert (
                CreditLedgerEntry.query.filter_by(creator_bid=order.creator_bid).count()
                == 1
            )
        dispatch.assert_called_once()


@pytest.mark.parametrize("gate", ["owner", "paid", "expired", "missing-product"])
def test_reopen_checkout_rejects_unusable_orders_and_persists_timeout(
    gate: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    monkeypatch.setattr(checkout, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order, product, _ = _seed(
            status=BILLING_ORDER_STATUS_PAID
            if gate == "paid"
            else BILLING_ORDER_STATUS_PENDING
        )
        if gate == "expired":
            order.expires_at = now_utc() - timedelta(seconds=1)
        if gate == "missing-product":
            product.deleted = 1
        db.session.commit()
        with pytest.raises(AppError):
            checkout.create_billing_order_checkout(
                app,
                "other" if gate == "owner" else order.creator_bid,
                order.bill_order_bid,
                {},
            )
        db.session.expire_all()
        assert order.status == (
            BILLING_ORDER_STATUS_TIMEOUT
            if gate == "expired"
            else BILLING_ORDER_STATUS_PAID
            if gate == "paid"
            else BILLING_ORDER_STATUS_PENDING
        )
        provider.create_payment.assert_not_called()


@pytest.mark.parametrize("rollback", [False, True])
def test_zero_amount_checkout_stages_credit_grant_within_callers_transaction(
    rollback: bool, app: Flask
) -> None:
    with app.app_context():
        order, _, _ = _seed(subscription=True)
        order.payable_amount = 0
        order.provider_reference_id = ""
        order.metadata_json = {"prepaid_offset_amount": 1000}
        db.session.commit()

        def complete() -> None:
            with unit_of_work():
                response, effects = (
                    checkout._complete_zero_amount_subscription_checkout(app, order)
                )
                assert response.status == "paid"
                assert response.payable_amount == 0
                assert effects.bill_order_bid == order.bill_order_bid
                db.session.flush()
                assert (
                    CreditLedgerEntry.query.filter_by(
                        creator_bid=order.creator_bid
                    ).count()
                    == 1
                )
                if rollback:
                    message = "caller rejected checkout"
                    raise RuntimeError(message)

        if rollback:
            with pytest.raises(RuntimeError, match="caller rejected checkout"):
                complete()
        else:
            complete()
        db.session.expire_all()
        assert order.status == (
            BILLING_ORDER_STATUS_PENDING if rollback else BILLING_ORDER_STATUS_PAID
        )
        assert CreditLedgerEntry.query.filter_by(
            creator_bid=order.creator_bid
        ).count() == int(not rollback)
        if not rollback:
            assert order.provider_reference_id == f"zero_amount:{order.bill_order_bid}"
            assert order.metadata_json["zero_amount_offset"] is True
            assert order.metadata_json["prepaid_offset_amount"] == 1000
            assert order.paid_amount == 0


@pytest.mark.parametrize(
    "gate", ["missing-tier", "unpaid-preorder", "zero-prepaid", "too-expensive-offset"]
)
def test_immediate_upgrade_validates_tier_and_paid_preorder_offset(gate: str) -> None:
    current = BillingProduct(sort_order=None if gate == "missing-tier" else 1)
    target = BillingProduct(sort_order=2, price_amount=1000)
    preorder = BillingOrder(
        status=BILLING_ORDER_STATUS_PENDING
        if gate == "unpaid-preorder"
        else BILLING_ORDER_STATUS_PAID,
        paid_amount=0 if gate == "zero-prepaid" else 1000,
    )
    if gate in {"missing-tier", "too-expensive-offset"}:
        with pytest.raises(AppError):
            checkout._validate_immediate_upgrade_checkout(
                current_product=current,
                target_product=target,
                active_preorder_order=preorder,
            )
    else:
        assert (
            checkout._validate_immediate_upgrade_checkout(
                current_product=current,
                target_product=target,
                active_preorder_order=preorder,
            )
            == 0
        )


@pytest.mark.parametrize(
    "gate",
    [
        "stripe",
        "mismatched-provider",
        "missing-current",
        "missing-tier",
        "upgrade",
        "missing-period",
        "no-cycle",
    ],
)
def test_preorder_refuses_incompatible_provider_product_and_period(gate: str) -> None:
    current = BillingProduct(
        product_bid="current",
        product_code="paid",
        sort_order=None if gate == "missing-tier" else 2,
    )
    target = BillingProduct(
        product_bid="target",
        product_code="target",
        sort_order=3 if gate == "upgrade" else 1,
        billing_interval=0,
    )
    plan = BillingSubscription(
        billing_provider="alipay",
        current_period_end_at=None if gate == "missing-period" else now_utc(),
    )
    with pytest.raises(AppError):
        checkout._prepare_subscription_preorder_checkout_metadata(
            subscription=plan,
            current_product=None if gate == "missing-current" else current,
            target_product=target,
            active_preorder_order=None,
            payment_provider="stripe"
            if gate == "stripe"
            else "wechatpay"
            if gate == "mismatched-provider"
            else "alipay",
        )


@pytest.mark.parametrize("gate", ["blank", "missing", "wrong-type", "trial"])
def test_catalog_checkout_hides_unavailable_and_trial_products(
    gate: str, app: Flask
) -> None:
    with app.app_context():
        order, product, _ = _seed(subscription=True)
        if gate == "trial":
            product.product_code = "creator-plan-trial"
            product.metadata_json = {"public_trial_offer": True}
        elif gate == "wrong-type":
            product.product_type = 0
        db.session.commit()
        with pytest.raises(AppError):
            checkout._load_catalog_product(
                ""
                if gate == "blank"
                else "absent"
                if gate == "missing"
                else order.product_bid,
                BILLING_PRODUCT_TYPE_PLAN,
            )

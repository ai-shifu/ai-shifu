"""Shared post-paid side-effect orchestration for billing orders."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Flask

from .credit_notifications import (
    enqueue_credit_notification as _enqueue_credit_notification,
    stage_credit_granted_notification_for_order as _stage_credit_granted_notification_for_order,
)
from .consts import BILLING_ORDER_STATUS_PAID
from .models import BillingOrder
from .notifications import (
    enqueue_billing_paid_feishu as _enqueue_billing_paid_feishu,
    enqueue_subscription_purchase_sms as _enqueue_subscription_purchase_sms,
    stage_billing_paid_feishu_for_paid_order as _stage_billing_paid_feishu_for_paid_order,
    stage_subscription_purchase_sms_for_paid_order as _stage_subscription_purchase_sms_for_paid_order,
)
from .subscriptions import grant_paid_order_credits as _grant_paid_order_credits


@dataclass(slots=True, frozen=True)
class BillingPaidOrderSideEffects:
    bill_order_bid: str = ""
    should_enqueue_subscription_purchase_sms: bool = False
    should_enqueue_billing_paid_feishu: bool = False
    credit_notification_bids: tuple[str, ...] = ()


def stage_billing_paid_order_side_effects(
    app: Flask,
    order: BillingOrder | None,
    *,
    previous_status: int | None,
) -> BillingPaidOrderSideEffects:
    """Stage idempotent side effects for one paid billing order."""

    if order is None or order.status != BILLING_ORDER_STATUS_PAID:
        return BillingPaidOrderSideEffects()

    granted = _grant_paid_order_credits(app, order)
    credit_notification_bids: list[str] = []
    if granted:
        grant_notification = _stage_credit_granted_notification_for_order(
            app,
            creator_bid=order.creator_bid,
            bill_order_bid=order.bill_order_bid,
            commit=False,
            enqueue=False,
        )
        notification_bid = str(grant_notification.get("notification_bid") or "").strip()
        if grant_notification.get("status") == "pending" and notification_bid:
            credit_notification_bids.append(notification_bid)
    should_enqueue_subscription_purchase_sms = (
        _stage_subscription_purchase_sms_for_paid_order(
            order,
            previous_status=previous_status,
        )
    )
    should_enqueue_billing_paid_feishu = _stage_billing_paid_feishu_for_paid_order(
        order,
        previous_status=previous_status,
    )
    return BillingPaidOrderSideEffects(
        bill_order_bid=order.bill_order_bid,
        should_enqueue_subscription_purchase_sms=should_enqueue_subscription_purchase_sms,
        should_enqueue_billing_paid_feishu=should_enqueue_billing_paid_feishu,
        credit_notification_bids=tuple(credit_notification_bids),
    )


def dispatch_billing_paid_order_side_effects(
    app: Flask,
    side_effects: BillingPaidOrderSideEffects,
) -> None:
    """Dispatch post-commit side effects for one paid billing order."""

    if not side_effects.bill_order_bid:
        return
    if side_effects.should_enqueue_subscription_purchase_sms:
        _enqueue_subscription_purchase_sms(
            app,
            bill_order_bid=side_effects.bill_order_bid,
        )
    if side_effects.should_enqueue_billing_paid_feishu:
        _enqueue_billing_paid_feishu(
            app,
            bill_order_bid=side_effects.bill_order_bid,
        )
    for notification_bid in side_effects.credit_notification_bids:
        _enqueue_credit_notification(app, notification_bid=notification_bid)

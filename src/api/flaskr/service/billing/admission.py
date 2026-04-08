"""Admission checks for creator-billed runtime requests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.service.common.models import raise_error

from .consts import (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
)
from .models import BillingSubscription, CreditWallet, CreditWalletBucket
from .ownership import resolve_shifu_creator_bid

_ZERO_CREDITS = Decimal("0")
_ADMISSION_ACTIVE_SUBSCRIPTION_STATUSES = (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)


def admit_creator_usage(
    app: Flask,
    *,
    creator_bid: str = "",
    shifu_bid: str = "",
    usage_scene: int | None = None,
) -> dict[str, Any]:
    """Validate whether a creator-owned usage request may proceed."""

    normalized_creator_bid = _resolve_creator_bid(
        app,
        creator_bid=creator_bid,
        shifu_bid=shifu_bid,
    )
    if not normalized_creator_bid:
        raise_error("server.shifu.shifuNotFound")

    with app.app_context():
        wallet = (
            CreditWallet.query.filter(
                CreditWallet.deleted == 0,
                CreditWallet.creator_bid == normalized_creator_bid,
            )
            .order_by(CreditWallet.id.desc())
            .first()
        )
        buckets = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.creator_bid == normalized_creator_bid,
                CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
            )
            .order_by(CreditWalletBucket.priority.asc(), CreditWalletBucket.id.asc())
            .all()
        )
        subscription = (
            BillingSubscription.query.filter(
                BillingSubscription.deleted == 0,
                BillingSubscription.creator_bid == normalized_creator_bid,
            )
            .order_by(
                BillingSubscription.created_at.desc(),
                BillingSubscription.id.desc(),
            )
            .first()
        )

        wallet_available_credits = _to_decimal(
            getattr(wallet, "available_credits", _ZERO_CREDITS)
        )
        active_buckets = [
            bucket
            for bucket in buckets
            if _to_decimal(bucket.available_credits) > _ZERO_CREDITS
        ]
        if wallet_available_credits <= _ZERO_CREDITS and not active_buckets:
            raise_error("server.billing.creditInsufficient")

        has_active_subscription = (
            subscription is not None
            and subscription.status in _ADMISSION_ACTIVE_SUBSCRIPTION_STATUSES
        )
        has_non_subscription_credits = any(
            bucket.bucket_category != CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            for bucket in active_buckets
        )
        if not has_active_subscription and not has_non_subscription_credits:
            raise_error("server.billing.subscriptionInactive")

        return {
            "allowed": True,
            "creator_bid": normalized_creator_bid,
            "shifu_bid": str(shifu_bid or "").strip(),
            "usage_scene": usage_scene,
            "wallet_available_credits": wallet_available_credits,
            "subscription_status": getattr(subscription, "status", None),
        }


def _resolve_creator_bid(app: Flask, *, creator_bid: str, shifu_bid: str) -> str:
    normalized_creator_bid = str(creator_bid or "").strip()
    if normalized_creator_bid:
        return normalized_creator_bid
    return str(resolve_shifu_creator_bid(app, shifu_bid) or "").strip()


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))

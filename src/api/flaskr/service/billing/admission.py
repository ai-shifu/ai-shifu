"""Admission checks for creator-billed runtime requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.service.common.models import raise_error

from .bucket_categories import (
    load_billing_order_type_by_bid,
    wallet_bucket_requires_active_subscription,
)
from .consts import CREDIT_BUCKET_CATEGORY_SUBSCRIPTION, CREDIT_BUCKET_STATUS_ACTIVE
from .entitlements import resolve_creator_entitlement_state
from .models import BillingSubscription, CreditWalletBucket
from .ownership import resolve_shifu_creator_bid
from .primitives import is_billing_enabled
from .primitives import to_decimal as _to_decimal
from .subscriptions import load_effective_topup_subscription

_ZERO_CREDITS = Decimal("0")


@dataclass(slots=True, frozen=True)
class CreatorUsageAdmission:
    allowed: bool
    creator_bid: str
    shifu_bid: str
    usage_scene: int | None
    wallet_available_credits: Decimal
    subscription_status: int | None
    priority_class: str

    def to_response_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "creator_bid": self.creator_bid,
            "shifu_bid": self.shifu_bid,
            "usage_scene": self.usage_scene,
            "wallet_available_credits": self.wallet_available_credits,
            "subscription_status": self.subscription_status,
            "priority_class": self.priority_class,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_response_dict()[key]


def admit_creator_usage(
    app: Flask,
    *,
    creator_bid: str = "",
    shifu_bid: str = "",
    usage_scene: int | None = None,
) -> CreatorUsageAdmission:
    """Validate whether a creator-owned usage request may proceed."""

    normalized_creator_bid = _resolve_creator_bid(
        app,
        creator_bid=creator_bid,
        shifu_bid=shifu_bid,
    )
    if not normalized_creator_bid:
        raise_error("server.shifu.shifuNotFound")

    if not is_billing_enabled():
        return CreatorUsageAdmission(
            allowed=True,
            creator_bid=normalized_creator_bid,
            shifu_bid=str(shifu_bid or "").strip(),
            usage_scene=usage_scene,
            wallet_available_credits=_ZERO_CREDITS,
            subscription_status=None,
            priority_class="standard",
        )

    with app.app_context():
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

        admission_at = datetime.now()
        active_buckets = [
            bucket
            for bucket in buckets
            if _to_decimal(bucket.available_credits) > _ZERO_CREDITS
            and (bucket.effective_from is None or bucket.effective_from <= admission_at)
            and (bucket.effective_to is None or bucket.effective_to > admission_at)
        ]
        has_active_subscription = (
            load_effective_topup_subscription(
                normalized_creator_bid,
                as_of=admission_at,
            )
            is not None
        )
        consumable_buckets = [
            bucket
            for bucket in active_buckets
            if has_active_subscription
            or not wallet_bucket_requires_active_subscription(
                bucket,
                load_order_type=load_billing_order_type_by_bid,
            )
        ]
        wallet_available_credits = sum(
            (_to_decimal(bucket.available_credits) for bucket in consumable_buckets),
            start=_ZERO_CREDITS,
        )
        if wallet_available_credits <= _ZERO_CREDITS and not consumable_buckets:
            if active_buckets and not has_active_subscription:
                active_subscription_bucket = next(
                    (
                        bucket
                        for bucket in active_buckets
                        if int(bucket.bucket_category or 0)
                        == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
                    ),
                    None,
                )
                if active_subscription_bucket is not None:
                    app.logger.warning(
                        "billing admission invariant violated: creator has an active "
                        "subscription bucket but no active subscription "
                        "creator_bid=%s shifu_bid=%s wallet_bucket_bid=%s "
                        "source_bid=%s effective_from=%s effective_to=%s",
                        normalized_creator_bid,
                        str(shifu_bid or "").strip(),
                        active_subscription_bucket.wallet_bucket_bid,
                        active_subscription_bucket.source_bid,
                        active_subscription_bucket.effective_from,
                        active_subscription_bucket.effective_to,
                    )
                if any(
                    wallet_bucket_requires_active_subscription(
                        bucket,
                        load_order_type=load_billing_order_type_by_bid,
                    )
                    for bucket in active_buckets
                ):
                    raise_error("server.billing.subscriptionInactive")
            raise_error("server.billing.creditInsufficient")

        entitlement_state = resolve_creator_entitlement_state(
            normalized_creator_bid,
            as_of=admission_at,
        )
        return CreatorUsageAdmission(
            allowed=True,
            creator_bid=normalized_creator_bid,
            shifu_bid=str(shifu_bid or "").strip(),
            usage_scene=usage_scene,
            wallet_available_credits=wallet_available_credits,
            subscription_status=getattr(subscription, "status", None),
            priority_class=entitlement_state.priority_class,
        )


def _resolve_creator_bid(app: Flask, *, creator_bid: str, shifu_bid: str) -> str:
    normalized_creator_bid = str(creator_bid or "").strip()
    if normalized_creator_bid:
        return normalized_creator_bid
    return str(resolve_shifu_creator_bid(app, shifu_bid) or "").strip()

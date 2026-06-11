"""Billing helper for referral invitation plan rewards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from flask import Flask, has_app_context

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.uuid import generate_id

_MANUAL_PROVIDER_NAME = "manual"
_CHECKOUT_TYPE = "referral_invitation_reward"


@dataclass(slots=True, frozen=True)
class ReferralPlanRewardRequest:
    reward_bid: str
    inviter_user_bid: str
    campaign_bid: str
    reward_rule_bid: str
    product_code: str
    cycle_count: int
    credit_amount: Decimal | None
    credit_validity_days: int | None
    timing_policy: str
    rule_snapshot: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ReferralPlanRewardResult:
    inviter_user_bid: str
    product_bid: str
    product_code: str
    subscription_bid: str
    bill_order_bid: str
    wallet_bucket_bid: str = ""
    ledger_bid: str = ""
    reused_existing_reward: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "inviter_user_bid": self.inviter_user_bid,
            "product_bid": self.product_bid,
            "product_code": self.product_code,
            "subscription_bid": self.subscription_bid,
            "bill_order_bid": self.bill_order_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "ledger_bid": self.ledger_bid,
            "reused_existing_reward": self.reused_existing_reward,
        }


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, *_exc):
        return False


def _with_app_context(app: Flask):
    return _NullContext() if has_app_context() else app.app_context()


def _provider_reference(reward_bid: str) -> str:
    return f"referral-reward:{reward_bid}"


def _normalize_bid(value: object) -> str:
    return str(value or "").strip()


def _billing_consts():
    from . import consts

    return consts


def _billing_models():
    from . import models

    return models


def _load_reward_product(product_code: str):
    consts = _billing_consts()
    models = _billing_models()
    return (
        models.BillingProduct.query.filter(
            models.BillingProduct.deleted == 0,
            models.BillingProduct.product_code == str(product_code or "").strip(),
            models.BillingProduct.product_type == consts.BILLING_PRODUCT_TYPE_PLAN,
            models.BillingProduct.status == consts.BILLING_PRODUCT_STATUS_ACTIVE,
        )
        .order_by(models.BillingProduct.id.desc())
        .first()
    )


def _load_product_by_bid(product_bid: str):
    consts = _billing_consts()
    models = _billing_models()
    return (
        models.BillingProduct.query.filter(
            models.BillingProduct.deleted == 0,
            models.BillingProduct.product_bid == _normalize_bid(product_bid),
            models.BillingProduct.product_type == consts.BILLING_PRODUCT_TYPE_PLAN,
        )
        .order_by(models.BillingProduct.id.desc())
        .first()
    )


def _is_trial_subscription_product(subscription, product) -> bool:
    consts = _billing_consts()
    product_bid = _normalize_bid(getattr(product, "product_bid", ""))
    product_code = str(getattr(product, "product_code", "") or "").strip()
    product_metadata = (
        product.metadata_json
        if product is not None and isinstance(product.metadata_json, dict)
        else {}
    )
    subscription_metadata = (
        subscription.metadata_json
        if subscription is not None and isinstance(subscription.metadata_json, dict)
        else {}
    )
    return (
        product_bid == consts.BILLING_TRIAL_PRODUCT_BID
        or product_code == consts.BILLING_TRIAL_PRODUCT_CODE
        or bool(product_metadata.get(consts.BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG))
        or bool(subscription_metadata.get("trial_bootstrap"))
    )


def _load_existing_order(
    *,
    inviter_user_bid: str,
    reward_bid: str,
) -> object | None:
    consts = _billing_consts()
    models = _billing_models()
    return (
        models.BillingOrder.query.filter(
            models.BillingOrder.deleted == 0,
            models.BillingOrder.creator_bid == inviter_user_bid,
            models.BillingOrder.payment_provider == _MANUAL_PROVIDER_NAME,
            models.BillingOrder.provider_reference_id
            == _provider_reference(reward_bid),
            models.BillingOrder.status == consts.BILLING_ORDER_STATUS_PAID,
        )
        .order_by(models.BillingOrder.id.desc())
        .first()
    )


def _load_primary_active_subscription(creator_bid: str, *, as_of: datetime):
    from .queries import load_primary_active_subscription

    return load_primary_active_subscription(creator_bid, as_of=as_of)


def _calculate_self_managed_billing_cycle_end(
    product,
    *,
    cycle_start_at: datetime,
):
    from .queries import calculate_self_managed_billing_cycle_end

    return calculate_self_managed_billing_cycle_end(
        product,
        cycle_start_at=cycle_start_at,
    )


def _calculate_self_managed_billing_cycle_end_after_boundary(
    product,
    *,
    cycle_boundary_at: datetime,
):
    from .queries import calculate_self_managed_billing_cycle_end_after_boundary

    return calculate_self_managed_billing_cycle_end_after_boundary(
        product,
        cycle_boundary_at=cycle_boundary_at,
    )


def _extract_order_metadata_datetime(metadata: Any, key: str) -> datetime | None:
    from .queries import extract_order_metadata_datetime

    return extract_order_metadata_datetime(metadata, key)


def _grant_paid_order_credits(app: Flask, order) -> bool:
    from .subscriptions import grant_paid_order_credits

    return grant_paid_order_credits(app, order)


def _is_self_managed_billing_provider(provider_name: str) -> bool:
    from .subscriptions import is_self_managed_billing_provider

    return is_self_managed_billing_provider(provider_name)


def _load_bucket_and_ledger(order) -> tuple[str, str]:
    models = _billing_models()
    bucket = (
        models.CreditWalletBucket.query.filter(
            models.CreditWalletBucket.deleted == 0,
            models.CreditWalletBucket.creator_bid == order.creator_bid,
            models.CreditWalletBucket.source_bid == order.bill_order_bid,
        )
        .order_by(models.CreditWalletBucket.id.desc())
        .first()
    )
    ledger = (
        models.CreditLedgerEntry.query.filter(
            models.CreditLedgerEntry.deleted == 0,
            models.CreditLedgerEntry.creator_bid == order.creator_bid,
            models.CreditLedgerEntry.source_bid == order.bill_order_bid,
        )
        .order_by(models.CreditLedgerEntry.id.desc())
        .first()
    )
    return (
        str(bucket.wallet_bucket_bid or "").strip() if bucket is not None else "",
        str(ledger.ledger_bid or "").strip() if ledger is not None else "",
    )


def _validate_reward_product(
    product,
    *,
    request: ReferralPlanRewardRequest,
) -> None:
    if request.credit_amount is not None:
        product_amount = Decimal(str(product.credit_amount or "0"))
        if product_amount != Decimal(str(request.credit_amount)):
            raise_error("server.billing.referralRewardProductMismatch")
    if int(request.cycle_count or 0) <= 0:
        raise_param_error("cycle_count")


def _cycle_end_from_start(product, cycle_start_at: datetime) -> datetime:
    cycle_end_at = _calculate_self_managed_billing_cycle_end(
        product,
        cycle_start_at=cycle_start_at,
    )
    if cycle_end_at is None or cycle_end_at <= cycle_start_at:
        raise_error("server.common.systemError")
    return cycle_end_at


def _cycle_end_after_boundary(
    product,
    cycle_boundary_at: datetime,
) -> datetime:
    cycle_end_at = _calculate_self_managed_billing_cycle_end_after_boundary(
        product,
        cycle_boundary_at=cycle_boundary_at,
    )
    if cycle_end_at is None or cycle_end_at <= cycle_boundary_at:
        raise_error("server.common.systemError")
    return cycle_end_at


def _is_referral_reward_order(order) -> bool:
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    checkout_type = str(metadata.get("checkout_type") or "").strip()
    return checkout_type == _CHECKOUT_TYPE or bool(
        metadata.get("referral_invitation_reward") is True
    )


def _latest_referral_renewal_cycle_end_after(
    *,
    creator_bid: str,
    subscription_bid: str,
    boundary_at: datetime,
) -> datetime | None:
    consts = _billing_consts()
    models = _billing_models()
    rows = (
        models.BillingOrder.query.filter(
            models.BillingOrder.deleted == 0,
            models.BillingOrder.creator_bid == _normalize_bid(creator_bid),
            models.BillingOrder.subscription_bid == _normalize_bid(subscription_bid),
            models.BillingOrder.order_type
            == consts.BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            models.BillingOrder.status == consts.BILLING_ORDER_STATUS_PAID,
            models.BillingOrder.payment_provider == _MANUAL_PROVIDER_NAME,
        )
        .order_by(models.BillingOrder.id.asc())
        .all()
    )
    latest_cycle_end_at: datetime | None = None
    for order in rows:
        if not _is_referral_reward_order(order):
            continue
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        cycle_end_at = _extract_order_metadata_datetime(
            metadata,
            "renewal_cycle_end_at",
        )
        if cycle_end_at is None or cycle_end_at <= boundary_at:
            continue
        if latest_cycle_end_at is None or cycle_end_at > latest_cycle_end_at:
            latest_cycle_end_at = cycle_end_at
    return latest_cycle_end_at


def _resolve_referral_renewal_cycle_start_at(
    *,
    active_subscription,
    now: datetime,
) -> datetime:
    cycle_start_at = active_subscription.current_period_end_at or now
    queued_cycle_end_at = _latest_referral_renewal_cycle_end_after(
        creator_bid=active_subscription.creator_bid,
        subscription_bid=active_subscription.subscription_bid,
        boundary_at=cycle_start_at,
    )
    if queued_cycle_end_at is not None:
        return queued_cycle_end_at
    return cycle_start_at


def _classify_deferred_entitlement(active_subscription, current_product) -> str:
    if _is_trial_subscription_product(active_subscription, current_product):
        return "trial"
    return "paid"


def _resolve_order_shape(
    *,
    request: ReferralPlanRewardRequest,
    product,
    now: datetime,
) -> tuple[object, int, datetime, datetime, dict[str, Any]]:
    consts = _billing_consts()
    models = _billing_models()
    active_subscription = _load_primary_active_subscription(
        request.inviter_user_bid,
        as_of=now,
    )
    metadata: dict[str, Any] = {
        "checkout_type": _CHECKOUT_TYPE,
        "referral_invitation_reward": True,
        "reward_bid": request.reward_bid,
        "campaign_bid": request.campaign_bid,
        "reward_rule_bid": request.reward_rule_bid,
        "rule_snapshot": request.rule_snapshot,
    }

    if active_subscription is None:
        cycle_start_at = now
        cycle_end_at = _cycle_end_from_start(product, cycle_start_at)
        subscription = models.BillingSubscription(
            subscription_bid=generate_id(None),
            creator_bid=request.inviter_user_bid,
            product_bid=product.product_bid,
            status=consts.BILLING_SUBSCRIPTION_STATUS_DRAFT,
            billing_provider=_MANUAL_PROVIDER_NAME,
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=cycle_start_at,
            current_period_start_at=cycle_start_at,
            current_period_end_at=cycle_end_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=None,
            last_failed_at=None,
            metadata_json={
                "referral_invitation_reward": True,
                "campaign_bid": request.campaign_bid,
                "reward_rule_bid": request.reward_rule_bid,
            },
        )
        metadata["applied_cycle_start_at"] = cycle_start_at.isoformat()
        metadata["applied_cycle_end_at"] = cycle_end_at.isoformat()
        return (
            subscription,
            consts.BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            cycle_start_at,
            cycle_end_at,
            metadata,
        )

    current_product_bid = _normalize_bid(active_subscription.product_bid)
    current_product = _load_product_by_bid(current_product_bid)

    cycle_start_at = _resolve_referral_renewal_cycle_start_at(
        active_subscription=active_subscription,
        now=now,
    )
    cycle_end_at = _cycle_end_after_boundary(product, cycle_start_at)
    metadata["renewal_cycle_start_at"] = cycle_start_at.isoformat()
    metadata["renewal_cycle_end_at"] = cycle_end_at.isoformat()
    metadata["deferred_after_entitlement"] = _classify_deferred_entitlement(
        active_subscription,
        current_product,
    )
    metadata["deferred_after_subscription_bid"] = active_subscription.subscription_bid
    if current_product is not None:
        metadata["deferred_after_product_bid"] = current_product.product_bid

    if current_product_bid == product.product_bid and _is_self_managed_billing_provider(
        active_subscription.billing_provider
    ):
        return (
            active_subscription,
            consts.BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            cycle_start_at,
            cycle_end_at,
            metadata,
        )

    return (
        active_subscription,
        consts.BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        cycle_start_at,
        cycle_end_at,
        metadata,
    )


def grant_referral_plan_reward(
    app: Flask,
    *,
    request: ReferralPlanRewardRequest,
) -> ReferralPlanRewardResult:
    """Grant one referral plan reward through billing order artifacts."""

    with _with_app_context(app):
        consts = _billing_consts()
        models = _billing_models()
        normalized_reward_bid = _normalize_bid(request.reward_bid)
        normalized_inviter_user_bid = _normalize_bid(request.inviter_user_bid)
        if not normalized_reward_bid:
            raise_param_error("reward_bid")
        if not normalized_inviter_user_bid:
            raise_param_error("inviter_user_bid")

        product = _load_reward_product(request.product_code)
        if product is None:
            raise_param_error("product_code")
        _validate_reward_product(product, request=request)

        existing_order = _load_existing_order(
            inviter_user_bid=normalized_inviter_user_bid,
            reward_bid=normalized_reward_bid,
        )
        if existing_order is not None:
            _grant_paid_order_credits(app, existing_order)
            db.session.commit()
            bucket_bid, ledger_bid = _load_bucket_and_ledger(existing_order)
            return ReferralPlanRewardResult(
                inviter_user_bid=normalized_inviter_user_bid,
                product_bid=str(existing_order.product_bid or "").strip(),
                product_code=str(product.product_code or "").strip(),
                subscription_bid=str(existing_order.subscription_bid or "").strip(),
                bill_order_bid=str(existing_order.bill_order_bid or "").strip(),
                wallet_bucket_bid=bucket_bid,
                ledger_bid=ledger_bid,
                reused_existing_reward=True,
            )

        now = datetime.now()
        safe_request = ReferralPlanRewardRequest(
            reward_bid=normalized_reward_bid,
            inviter_user_bid=normalized_inviter_user_bid,
            campaign_bid=_normalize_bid(request.campaign_bid),
            reward_rule_bid=_normalize_bid(request.reward_rule_bid),
            product_code=str(request.product_code or "").strip(),
            cycle_count=request.cycle_count,
            credit_amount=request.credit_amount,
            credit_validity_days=request.credit_validity_days,
            timing_policy=str(request.timing_policy or "").strip(),
            rule_snapshot=dict(request.rule_snapshot or {}),
        )
        subscription, order_type, _cycle_start_at, _cycle_end_at, metadata = (
            _resolve_order_shape(request=safe_request, product=product, now=now)
        )
        db.session.add(subscription)
        db.session.flush()

        order = models.BillingOrder(
            bill_order_bid=generate_id(app),
            creator_bid=normalized_inviter_user_bid,
            order_type=order_type,
            product_bid=product.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency=product.currency,
            payable_amount=0,
            paid_amount=0,
            payment_provider=_MANUAL_PROVIDER_NAME,
            channel=_MANUAL_PROVIDER_NAME,
            provider_reference_id=_provider_reference(normalized_reward_bid),
            status=consts.BILLING_ORDER_STATUS_PAID,
            paid_at=now,
            metadata_json=metadata,
        )
        db.session.add(order)
        db.session.flush()

        _grant_paid_order_credits(app, order)
        db.session.commit()
        bucket_bid, ledger_bid = _load_bucket_and_ledger(order)
        return ReferralPlanRewardResult(
            inviter_user_bid=normalized_inviter_user_bid,
            product_bid=product.product_bid,
            product_code=str(product.product_code or "").strip(),
            subscription_bid=str(subscription.subscription_bid or "").strip(),
            bill_order_bid=str(order.bill_order_bid or "").strip(),
            wallet_bucket_bid=bucket_bid,
            ledger_bid=ledger_bid,
            reused_existing_reward=False,
        )

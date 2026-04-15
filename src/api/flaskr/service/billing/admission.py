"""Admission checks for creator-billed runtime requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Any

from flask import Flask

from flaskr.common.cache_provider import cache as cache_provider
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
from .bucket_categories import (
    load_billing_order_type_by_bid,
    resolve_wallet_bucket_runtime_category,
)
from .entitlements import resolve_creator_entitlement_state
from .models import BillingSubscription, CreditWalletBucket
from .ownership import resolve_shifu_creator_bid
from .primitives import to_decimal as _to_decimal

_ZERO_CREDITS = Decimal("0")
_RUNTIME_CONCURRENCY_KEY_SUFFIX = ":billing:runtime:concurrency:"
_RUNTIME_CONCURRENCY_LOCK_KEY_SUFFIX = ":billing:runtime:concurrency:lock:"
_RUNTIME_CONCURRENCY_LOCK_TIMEOUT_SECONDS = 5
_RUNTIME_CONCURRENCY_SLOT_TTL_SECONDS = 3600
_ADMISSION_ACTIVE_SUBSCRIPTION_STATUSES = (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)


@dataclass
class CreatorRuntimeAdmissionLease:
    app: Flask
    creator_bid: str
    counter_key: str
    lock_key: str
    active_runtime_count: int
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        _decrement_runtime_concurrency(
            self.app,
            counter_key=self.counter_key,
            lock_key=self.lock_key,
        )

    def __enter__(self) -> "CreatorRuntimeAdmissionLease":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


@dataclass(slots=True, frozen=True)
class CreatorUsageAdmission:
    allowed: bool
    creator_bid: str
    shifu_bid: str
    usage_scene: int | None
    wallet_available_credits: Decimal
    subscription_status: int | None
    priority_class: str
    max_concurrency: int

    def to_response_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "creator_bid": self.creator_bid,
            "shifu_bid": self.shifu_bid,
            "usage_scene": self.usage_scene,
            "wallet_available_credits": self.wallet_available_credits,
            "subscription_status": self.subscription_status,
            "priority_class": self.priority_class,
            "max_concurrency": self.max_concurrency,
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
        wallet_available_credits = sum(
            (_to_decimal(bucket.available_credits) for bucket in active_buckets),
            start=_ZERO_CREDITS,
        )
        if wallet_available_credits <= _ZERO_CREDITS and not active_buckets:
            raise_error("server.billing.creditInsufficient")

        has_active_subscription = (
            subscription is not None
            and subscription.status in _ADMISSION_ACTIVE_SUBSCRIPTION_STATUSES
        )
        has_non_subscription_credits = any(
            resolve_wallet_bucket_runtime_category(
                bucket,
                load_order_type=load_billing_order_type_by_bid,
            )
            != CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            for bucket in active_buckets
        )
        if not has_active_subscription and not has_non_subscription_credits:
            raise_error("server.billing.subscriptionInactive")

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
            max_concurrency=int(entitlement_state.max_concurrency),
        )


def reserve_creator_runtime_slot(
    app: Flask,
    *,
    admission_payload: CreatorUsageAdmission,
) -> CreatorRuntimeAdmissionLease:
    """Reserve one creator-scoped runtime slot for an admitted request."""

    creator_bid = _resolve_required_bid(admission_payload.creator_bid)
    max_concurrency = _resolve_positive_int(admission_payload.max_concurrency)
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu") or "ai-shifu")
    counter_key = f"{prefix}{_RUNTIME_CONCURRENCY_KEY_SUFFIX}{creator_bid}"
    lock_key = f"{prefix}{_RUNTIME_CONCURRENCY_LOCK_KEY_SUFFIX}{creator_bid}"

    active_runtime_count = _increment_runtime_concurrency(
        app,
        counter_key=counter_key,
        lock_key=lock_key,
        max_concurrency=max_concurrency,
    )
    return CreatorRuntimeAdmissionLease(
        app=app,
        creator_bid=creator_bid,
        counter_key=counter_key,
        lock_key=lock_key,
        active_runtime_count=active_runtime_count,
    )


def _resolve_creator_bid(app: Flask, *, creator_bid: str, shifu_bid: str) -> str:
    normalized_creator_bid = str(creator_bid or "").strip()
    if normalized_creator_bid:
        return normalized_creator_bid
    return str(resolve_shifu_creator_bid(app, shifu_bid) or "").strip()


def _resolve_required_bid(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise_error("server.shifu.shifuNotFound")
    return normalized


def _resolve_positive_int(value: Any) -> int:
    try:
        return max(int(value or 1), 1)
    except (TypeError, ValueError):
        return 1


def _increment_runtime_concurrency(
    app: Flask,
    *,
    counter_key: str,
    lock_key: str,
    max_concurrency: int,
) -> int:
    with _runtime_concurrency_lock(lock_key):
        current = _read_runtime_concurrency(counter_key)
        if current >= max_concurrency:
            raise_error("server.billing.concurrencyExceeded")
        next_count = current + 1
        cache_provider.set(
            counter_key,
            next_count,
            ex=_RUNTIME_CONCURRENCY_SLOT_TTL_SECONDS,
        )
        app.logger.info(
            "billing runtime slot reserved key=%s active=%s max=%s",
            counter_key,
            next_count,
            max_concurrency,
        )
        return next_count


def _decrement_runtime_concurrency(
    app: Flask,
    *,
    counter_key: str,
    lock_key: str,
) -> None:
    with _runtime_concurrency_lock(lock_key):
        current = _read_runtime_concurrency(counter_key)
        if current <= 1:
            cache_provider.delete(counter_key)
            app.logger.info("billing runtime slots cleared key=%s", counter_key)
            return
        next_count = current - 1
        cache_provider.set(
            counter_key,
            next_count,
            ex=_RUNTIME_CONCURRENCY_SLOT_TTL_SECONDS,
        )
        app.logger.info(
            "billing runtime slot released key=%s active=%s",
            counter_key,
            next_count,
        )


def _read_runtime_concurrency(counter_key: str) -> int:
    raw_value = cache_provider.get(counter_key)
    if raw_value in (None, b"", ""):
        return 0
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8", errors="ignore")
    try:
        return max(int(raw_value), 0)
    except (TypeError, ValueError):
        return 0


class _RuntimeConcurrencyLock:
    def __init__(self, lock) -> None:
        self._lock = lock
        self._acquired = False

    def __enter__(self) -> "_RuntimeConcurrencyLock":
        if self._lock is None:
            raise_error("server.billing.concurrencyExceeded")
        self._acquired = bool(
            self._lock.acquire(
                blocking=True,
                blocking_timeout=_RUNTIME_CONCURRENCY_LOCK_TIMEOUT_SECONDS,
            )
        )
        if not self._acquired:
            raise_error("server.billing.concurrencyExceeded")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._acquired:
            self._lock.release()
            self._acquired = False


def _runtime_concurrency_lock(lock_key: str) -> _RuntimeConcurrencyLock:
    return _RuntimeConcurrencyLock(
        cache_provider.lock(
            lock_key,
            timeout=_RUNTIME_CONCURRENCY_LOCK_TIMEOUT_SECONDS,
            blocking_timeout=_RUNTIME_CONCURRENCY_LOCK_TIMEOUT_SECONDS,
        )
    )

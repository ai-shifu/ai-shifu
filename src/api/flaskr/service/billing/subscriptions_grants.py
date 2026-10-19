"""Credit grants for paid billing orders, including campaign bonuses."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.util.uuid import generate_id

from .bucket_categories import (
    resolve_bucket_category_from_order_type,
    resolve_credit_bucket_priority,
)
from .consts import (
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_CANCELED,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .cycle_state_transitions import (
    realign_active_credit_bucket_effective_to as _realign_active_credit_bucket_effective_to,
)
from .cycle_state_transitions import (
    resolve_effective_subscription_cycle_window as _resolve_effective_subscription_cycle_window,
)
from .models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .queries import (
    load_subscription_by_bid as _load_subscription_by_bid,
)
from .reserved_renewal_activation import (
    IncompleteReservedGrantActivationError,  # noqa: F401
    validate_reserved_renewal_cycle_activation,  # noqa: F401
)
from .subscriptions_activation import (
    _activate_subscription_for_paid_order,
    _expire_credit_bucket_balance_for_transition,
)
from .subscriptions_cycles import (
    _ensure_manual_renewal_applied_cycle,
    _is_same_product_preorder_renewal,
    _is_stale_manual_cycle,
    _load_billing_product_by_bid,
    _load_or_create_credit_wallet,
    _resolve_credit_bucket_effective_from,
    _resolve_credit_bucket_effective_to,
    _should_reserve_subscription_renewal_grant,
)
from .subscriptions_reserved import (
    _absorb_preorder_replaced_by_paid_upgrade,
    _load_preorder_replaced_by_paid_upgrade,
)
from .wallets import (
    load_or_create_credit_bucket_by_category,
    refresh_credit_wallet_snapshot,
    resolve_bucket_source_type_for_category,
    sync_credit_bucket_status,
)

if TYPE_CHECKING:
    from datetime import datetime
    from types import ModuleType

    from flask import Flask


def _subscriptions_facade() -> ModuleType:
    """Resolve collaborators through ``subscriptions`` so its patch points stay live."""
    from . import subscriptions

    return subscriptions


@dataclass(slots=True, frozen=True)
class CreditGrantContext:
    """Carry context for credit grant."""

    source_type: int
    bucket_category: int
    priority: int
    grant_reason: str


def _repair_existing_paid_order_grant_bucket(
    app: Flask,
    *,
    order: BillingOrder,
    grant_entry: CreditLedgerEntry,
) -> bool:
    """Repair the mutable bucket snapshot for an already-granted paid order."""
    if _normalize_bid(grant_entry.source_bid) != _normalize_bid(order.bill_order_bid):
        return False

    bucket = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid == order.creator_bid,
            CreditWalletBucket.wallet_bucket_bid == grant_entry.wallet_bucket_bid,
        )
        .order_by(CreditWalletBucket.id.desc())
        .first()
    )
    if bucket is None:
        return False

    normalized_order_bid = _normalize_bid(order.bill_order_bid)
    bucket_source_bid = _normalize_bid(bucket.source_bid)
    is_topup_bucket = int(bucket.bucket_category or 0) == CREDIT_BUCKET_CATEGORY_TOPUP
    is_shared_topup_replay = (
        is_topup_bucket
        and bucket_source_bid
        and bucket_source_bid != normalized_order_bid
    )
    if (
        bucket_source_bid
        and bucket_source_bid != normalized_order_bid
        and not is_topup_bucket
    ):
        return False

    effective_to = grant_entry.expires_at
    now = _subscriptions_facade().now_utc()
    if (
        effective_to is not None
        and effective_to <= now
        and _to_decimal(bucket.available_credits) <= 0
        and _to_decimal(bucket.reserved_credits) <= 0
    ):
        return False

    changed = False
    effective_from = grant_entry.consumable_from
    metadata = _normalize_json_object(grant_entry.metadata_json)
    is_reserved_grant = (
        str(metadata.get("bucket_credit_state") or "").strip().lower() == "reserved"
    )
    if is_topup_bucket and not is_reserved_grant:
        bucket_ledgers = (
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.creator_bid == order.creator_bid,
                CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )
        grant_total = sum(
            (
                _to_decimal(row.amount)
                for row in bucket_ledgers
                if int(row.entry_type or 0) == CREDIT_LEDGER_ENTRY_TYPE_GRANT
            ),
            start=Decimal(0),
        )
        net_available = sum(
            (_to_decimal(row.amount) for row in bucket_ledgers),
            start=Decimal(0),
        )
        if grant_total > _to_decimal(bucket.original_credits):
            bucket.original_credits = _quantize_credit_amount(grant_total)
            changed = True
        if net_available > _to_decimal(bucket.available_credits):
            bucket.available_credits = _quantize_credit_amount(net_available)
            changed = True
    if is_reserved_grant:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        has_current_available_balance = _to_decimal(bucket.available_credits) > 0
        current_cycle_window = _resolve_effective_subscription_cycle_window(
            subscription,
            as_of=now,
        )
        if has_current_available_balance and current_cycle_window is not None:
            if bucket.effective_from is None or bucket.effective_from > now:
                bucket.effective_from = current_cycle_window.start_at
                changed = True
            if (
                bucket.effective_to is None
                or bucket.effective_to > current_cycle_window.end_at
            ):
                bucket.effective_to = current_cycle_window.end_at
                changed = True
    elif not is_shared_topup_replay:
        if effective_from is not None and bucket.effective_from != effective_from:
            bucket.effective_from = effective_from
            changed = True
        if bucket.effective_to != effective_to:
            bucket.effective_to = effective_to
            changed = True
    if bucket.source_bid != order.bill_order_bid and (
        not is_topup_bucket or not bucket_source_bid
    ):
        bucket.source_bid = order.bill_order_bid
        changed = True

    previous_status = int(bucket.status or 0)
    can_reuse_preserved_status = previous_status == CREDIT_BUCKET_STATUS_EXPIRED or (
        previous_status == CREDIT_BUCKET_STATUS_CANCELED and is_topup_bucket
    )
    if can_reuse_preserved_status and (
        _to_decimal(bucket.available_credits) > 0
        or _to_decimal(bucket.reserved_credits) > 0
    ):
        _prepare_bucket_for_runtime_reuse(bucket)
        changed = True

    sync_credit_bucket_status(bucket)
    if int(bucket.status or 0) != previous_status:
        changed = True

    if not changed:
        return False

    bucket.updated_at = now
    db.session.add(bucket)

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    refresh_credit_wallet_snapshot(
        wallet,
        snapshot_at=now if is_reserved_grant else effective_from or now,
    )
    _subscriptions_facade().persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        updated_at=now,
    )
    return True


def _prepare_bucket_for_runtime_reuse(bucket: CreditWalletBucket) -> None:
    """Allow an explicitly re-funded bucket to re-enter runtime status sync."""
    current_status = int(bucket.status or 0)
    if current_status == CREDIT_BUCKET_STATUS_EXPIRED or (
        current_status == CREDIT_BUCKET_STATUS_CANCELED
        and int(bucket.bucket_category or 0) == CREDIT_BUCKET_CATEGORY_TOPUP
    ):
        bucket.status = CREDIT_BUCKET_STATUS_EXHAUSTED


def _build_bucket_metadata_from_order(order: BillingOrder) -> dict[str, object]:
    return _normalize_json_object(
        {
            "bill_order_bid": order.bill_order_bid,
            "subscription_bid": order.subscription_bid or None,
            "product_bid": order.product_bid,
            "payment_provider": order.payment_provider,
        }
    ).to_metadata_json()


def _upsert_paid_order_credit_bucket(
    app: Flask,
    *,
    wallet: CreditWallet,
    order: BillingOrder,
    grant_context: CreditGrantContext,
    amount: Decimal,
    effective_from: datetime,
    effective_to: datetime | None,
) -> tuple[CreditWalletBucket, bool]:
    bucket = load_or_create_credit_bucket_by_category(
        app,
        wallet=wallet,
        creator_bid=order.creator_bid,
        bucket_category=grant_context.bucket_category,
        source_bid=order.bill_order_bid,
        metadata=_build_bucket_metadata_from_order(order),
        effective_from=effective_from,
        effective_to=effective_to,
    )
    now = _subscriptions_facade().now_utc()
    current_available = _to_decimal(bucket.available_credits)
    current_reserved = _to_decimal(bucket.reserved_credits)

    bucket.wallet_bid = wallet.wallet_bid
    bucket.bucket_category = grant_context.bucket_category
    bucket.source_type = resolve_bucket_source_type_for_category(
        grant_context.bucket_category
    )
    bucket.source_bid = order.bill_order_bid
    bucket.priority = grant_context.priority
    bucket.original_credits = _quantize_credit_amount(
        _to_decimal(bucket.original_credits) + amount
    )
    bucket.metadata_json = {
        **(bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}),
        **_build_bucket_metadata_from_order(order),
    }

    reserve_grant = False
    if grant_context.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP:
        bucket.available_credits = _quantize_credit_amount(current_available + amount)
        bucket.reserved_credits = _quantize_credit_amount(current_reserved)
        if current_available > 0 or current_reserved > 0:
            if bucket.effective_from is None or bucket.effective_from > effective_from:
                bucket.effective_from = effective_from
        else:
            bucket.effective_from = effective_from
        bucket.effective_to = effective_to
    else:
        reserve_grant = _should_reserve_subscription_renewal_grant(
            order,
            effective_from=effective_from,
        )
        if reserve_grant:
            bucket.reserved_credits = _quantize_credit_amount(current_reserved + amount)
            if bucket.effective_from is None:
                bucket.effective_from = effective_from
            if bucket.effective_to is None:
                bucket.effective_to = effective_to
        else:
            same_product_preorder_renewal = _is_same_product_preorder_renewal(order)
            if (
                order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
                and not same_product_preorder_renewal
            ):
                _expire_credit_bucket_balance_for_transition(
                    app,
                    wallet=wallet,
                    bucket=bucket,
                    order=order,
                    transition_at=effective_from,
                )
            bucket.available_credits = _quantize_credit_amount(
                _to_decimal(bucket.available_credits) + amount
            )
            bucket.reserved_credits = _quantize_credit_amount(
                _to_decimal(bucket.reserved_credits)
            )
            if same_product_preorder_renewal:
                if (
                    bucket.effective_from is None
                    or bucket.effective_from > effective_from
                ):
                    bucket.effective_from = effective_from
            else:
                bucket.effective_from = effective_from
            bucket.effective_to = effective_to

    bucket.updated_at = now
    _prepare_bucket_for_runtime_reuse(bucket)
    sync_credit_bucket_status(bucket)
    db.session.add(bucket)
    return bucket, reserve_grant


def _grant_paid_order_credits(app: Flask, order: BillingOrder) -> bool:
    grant_context = _resolve_credit_grant_context(order)
    if grant_context is None:
        return False

    product = _load_billing_product_by_bid(order.product_bid)
    if product is None:
        return False
    _ensure_manual_renewal_applied_cycle(order, product)

    amount = _quantize_credit_amount(product.credit_amount)
    if amount <= 0:
        return False

    if _paid_order_grant_needs_review(order):
        return False
    _absorb_preorder_replaced_by_paid_upgrade(app, order)

    effective_from = _resolve_credit_bucket_effective_from(
        order=order,
        default_effective_from=order.paid_at or _subscriptions_facade().now_utc(),
    )
    effective_to = _resolve_credit_bucket_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
    )

    idempotency_key = f"grant:{order.bill_order_bid}"
    existing_entry = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if existing_entry is not None:
        _activate_subscription_for_paid_order(app, order)
        _repair_existing_paid_order_grant_bucket(
            app,
            order=order,
            grant_entry=existing_entry,
        )
        _grant_paid_campaign_bonus_credits(
            app,
            order=order,
            product=product,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        return False

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)

    bucket, reserve_grant = _upsert_paid_order_credit_bucket(
        app,
        wallet=wallet,
        order=order,
        grant_context=grant_context,
        amount=amount,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    if (
        grant_context.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
        and order.order_type
        in {
            BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
        }
    ):
        _realign_active_credit_bucket_effective_to(
            creator_bid=order.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            effective_from=effective_from,
            effective_to=effective_to,
            include_effective_to_boundary=False,
        )

    _activate_subscription_for_paid_order(app, order)

    _record_paid_order_grant_ledger_entry(
        app,
        order=order,
        wallet=wallet,
        bucket=bucket,
        grant_context=grant_context,
        amount=amount,
        effective_from=effective_from,
        effective_to=effective_to,
        reserve_grant=reserve_grant,
        idempotency_key=idempotency_key,
    )

    _grant_paid_campaign_bonus_credits(
        app,
        order=order,
        product=product,
        effective_from=effective_from,
        effective_to=effective_to,
    )

    return True


def _paid_order_grant_needs_review(order: BillingOrder) -> bool:
    """Flag stale manual cycles and lost preorder offsets for settlement review."""
    # Serialize activation against upgrades and cycle-boundary workers.
    subscription = None
    if order.subscription_bid:
        subscription = (
            BillingSubscription.query.filter_by(
                subscription_bid=order.subscription_bid,
                deleted=0,
            )
            .populate_existing()
            .with_for_update()
            .first()
        )
    if subscription is not None and subscription.current_period_start_at is not None:
        effective_from = _resolve_credit_bucket_effective_from(
            order=order,
            default_effective_from=order.paid_at or _subscriptions_facade().now_utc(),
        )
        if _is_stale_manual_cycle(order, subscription, effective_from):
            metadata = (
                dict(order.metadata_json)
                if isinstance(order.metadata_json, dict)
                else {}
            )
            metadata["settlement_review_reason"] = "newer_cycle_already_effective"
            order.metadata_json = metadata
            db.session.add(order)
            return True
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    if (
        order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
        and int(metadata.get("prepaid_offset_amount") or 0) > 0
    ):
        preorder = _load_preorder_replaced_by_paid_upgrade(order)
        if (
            preorder is None
            or preorder.currency != order.currency
            or int(preorder.paid_amount or 0)
            != int(metadata.get("prepaid_offset_amount") or 0)
        ):
            order.metadata_json = {
                **metadata,
                "settlement_review_reason": "preorder_offset_no_longer_available",
            }
            db.session.add(order)
            return True
    return False


def _record_paid_order_grant_ledger_entry(
    app: Flask,
    *,
    order: BillingOrder,
    wallet: CreditWallet,
    bucket: CreditWalletBucket,
    grant_context: CreditGrantContext,
    amount: Decimal,
    effective_from: datetime,
    effective_to: datetime | None,
    reserve_grant: bool,
    idempotency_key: str,
) -> None:
    """Refresh the wallet, stage the grant ledger entry, and persist the snapshot."""
    snapshot_at = _subscriptions_facade().now_utc() if reserve_grant else effective_from
    refresh_credit_wallet_snapshot(wallet, snapshot_at=snapshot_at)
    balance_after = _quantize_credit_amount(wallet.available_credits)
    next_lifetime_granted = _quantize_credit_amount(
        _to_decimal(wallet.lifetime_granted_credits) + amount
    )
    ledger_entry = CreditLedgerEntry(
        ledger_bid=generate_id(app),
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=grant_context.source_type,
        source_bid=order.bill_order_bid,
        idempotency_key=idempotency_key,
        amount=amount,
        balance_after=balance_after,
        expires_at=effective_to,
        consumable_from=effective_from,
        metadata_json=_normalize_json_object(
            {
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": order.subscription_bid or None,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": grant_context.grant_reason,
                "grant_credit_amount": str(amount),
                "bucket_credit_state": "reserved" if reserve_grant else "available",
                "reserved_until": (
                    effective_from.isoformat() if reserve_grant else None
                ),
            }
        ).to_metadata_json(),
    )

    wallet.available_credits = balance_after
    _subscriptions_facade().persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        lifetime_granted_credits=next_lifetime_granted,
        updated_at=_subscriptions_facade().now_utc(),
    )
    db.session.add(ledger_entry)


def _grant_paid_campaign_bonus_credits(
    app: Flask,
    *,
    order: BillingOrder,
    product: BillingProduct,
    effective_from: datetime,
    effective_to: datetime | None = None,
) -> bool:
    bonus_amount = _quantize_credit_amount(order.campaign_bonus_credit_amount)
    if not _normalize_bid(order.campaign_bid) or bonus_amount <= 0:
        return False

    idempotency_key = f"grant:campaign_bonus:{order.bill_order_bid}"
    existing_entry = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if existing_entry is not None:
        return False

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    resolved_effective_to = effective_to or _resolve_credit_bucket_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
    )
    bucket_category = resolve_bucket_category_from_order_type(
        int(order.order_type or 0)
    )
    if bucket_category not in {
        CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        CREDIT_BUCKET_CATEGORY_TOPUP,
    }:
        return False
    reserve_grant = (
        bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
        and _should_reserve_subscription_renewal_grant(
            order,
            effective_from=effective_from,
        )
    )

    bucket = CreditWalletBucket(
        wallet_bucket_bid=generate_id(app),
        wallet_bid=wallet.wallet_bid,
        creator_bid=order.creator_bid,
        bucket_category=bucket_category,
        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
        source_bid=order.bill_order_bid,
        priority=resolve_credit_bucket_priority(bucket_category),
        original_credits=bonus_amount,
        available_credits=_to_decimal(0) if reserve_grant else bonus_amount,
        reserved_credits=bonus_amount if reserve_grant else _to_decimal(0),
        consumed_credits=_to_decimal(0),
        expired_credits=_to_decimal(0),
        effective_from=effective_from,
        effective_to=resolved_effective_to,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json=_normalize_json_object(
            {
                **_build_bucket_metadata_from_order(order),
                "campaign_bid": order.campaign_bid,
                "campaign_bonus_credit_amount": bonus_amount,
                "grant_reason": "campaign_bonus",
                "bucket_credit_state": "reserved" if reserve_grant else "available",
                "reserved_until": (
                    effective_from.isoformat() if reserve_grant else None
                ),
            }
        ).to_metadata_json(),
    )
    db.session.add(bucket)
    sync_credit_bucket_status(bucket)
    refresh_credit_wallet_snapshot(wallet, snapshot_at=effective_from)
    balance_after = _quantize_credit_amount(wallet.available_credits)
    next_lifetime_granted = _quantize_credit_amount(
        _to_decimal(wallet.lifetime_granted_credits) + bonus_amount
    )
    ledger_entry = CreditLedgerEntry(
        ledger_bid=generate_id(app),
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
        source_bid=order.bill_order_bid,
        idempotency_key=idempotency_key,
        amount=bonus_amount,
        balance_after=balance_after,
        expires_at=resolved_effective_to,
        consumable_from=effective_from,
        metadata_json=_normalize_json_object(
            {
                "bill_order_bid": order.bill_order_bid,
                "product_bid": order.product_bid,
                "campaign_bid": order.campaign_bid,
                "grant_reason": "campaign_bonus",
                "bonus_credit_amount": bonus_amount,
                "bucket_credit_state": "reserved" if reserve_grant else "available",
                "reserved_until": (
                    effective_from.isoformat() if reserve_grant else None
                ),
            }
        ).to_metadata_json(),
    )
    wallet.available_credits = balance_after
    _subscriptions_facade().persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        lifetime_granted_credits=next_lifetime_granted,
        updated_at=_subscriptions_facade().now_utc(),
    )
    db.session.add(ledger_entry)
    return True


def _resolve_credit_grant_context(order: BillingOrder) -> CreditGrantContext | None:
    bucket_category = resolve_bucket_category_from_order_type(
        int(order.order_type or 0)
    )
    if bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION:
        return CreditGrantContext(
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            priority=resolve_credit_bucket_priority(
                CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            ),
            grant_reason="subscription",
        )
    if bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP:
        return CreditGrantContext(
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            priority=resolve_credit_bucket_priority(CREDIT_BUCKET_CATEGORY_TOPUP),
            grant_reason="topup",
        )
    return None

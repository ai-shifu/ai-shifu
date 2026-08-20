"""Reserved renewal grant activation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from flaskr.dao import db
from flaskr.util.datetime import NAIVE_DATETIME_MIN, now_utc

from .bucket_categories import resolve_credit_bucket_priority
from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
)
from .credit_mutations import (
    activate_reserved_grant_credit,
)
from .credit_mutations import (
    reserved_grant_state as _reserved_grant_state,
)
from .cycle_transitions import (
    resolve_order_effective_from as _resolve_order_effective_from,
)
from .models import (
    BillingOrder,
    BillingProduct,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .queries import (
    extract_resolved_order_cycle_start_at as _extract_resolved_order_cycle_start_at,
)
from .queries import (
    load_subscription_by_bid as _load_subscription_by_bid,
)
from .wallets import (
    _load_or_create_credit_wallet,
    load_primary_credit_bucket_by_category,
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    resolve_bucket_source_type_for_category,
)

if TYPE_CHECKING:
    from flask import Flask


class ExpireBucketBalanceForTransition(Protocol):
    def __call__(
        self,
        app: Flask,
        *,
        wallet: CreditWallet,
        bucket: CreditWalletBucket,
        order: BillingOrder,
        transition_at: datetime,
    ) -> Decimal: ...


class IncompleteReservedGrantActivationError(RuntimeError):
    """Raised when a renewal cycle cannot activate every reserved grant atomically."""


@dataclass(slots=True, frozen=True)
class ReservedActivationTarget:
    kind: str
    order_bid: str
    ledger_bid: str
    wallet_bucket_bid: str
    amount: Decimal


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _datetime_sort_value(value: datetime | None) -> datetime:
    if value is None:
        return NAIVE_DATETIME_MIN
    return _normalize_utc_datetime(value)


def activate_reserved_renewal_grants_for_cycle(
    app: Flask,
    *,
    order: BillingOrder,
    effective_from: datetime,
    effective_to: datetime | None,
    expire_bucket_balance_for_transition: ExpireBucketBalanceForTransition,
) -> tuple[ReservedActivationTarget, ...]:
    cycle_orders = _load_sorted_paid_subscription_renewal_orders_for_cycle(
        order=order,
        effective_from=effective_from,
    )

    attribution_order_bid = next(
        (
            row.bill_order_bid
            for row in cycle_orders
            if int(row.paid_amount or 0) > 0 or int(row.payable_amount or 0) > 0
        ),
        order.bill_order_bid,
    )

    if not _cycle_has_reserved_activation_evidence(cycle_orders):
        return ()

    targets = _preflight_reserved_renewal_grants_for_cycle(cycle_orders)
    with db.session.begin_nested():
        for cycle_order in cycle_orders:
            _activate_reserved_subscription_grant_for_order(
                app,
                order=cycle_order,
                effective_from=effective_from,
                effective_to=effective_to,
                attribution_order_bid=attribution_order_bid,
                expire_bucket_balance_for_transition=expire_bucket_balance_for_transition,
            )
            _activate_reserved_campaign_bonus_grant_for_order(
                app,
                order=cycle_order,
                effective_from=effective_from,
                effective_to=effective_to,
            )
        _assert_reserved_activation_targets_completed(cycle_orders)
    return targets


def validate_reserved_renewal_cycle_activation(
    order: BillingOrder,
    *,
    effective_from: datetime | None = None,
) -> tuple[ReservedActivationTarget, ...]:
    """Validate a renewal cycle can activate every reserved grant atomically."""
    resolved_effective_from = effective_from or _resolve_order_effective_from(
        order=order,
        default_effective_from=order.paid_at or now_utc(),
        load_subscription_by_bid=_load_subscription_by_bid,
    )
    cycle_orders = _load_sorted_paid_subscription_renewal_orders_for_cycle(
        order=order,
        effective_from=resolved_effective_from,
    )
    return _preflight_reserved_renewal_grants_for_cycle(cycle_orders)


def sync_activated_reserved_renewal_ledger_balances(
    *,
    targets: tuple[ReservedActivationTarget, ...],
    final_balance_after: Decimal,
) -> None:
    if not targets:
        return

    total_activated = sum((target.amount for target in targets), start=Decimal(0))
    running_balance = _quantize_credit_amount(final_balance_after - total_activated)
    now = now_utc()
    for target in targets:
        grant_entry = (
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.ledger_bid == target.ledger_bid,
            )
            .order_by(CreditLedgerEntry.id.desc())
            .first()
        )
        if grant_entry is None or _reserved_grant_state(grant_entry) != "available":
            raise IncompleteReservedGrantActivationError(
                f"incomplete_{target.kind}_activation:{target.order_bid}"
            )
        running_balance = _quantize_credit_amount(running_balance + target.amount)
        grant_entry.balance_after = running_balance
        grant_entry.updated_at = now
        db.session.add(grant_entry)


def load_grant_ledger_entry_for_order(order: BillingOrder) -> CreditLedgerEntry | None:
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key == f"grant:{order.bill_order_bid}",
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )


def load_campaign_bonus_ledger_entry_for_order(
    order: BillingOrder,
) -> CreditLedgerEntry | None:
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key
            == f"grant:campaign_bonus:{order.bill_order_bid}",
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )


def _load_paid_subscription_renewal_orders_for_cycle(
    *,
    subscription_bid: str,
    effective_from: datetime,
) -> tuple[BillingOrder, ...]:
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    if not normalized_subscription_bid:
        return ()

    rows = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.subscription_bid == normalized_subscription_bid,
            BillingOrder.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
        )
        .order_by(BillingOrder.created_at.asc(), BillingOrder.id.asc())
        .all()
    )
    normalized_effective_from = _normalize_utc_datetime(effective_from)
    due_orders: list[BillingOrder] = []
    for row in rows:
        cycle_start_at = _extract_resolved_order_cycle_start_at(row.metadata_json)
        if (
            cycle_start_at is None
            or _normalize_utc_datetime(cycle_start_at) != normalized_effective_from
        ):
            continue
        due_orders.append(row)
    return tuple(due_orders)


def _load_sorted_paid_subscription_renewal_orders_for_cycle(
    *,
    order: BillingOrder,
    effective_from: datetime,
) -> list[BillingOrder]:
    cycle_orders = list(
        _load_paid_subscription_renewal_orders_for_cycle(
            subscription_bid=order.subscription_bid,
            effective_from=effective_from,
        )
    )
    if not cycle_orders:
        cycle_orders = [order]
    else:
        cycle_orders.sort(
            key=lambda row: (
                0
                if int(row.paid_amount or 0) > 0 or int(row.payable_amount or 0) > 0
                else 1,
                _datetime_sort_value(row.paid_at or row.created_at),
                _datetime_sort_value(row.created_at),
                row.id,
            )
        )
    return cycle_orders


def _cycle_has_reserved_activation_evidence(cycle_orders: list[BillingOrder]) -> bool:
    for cycle_order in cycle_orders:
        for grant_entry in (
            load_grant_ledger_entry_for_order(cycle_order),
            load_campaign_bonus_ledger_entry_for_order(cycle_order),
        ):
            if (
                grant_entry is not None
                and _reserved_grant_state(grant_entry) != "available"
            ):
                return True
    return False


def _build_bucket_metadata_from_order(order: BillingOrder) -> dict[str, object]:
    return _normalize_json_object(
        {
            "bill_order_bid": order.bill_order_bid,
            "subscription_bid": order.subscription_bid or None,
            "product_bid": order.product_bid,
            "payment_provider": order.payment_provider,
        }
    ).to_metadata_json()


def _load_reserved_activation_bucket(
    order: BillingOrder,
    grant_entry: CreditLedgerEntry,
    *,
    fallback_bucket_category: int | None = None,
) -> CreditWalletBucket | None:
    bucket = None
    if _normalize_bid(grant_entry.wallet_bucket_bid):
        bucket = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.wallet_bucket_bid == grant_entry.wallet_bucket_bid,
            )
            .order_by(CreditWalletBucket.id.desc())
            .first()
        )
    if bucket is None and fallback_bucket_category is not None:
        bucket = load_primary_credit_bucket_by_category(
            order.creator_bid,
            bucket_category=fallback_bucket_category,
        )
    return bucket


def _expected_subscription_grant_amount(order: BillingOrder) -> Decimal:
    grant_entry = load_grant_ledger_entry_for_order(order)
    if grant_entry is not None:
        metadata = _normalize_json_object(grant_entry.metadata_json)
        for key in ("grant_credit_amount", "credit_amount"):
            if metadata.get(key) is not None:
                amount = _quantize_credit_amount(_to_decimal(metadata.get(key)))
                if amount > 0:
                    return amount
    return Decimal(0)


def _expected_subscription_cycle_grant_amount(order: BillingOrder) -> Decimal:
    product = _load_billing_product_by_bid(order.product_bid)
    if product is None:
        raise IncompleteReservedGrantActivationError(
            f"missing_subscription_product:{order.bill_order_bid}"
        )
    return _quantize_credit_amount(_to_decimal(product.credit_amount))


def _expected_campaign_bonus_grant_amount(order: BillingOrder) -> Decimal:
    if not _normalize_bid(order.campaign_bid):
        return Decimal(0)
    return _quantize_credit_amount(_to_decimal(order.campaign_bonus_credit_amount))


def _build_reserved_activation_target(
    *,
    order: BillingOrder,
    grant_entry: CreditLedgerEntry | None,
    kind: str,
    expected_amount: Decimal,
    fallback_bucket_category: int | None = None,
) -> ReservedActivationTarget | None:
    if kind != "subscription" and expected_amount <= 0:
        return None
    if grant_entry is None:
        raise IncompleteReservedGrantActivationError(
            f"missing_{kind}_ledger:{order.bill_order_bid}"
        )

    state = _reserved_grant_state(grant_entry)
    if state == "available":
        return None
    if state != "reserved":
        raise IncompleteReservedGrantActivationError(
            f"invalid_{kind}_state:{order.bill_order_bid}:{state or 'missing'}"
        )

    amount = _quantize_credit_amount(_to_decimal(grant_entry.amount))
    if expected_amount > 0 and amount != expected_amount:
        raise IncompleteReservedGrantActivationError(
            f"{kind}_amount_mismatch:{order.bill_order_bid}"
        )
    if amount <= 0:
        raise IncompleteReservedGrantActivationError(
            f"invalid_{kind}_amount:{order.bill_order_bid}"
        )

    bucket = _load_reserved_activation_bucket(
        order,
        grant_entry,
        fallback_bucket_category=fallback_bucket_category,
    )
    if bucket is None:
        raise IncompleteReservedGrantActivationError(
            f"missing_{kind}_bucket:{order.bill_order_bid}"
        )
    if _quantize_credit_amount(_to_decimal(bucket.reserved_credits)) < amount:
        raise IncompleteReservedGrantActivationError(
            f"insufficient_{kind}_reserved:{order.bill_order_bid}"
        )

    return ReservedActivationTarget(
        kind=kind,
        order_bid=order.bill_order_bid,
        ledger_bid=grant_entry.ledger_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        amount=amount,
    )


def _build_reserved_completion_target(
    *,
    order: BillingOrder,
    grant_entry: CreditLedgerEntry | None,
    kind: str,
    expected_amount: Decimal,
    fallback_bucket_category: int | None = None,
) -> ReservedActivationTarget | None:
    if kind != "subscription" and expected_amount <= 0:
        return None
    if grant_entry is None:
        raise IncompleteReservedGrantActivationError(
            f"missing_{kind}_ledger:{order.bill_order_bid}"
        )
    state = _reserved_grant_state(grant_entry)
    if state != "available":
        raise IncompleteReservedGrantActivationError(
            f"incomplete_{kind}_activation:{order.bill_order_bid}"
        )
    amount = _quantize_credit_amount(_to_decimal(grant_entry.amount))
    if expected_amount > 0 and amount != expected_amount:
        raise IncompleteReservedGrantActivationError(
            f"{kind}_amount_mismatch:{order.bill_order_bid}"
        )
    bucket = _load_reserved_activation_bucket(
        order,
        grant_entry,
        fallback_bucket_category=fallback_bucket_category,
    )
    if bucket is None:
        raise IncompleteReservedGrantActivationError(
            f"missing_{kind}_bucket:{order.bill_order_bid}"
        )
    if _quantize_credit_amount(_to_decimal(bucket.available_credits)) < amount:
        raise IncompleteReservedGrantActivationError(
            f"incomplete_{kind}_bucket:{order.bill_order_bid}"
        )
    return ReservedActivationTarget(
        kind=kind,
        order_bid=order.bill_order_bid,
        ledger_bid=grant_entry.ledger_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        amount=amount,
    )


def _load_reserved_activation_targets_for_cycle_order(
    order: BillingOrder,
) -> tuple[ReservedActivationTarget, ...]:
    targets: list[ReservedActivationTarget] = []
    subscription_target = _build_reserved_activation_target(
        order=order,
        grant_entry=load_grant_ledger_entry_for_order(order),
        kind="subscription",
        expected_amount=_expected_subscription_grant_amount(order),
        fallback_bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    )
    if subscription_target is not None:
        targets.append(subscription_target)
    campaign_target = _build_reserved_activation_target(
        order=order,
        grant_entry=load_campaign_bonus_ledger_entry_for_order(order),
        kind="campaign_bonus",
        expected_amount=_expected_campaign_bonus_grant_amount(order),
    )
    if campaign_target is not None:
        targets.append(campaign_target)
    return tuple(targets)


def _load_reserved_completion_targets_for_cycle_order(
    order: BillingOrder,
) -> tuple[ReservedActivationTarget, ...]:
    targets: list[ReservedActivationTarget] = []
    subscription_target = _build_reserved_completion_target(
        order=order,
        grant_entry=load_grant_ledger_entry_for_order(order),
        kind="subscription",
        expected_amount=_expected_subscription_grant_amount(order),
        fallback_bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    )
    if subscription_target is not None:
        targets.append(subscription_target)
    campaign_target = _build_reserved_completion_target(
        order=order,
        grant_entry=load_campaign_bonus_ledger_entry_for_order(order),
        kind="campaign_bonus",
        expected_amount=_expected_campaign_bonus_grant_amount(order),
    )
    if campaign_target is not None:
        targets.append(campaign_target)
    return tuple(targets)


def _preflight_reserved_renewal_grants_for_cycle(
    cycle_orders: list[BillingOrder],
) -> tuple[ReservedActivationTarget, ...]:
    targets: list[ReservedActivationTarget] = []
    required_reserved_by_bucket: dict[str, Decimal] = {}
    for cycle_order in cycle_orders:
        for target in _load_reserved_activation_targets_for_cycle_order(cycle_order):
            targets.append(target)
            required_reserved_by_bucket[target.wallet_bucket_bid] = (
                required_reserved_by_bucket.get(target.wallet_bucket_bid, Decimal(0))
                + target.amount
            )
    _assert_subscription_cycle_grant_amounts(cycle_orders, targets)

    for wallet_bucket_bid, required_reserved in required_reserved_by_bucket.items():
        bucket = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.wallet_bucket_bid == wallet_bucket_bid,
            )
            .order_by(CreditWalletBucket.id.desc())
            .first()
        )
        if bucket is None:
            raise IncompleteReservedGrantActivationError(
                f"missing_bucket:{wallet_bucket_bid}"
            )
        if _quantize_credit_amount(
            _to_decimal(bucket.reserved_credits)
        ) < _quantize_credit_amount(required_reserved):
            raise IncompleteReservedGrantActivationError(
                f"insufficient_reserved:{wallet_bucket_bid}"
            )
    return tuple(targets)


def _assert_reserved_activation_targets_completed(
    cycle_orders: list[BillingOrder],
) -> None:
    targets: list[ReservedActivationTarget] = []
    for cycle_order in cycle_orders:
        targets.extend(_load_reserved_completion_targets_for_cycle_order(cycle_order))
    _assert_subscription_cycle_grant_amounts(cycle_orders, targets)


def _assert_subscription_cycle_grant_amounts(
    cycle_orders: list[BillingOrder],
    targets: list[ReservedActivationTarget] | tuple[ReservedActivationTarget, ...],
) -> None:
    subscription_amount_by_product: dict[str, Decimal] = {}
    expected_subscription_amount_by_product: dict[str, Decimal] = {}
    orders_by_bid = {
        _normalize_bid(order.bill_order_bid): order for order in cycle_orders
    }
    orders_with_subscription_targets: set[str] = set()
    for target in targets:
        if target.kind != "subscription":
            continue
        order_bid = _normalize_bid(target.order_bid)
        order = orders_by_bid.get(order_bid)
        if order is None:
            continue
        orders_with_subscription_targets.add(order_bid)
        product_bid = _normalize_bid(order.product_bid)
        subscription_amount_by_product[product_bid] = (
            subscription_amount_by_product.get(product_bid, Decimal(0)) + target.amount
        )

    for order in cycle_orders:
        order_bid = _normalize_bid(order.bill_order_bid)
        if order_bid not in orders_with_subscription_targets:
            continue
        if _is_referral_invitation_renewal(order):
            continue
        product_bid = _normalize_bid(order.product_bid)
        expected_subscription_amount_by_product[product_bid] = (
            expected_subscription_amount_by_product.get(product_bid, Decimal(0))
            + _expected_subscription_cycle_grant_amount(order)
        )

    for product_bid, expected_amount in expected_subscription_amount_by_product.items():
        if _quantize_credit_amount(
            subscription_amount_by_product.get(product_bid, Decimal(0))
        ) < _quantize_credit_amount(expected_amount):
            raise IncompleteReservedGrantActivationError(
                f"subscription_cycle_amount_mismatch:{product_bid}"
            )


def _activate_reserved_subscription_grant_for_order(
    app: Flask,
    *,
    order: BillingOrder,
    effective_from: datetime,
    effective_to: datetime | None,
    attribution_order_bid: str | None = None,
    expire_bucket_balance_for_transition: ExpireBucketBalanceForTransition,
) -> bool:
    grant_entry = load_grant_ledger_entry_for_order(order)
    if grant_entry is None:
        return False

    metadata = _normalize_json_object(grant_entry.metadata_json)
    if str(metadata.get("bucket_credit_state") or "").strip().lower() != "reserved":
        return False

    bucket = None
    if _normalize_bid(grant_entry.wallet_bucket_bid):
        bucket = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.wallet_bucket_bid == grant_entry.wallet_bucket_bid,
            )
            .order_by(CreditWalletBucket.id.desc())
            .first()
        )
    if bucket is None:
        bucket = load_primary_credit_bucket_by_category(
            order.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        )
    if bucket is None:
        return False

    grant_amount = _quantize_credit_amount(_to_decimal(grant_entry.amount))
    reserved_credits = _quantize_credit_amount(_to_decimal(bucket.reserved_credits))
    if grant_amount <= 0 or reserved_credits < grant_amount:
        return False

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    normalized_effective_from = _normalize_utc_datetime(effective_from)
    bucket_effective_from = (
        _normalize_utc_datetime(bucket.effective_from)
        if bucket.effective_from is not None
        else None
    )
    is_first_cycle_activation = (
        bucket_effective_from is None
        or bucket_effective_from < normalized_effective_from
    )
    if is_first_cycle_activation:
        expire_bucket_balance_for_transition(
            app,
            wallet=wallet,
            bucket=bucket,
            order=order,
            transition_at=effective_from,
        )

    now = now_utc()
    bucket.wallet_bid = wallet.wallet_bid
    bucket.bucket_category = CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    bucket.source_type = resolve_bucket_source_type_for_category(
        CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    )
    if is_first_cycle_activation:
        bucket.source_bid = attribution_order_bid or order.bill_order_bid
    bucket.priority = resolve_credit_bucket_priority(
        CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    )
    if is_first_cycle_activation:
        bucket.metadata_json = {
            **(bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}),
            **_build_bucket_metadata_from_order(order),
            "bill_order_bid": attribution_order_bid or order.bill_order_bid,
        }

    mutation_result = activate_reserved_grant_credit(
        grant_entry=grant_entry,
        bucket=bucket,
        effective_from=effective_from,
        effective_to=effective_to,
        now=now,
    )
    if not mutation_result.completed:
        return False

    refresh_credit_wallet_snapshot(wallet, snapshot_at=effective_from)
    persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        updated_at=now,
    )
    grant_entry.balance_after = _quantize_credit_amount(wallet.available_credits)
    return True


def _activate_reserved_campaign_bonus_grant_for_order(
    app: Flask,
    *,
    order: BillingOrder,
    effective_from: datetime,
    effective_to: datetime | None,
) -> bool:
    grant_entry = load_campaign_bonus_ledger_entry_for_order(order)
    if grant_entry is None:
        return False

    metadata = _normalize_json_object(grant_entry.metadata_json)
    if str(metadata.get("bucket_credit_state") or "").strip().lower() != "reserved":
        return False
    if not _normalize_bid(grant_entry.wallet_bucket_bid):
        return False

    bucket = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.wallet_bucket_bid == grant_entry.wallet_bucket_bid,
        )
        .order_by(CreditWalletBucket.id.desc())
        .first()
    )
    if bucket is None:
        return False

    grant_amount = _quantize_credit_amount(_to_decimal(grant_entry.amount))
    reserved_credits = _quantize_credit_amount(_to_decimal(bucket.reserved_credits))
    if grant_amount <= 0 or reserved_credits < grant_amount:
        return False

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    now = now_utc()
    mutation_result = activate_reserved_grant_credit(
        grant_entry=grant_entry,
        bucket=bucket,
        effective_from=effective_from,
        effective_to=effective_to,
        now=now,
    )
    if not mutation_result.completed:
        return False

    refresh_credit_wallet_snapshot(wallet, snapshot_at=effective_from)
    persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        updated_at=now,
    )
    grant_entry.balance_after = _quantize_credit_amount(wallet.available_credits)
    return True


def _load_billing_product_by_bid(product_bid: str) -> BillingProduct | None:
    normalized_product_bid = _normalize_bid(product_bid)
    if not normalized_product_bid:
        return None
    return (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == normalized_product_bid,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )


def _is_referral_invitation_renewal(order: BillingOrder) -> bool:
    if order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        return False

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    checkout_type = str(metadata.get("checkout_type") or "").strip()
    return checkout_type == "referral_invitation_reward" or (
        metadata.get("referral_invitation_reward") is True
    )

"""Usage settlement helpers for creator billing."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.metering.consts import BILL_USAGE_TYPE_LLM, BILL_USAGE_TYPE_TTS
from flaskr.service.metering.models import BillUsageRecord
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_METRIC_LABELS,
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_INPUT_CHARS,
    BILLING_METRIC_TTS_OUTPUT_CHARS,
    BILLING_METRIC_TTS_REQUEST_COUNT,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_ROUNDING_MODE_FLOOR,
    CREDIT_ROUNDING_MODE_ROUND,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from .models import CreditLedgerEntry, CreditUsageRate, CreditWallet, CreditWalletBucket
from .ownership import resolve_usage_creator_bid

_ZERO = Decimal("0")
_DECIMAL_QUANT = Decimal("0.0000000001")
_ROUNDING_LABELS = {
    CREDIT_ROUNDING_MODE_CEIL: "ceil",
    CREDIT_ROUNDING_MODE_FLOOR: "floor",
    CREDIT_ROUNDING_MODE_ROUND: "round",
}


def settle_bill_usage(
    app: Flask,
    *,
    usage_bid: str = "",
    usage_id: int | None = None,
) -> dict[str, Any]:
    """Settle a single metering usage record into credit ledger consumption."""

    normalized_usage_bid = str(usage_bid or "").strip()
    with app.app_context():
        usage = _load_usage_record(usage_bid=normalized_usage_bid, usage_id=usage_id)
        if usage is None:
            return {
                "status": "not_found",
                "usage_bid": normalized_usage_bid or None,
                "usage_id": usage_id,
            }

        if int(usage.record_level or 0) != 0:
            return _build_skip_result(usage, reason="segment_record")
        if int(usage.billable or 0) != 1:
            return _build_skip_result(usage, reason="non_billable")
        if int(usage.status or 0) != 0:
            return _build_skip_result(usage, reason="usage_failed")

        creator_bid = str(resolve_usage_creator_bid(app, usage) or "").strip()
        if not creator_bid:
            return _build_skip_result(usage, reason="creator_not_found")

        existing_entries = (
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.creator_bid == creator_bid,
                CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_USAGE,
                CreditLedgerEntry.source_bid == usage.usage_bid,
            )
            .order_by(CreditLedgerEntry.id.desc())
            .all()
        )
        if existing_entries:
            return {
                "status": "already_settled",
                "usage_bid": usage.usage_bid,
                "creator_bid": creator_bid,
                "entry_count": len(existing_entries),
            }

        settlement_at = usage.created_at or datetime.now()
        metric_charges = _build_usage_metric_charges(usage, settlement_at=settlement_at)
        if not metric_charges:
            wallet = _load_credit_wallet(creator_bid)
            if wallet is not None:
                wallet.last_settled_usage_id = max(
                    int(wallet.last_settled_usage_id or 0), int(usage.id or 0)
                )
                wallet.updated_at = datetime.now()
                db.session.add(wallet)
                db.session.commit()
            return {
                "status": "noop",
                "usage_bid": usage.usage_bid,
                "creator_bid": creator_bid,
                "entry_count": 0,
                "consumed_credits": 0,
            }

        wallet = _load_credit_wallet(creator_bid)
        if wallet is None:
            return {
                "status": "insufficient",
                "usage_bid": usage.usage_bid,
                "creator_bid": creator_bid,
                "entry_count": 0,
                "consumed_credits": _decimal_to_number(
                    sum(
                        (
                            _to_decimal(item["consumed_credits"])
                            for item in metric_charges
                        ),
                        start=_ZERO,
                    )
                ),
            }

        buckets = _load_consumable_buckets(creator_bid, settlement_at=settlement_at)
        total_required = sum(
            (_to_decimal(item["consumed_credits"]) for item in metric_charges),
            start=_ZERO,
        )
        total_available = sum(
            (_to_decimal(bucket.available_credits) for bucket in buckets),
            start=_ZERO,
        )
        if total_required <= _ZERO:
            return {
                "status": "noop",
                "usage_bid": usage.usage_bid,
                "creator_bid": creator_bid,
                "entry_count": 0,
                "consumed_credits": 0,
            }
        if total_available < total_required:
            return {
                "status": "insufficient",
                "usage_bid": usage.usage_bid,
                "creator_bid": creator_bid,
                "entry_count": 0,
                "consumed_credits": _decimal_to_number(total_required),
            }

        balance_after = _to_decimal(wallet.available_credits)
        entry_count = 0
        total_consumed = _ZERO
        for charge in metric_charges:
            remaining = _to_decimal(charge["consumed_credits"])
            for bucket in buckets:
                bucket_available = _to_decimal(bucket.available_credits)
                if remaining <= _ZERO:
                    break
                if bucket_available <= _ZERO:
                    continue

                consumed = min(bucket_available, remaining)
                balance_after -= consumed
                remaining -= consumed
                total_consumed += consumed
                bucket.available_credits = bucket_available - consumed
                bucket.consumed_credits = (
                    _to_decimal(bucket.consumed_credits) + consumed
                )
                if _to_decimal(bucket.available_credits) <= _ZERO:
                    bucket.available_credits = _ZERO
                    bucket.status = CREDIT_BUCKET_STATUS_EXHAUSTED
                db.session.add(bucket)

                ledger_entry = CreditLedgerEntry(
                    ledger_bid=generate_id(app),
                    creator_bid=creator_bid,
                    wallet_bid=wallet.wallet_bid,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                    source_type=CREDIT_SOURCE_TYPE_USAGE,
                    source_bid=usage.usage_bid,
                    idempotency_key=(
                        f"usage:{usage.usage_bid}:{charge['billing_metric']}:"
                        f"{bucket.wallet_bucket_bid}:consume"
                    ),
                    amount=-consumed,
                    balance_after=balance_after,
                    expires_at=bucket.effective_to,
                    consumable_from=bucket.effective_from,
                    metadata_json=_build_usage_entry_metadata(
                        usage=usage,
                        charge=charge,
                        consumed=consumed,
                    ),
                )
                db.session.add(ledger_entry)
                entry_count += 1

            if remaining > _ZERO:
                db.session.rollback()
                return {
                    "status": "insufficient",
                    "usage_bid": usage.usage_bid,
                    "creator_bid": creator_bid,
                    "entry_count": 0,
                    "consumed_credits": _decimal_to_number(total_required),
                }

        wallet.available_credits = balance_after
        wallet.lifetime_consumed_credits = (
            _to_decimal(wallet.lifetime_consumed_credits) + total_consumed
        )
        wallet.last_settled_usage_id = max(
            int(wallet.last_settled_usage_id or 0), int(usage.id or 0)
        )
        wallet.version = int(wallet.version or 0) + 1
        wallet.updated_at = datetime.now()
        db.session.add(wallet)
        db.session.commit()
        return {
            "status": "settled",
            "usage_bid": usage.usage_bid,
            "creator_bid": creator_bid,
            "entry_count": entry_count,
            "consumed_credits": _decimal_to_number(total_consumed),
        }


def _load_usage_record(
    *, usage_bid: str, usage_id: int | None
) -> BillUsageRecord | None:
    query = BillUsageRecord.query.filter(BillUsageRecord.deleted == 0)
    if usage_bid:
        return (
            query.filter(BillUsageRecord.usage_bid == usage_bid)
            .order_by(BillUsageRecord.id.desc())
            .first()
        )
    if usage_id is None:
        return None
    return (
        query.filter(BillUsageRecord.id == int(usage_id))
        .order_by(BillUsageRecord.id.desc())
        .first()
    )


def _build_skip_result(usage: BillUsageRecord, *, reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": reason,
        "usage_bid": usage.usage_bid,
    }


def _load_credit_wallet(creator_bid: str) -> CreditWallet | None:
    return (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid == creator_bid,
        )
        .order_by(CreditWallet.id.desc())
        .first()
    )


def _load_consumable_buckets(
    creator_bid: str,
    *,
    settlement_at: datetime,
) -> list[CreditWalletBucket]:
    rows = (
        CreditWalletBucket.query.filter(
            CreditWalletBucket.deleted == 0,
            CreditWalletBucket.creator_bid == creator_bid,
            CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
        )
        .order_by(CreditWalletBucket.priority.asc(), CreditWalletBucket.id.asc())
        .all()
    )
    eligible = [
        row
        for row in rows
        if _to_decimal(row.available_credits) > _ZERO
        and (row.effective_from is None or row.effective_from <= settlement_at)
        and (row.effective_to is None or row.effective_to > settlement_at)
    ]
    eligible.sort(
        key=lambda row: (
            int(row.priority or 0),
            row.effective_to is None,
            row.effective_to or datetime.max,
            row.created_at or datetime.min,
            int(row.id or 0),
        )
    )
    return eligible


def _build_usage_metric_charges(
    usage: BillUsageRecord,
    *,
    settlement_at: datetime,
) -> list[dict[str, Any]]:
    usage_type = int(usage.usage_type or 0)
    if usage_type == BILL_USAGE_TYPE_LLM:
        return [
            charge
            for charge in (
                _build_metric_charge(
                    usage,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    raw_amount=int(usage.input or 0),
                    settlement_at=settlement_at,
                ),
                _build_metric_charge(
                    usage,
                    billing_metric=BILLING_METRIC_LLM_CACHE_TOKENS,
                    raw_amount=int(usage.input_cache or 0),
                    settlement_at=settlement_at,
                ),
                _build_metric_charge(
                    usage,
                    billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    raw_amount=int(usage.output or 0),
                    settlement_at=settlement_at,
                ),
            )
            if charge is not None
        ]

    if usage_type == BILL_USAGE_TYPE_TTS:
        charges: list[dict[str, Any]] = []
        for billing_metric, raw_amount in (
            (BILLING_METRIC_TTS_REQUEST_COUNT, 1),
            (BILLING_METRIC_TTS_OUTPUT_CHARS, int(usage.output or 0)),
            (BILLING_METRIC_TTS_INPUT_CHARS, int(usage.input or 0)),
        ):
            charge = _build_metric_charge(
                usage,
                billing_metric=billing_metric,
                raw_amount=raw_amount,
                settlement_at=settlement_at,
            )
            if charge is None:
                continue
            charges.append(charge)
            if _to_decimal(charge["consumed_credits"]) > _ZERO:
                break
        return charges[:1]

    return []


def _build_metric_charge(
    usage: BillUsageRecord,
    *,
    billing_metric: int,
    raw_amount: int,
    settlement_at: datetime,
) -> dict[str, Any] | None:
    if raw_amount <= 0:
        return None
    rate = _load_usage_rate(
        usage=usage,
        billing_metric=billing_metric,
        settlement_at=settlement_at,
    )
    if rate is None:
        return None

    rounded_units = _round_usage_units(
        raw_amount=raw_amount,
        unit_size=int(rate.unit_size or 1),
        rounding_mode=int(rate.rounding_mode or CREDIT_ROUNDING_MODE_CEIL),
    )
    consumed_credits = (rounded_units * _to_decimal(rate.credits_per_unit)).quantize(
        _DECIMAL_QUANT
    )
    return {
        "billing_metric": int(rate.billing_metric or billing_metric),
        "metric_label": BILLING_METRIC_LABELS.get(billing_metric, str(billing_metric)),
        "raw_amount": raw_amount,
        "unit_size": int(rate.unit_size or 1),
        "credits_per_unit": _to_decimal(rate.credits_per_unit),
        "rounding_mode": int(rate.rounding_mode or CREDIT_ROUNDING_MODE_CEIL),
        "rounded_units": rounded_units,
        "consumed_credits": consumed_credits,
    }


def _load_usage_rate(
    *,
    usage: BillUsageRecord,
    billing_metric: int,
    settlement_at: datetime,
) -> CreditUsageRate | None:
    provider = str(usage.provider or "").strip()
    model = str(usage.model or "").strip()
    usage_scene = int(usage.usage_scene or 0)
    rows = (
        CreditUsageRate.query.filter(
            CreditUsageRate.deleted == 0,
            CreditUsageRate.status == CREDIT_USAGE_RATE_STATUS_ACTIVE,
        )
        .filter(CreditUsageRate.usage_type == int(usage.usage_type or 0))
        .filter(CreditUsageRate.usage_scene == usage_scene)
        .filter(CreditUsageRate.billing_metric == billing_metric)
        .order_by(CreditUsageRate.effective_from.desc(), CreditUsageRate.id.desc())
        .all()
    )
    candidates = [
        row
        for row in rows
        if row.effective_from <= settlement_at
        and (row.effective_to is None or row.effective_to > settlement_at)
        and row.provider in {provider, "*"}
        and row.model in {model, "*"}
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            row.provider == provider,
            row.model == model,
            row.effective_from or datetime.min,
            int(row.id or 0),
        ),
        reverse=True,
    )
    return candidates[0]


def _round_usage_units(
    *,
    raw_amount: int,
    unit_size: int,
    rounding_mode: int,
) -> Decimal:
    normalized_unit_size = max(int(unit_size or 1), 1)
    quotient = Decimal(str(raw_amount)) / Decimal(str(normalized_unit_size))
    if rounding_mode == CREDIT_ROUNDING_MODE_FLOOR:
        return quotient.to_integral_value(rounding=ROUND_FLOOR)
    if rounding_mode == CREDIT_ROUNDING_MODE_ROUND:
        return quotient.to_integral_value(rounding=ROUND_HALF_UP)
    return quotient.to_integral_value(rounding=ROUND_CEILING)


def _build_usage_entry_metadata(
    *,
    usage: BillUsageRecord,
    charge: dict[str, Any],
    consumed: Decimal,
) -> dict[str, Any]:
    return _json_ready(
        {
            "usage_bid": usage.usage_bid,
            "usage_record_id": int(usage.id or 0),
            "usage_scene": int(usage.usage_scene or 0),
            "usage_type": int(usage.usage_type or 0),
            "provider": str(usage.provider or ""),
            "model": str(usage.model or ""),
            "metric_breakdown": [
                {
                    "billing_metric": charge["metric_label"],
                    "billing_metric_code": int(charge["billing_metric"]),
                    "raw_amount": int(charge["raw_amount"]),
                    "unit_size": int(charge["unit_size"]),
                    "rounded_units": _decimal_to_number(charge["rounded_units"]),
                    "credits_per_unit": _decimal_to_number(charge["credits_per_unit"]),
                    "rounding_mode": _ROUNDING_LABELS.get(
                        int(charge["rounding_mode"] or CREDIT_ROUNDING_MODE_CEIL),
                        "ceil",
                    ),
                    "consumed_credits": _decimal_to_number(consumed),
                }
            ],
        }
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_to_number(value)
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _decimal_to_number(value: Decimal | Any) -> int | float:
    decimal_value = _to_decimal(value)
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return float(decimal_value)

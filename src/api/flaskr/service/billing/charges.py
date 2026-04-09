"""Shared usage charge calculation helpers for billing settlement/reporting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from flaskr.service.metering.consts import BILL_USAGE_TYPE_LLM, BILL_USAGE_TYPE_TTS
from flaskr.service.metering.models import BillUsageRecord

from .consts import (
    BILLING_METRIC_LABELS,
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_INPUT_CHARS,
    BILLING_METRIC_TTS_OUTPUT_CHARS,
    BILLING_METRIC_TTS_REQUEST_COUNT,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_ROUNDING_MODE_FLOOR,
    CREDIT_ROUNDING_MODE_ROUND,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from .models import CreditUsageRate

_ZERO = Decimal("0")
_DECIMAL_QUANT = Decimal("0.0000000001")
_ROUNDING_LABELS = {
    CREDIT_ROUNDING_MODE_CEIL: "ceil",
    CREDIT_ROUNDING_MODE_FLOOR: "floor",
    CREDIT_ROUNDING_MODE_ROUND: "round",
}


def build_usage_metric_charges(
    usage: BillUsageRecord,
    *,
    settlement_at: datetime,
) -> list[dict[str, Any]]:
    usage_type = int(usage.usage_type or 0)
    if usage_type == BILL_USAGE_TYPE_LLM:
        return [
            charge
            for charge in (
                build_metric_charge(
                    usage,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    raw_amount=int(usage.input or 0),
                    settlement_at=settlement_at,
                ),
                build_metric_charge(
                    usage,
                    billing_metric=BILLING_METRIC_LLM_CACHE_TOKENS,
                    raw_amount=int(usage.input_cache or 0),
                    settlement_at=settlement_at,
                ),
                build_metric_charge(
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
            charge = build_metric_charge(
                usage,
                billing_metric=billing_metric,
                raw_amount=raw_amount,
                settlement_at=settlement_at,
            )
            if charge is None:
                continue
            charges.append(charge)
            if to_decimal(charge["consumed_credits"]) > _ZERO:
                break
        return charges[:1]

    return []


def build_metric_charge(
    usage: BillUsageRecord,
    *,
    billing_metric: int,
    raw_amount: int,
    settlement_at: datetime,
) -> dict[str, Any] | None:
    if raw_amount <= 0:
        return None
    rate = load_usage_rate(
        usage=usage,
        billing_metric=billing_metric,
        settlement_at=settlement_at,
    )
    if rate is None:
        return None

    rounded_units = round_usage_units(
        raw_amount=raw_amount,
        unit_size=int(rate.unit_size or 1),
        rounding_mode=int(rate.rounding_mode or CREDIT_ROUNDING_MODE_CEIL),
    )
    consumed_credits = (rounded_units * to_decimal(rate.credits_per_unit)).quantize(
        _DECIMAL_QUANT
    )
    return {
        "billing_metric": int(rate.billing_metric or billing_metric),
        "metric_label": BILLING_METRIC_LABELS.get(billing_metric, str(billing_metric)),
        "raw_amount": raw_amount,
        "unit_size": int(rate.unit_size or 1),
        "credits_per_unit": to_decimal(rate.credits_per_unit),
        "rounding_mode": int(rate.rounding_mode or CREDIT_ROUNDING_MODE_CEIL),
        "rounded_units": rounded_units,
        "consumed_credits": consumed_credits,
    }


def load_usage_rate(
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


def round_usage_units(
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


def build_usage_entry_metadata(
    *,
    usage: BillUsageRecord,
    charge: dict[str, Any],
    consumed: Decimal,
) -> dict[str, Any]:
    return json_ready(
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
                    "rounded_units": decimal_to_number(charge["rounded_units"]),
                    "credits_per_unit": decimal_to_number(charge["credits_per_unit"]),
                    "rounding_mode": _ROUNDING_LABELS.get(
                        int(charge["rounding_mode"] or CREDIT_ROUNDING_MODE_CEIL),
                        "ceil",
                    ),
                    "consumed_credits": decimal_to_number(consumed),
                }
            ],
        }
    )


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_to_number(value)
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    return value


def to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def decimal_to_number(value: Decimal | Any) -> int | float:
    decimal_value = to_decimal(value)
    if decimal_value == decimal_value.to_integral_value():
        return int(decimal_value)
    return float(decimal_value)

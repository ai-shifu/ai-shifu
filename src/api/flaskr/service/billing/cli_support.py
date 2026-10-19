"""Shared option tables and payload helpers for the billing Flask CLI."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import click
from flaskr.dao import db

from .consts import (
    ALLOCATION_INTERVAL_MANUAL,
    ALLOCATION_INTERVAL_ONE_TIME,
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_NONE,
    BILLING_INTERVAL_YEAR,
    BILLING_MODE_MANUAL,
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_STATUS_INACTIVE,
    BILLING_PRODUCT_TYPE_CUSTOM,
    BILLING_PRODUCT_TYPE_GRANT,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_DRAFT,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
    BILLING_PROVIDER_PRICE_STATUS_RETIRED,
)

_PRODUCT_TYPE_LABELS = {
    "custom": BILLING_PRODUCT_TYPE_CUSTOM,
    "grant": BILLING_PRODUCT_TYPE_GRANT,
    "plan": BILLING_PRODUCT_TYPE_PLAN,
    "topup": BILLING_PRODUCT_TYPE_TOPUP,
}


_BILLING_MODE_LABELS = {
    "manual": BILLING_MODE_MANUAL,
    "one_time": BILLING_MODE_ONE_TIME,
    "recurring": BILLING_MODE_RECURRING,
}


_BILLING_INTERVAL_LABELS = {
    "day": BILLING_INTERVAL_DAY,
    "month": BILLING_INTERVAL_MONTH,
    "none": BILLING_INTERVAL_NONE,
    "year": BILLING_INTERVAL_YEAR,
}


_ALLOCATION_INTERVAL_LABELS = {
    "manual": ALLOCATION_INTERVAL_MANUAL,
    "one_time": ALLOCATION_INTERVAL_ONE_TIME,
    "per_cycle": ALLOCATION_INTERVAL_PER_CYCLE,
}


_PRODUCT_STATUS_LABELS = {
    "active": BILLING_PRODUCT_STATUS_ACTIVE,
    "inactive": BILLING_PRODUCT_STATUS_INACTIVE,
}


_PROVIDER_PRICE_STATUS_LABELS = {
    "active": BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    "draft": BILLING_PROVIDER_PRICE_STATUS_DRAFT,
    "invalid": BILLING_PROVIDER_PRICE_STATUS_INVALID,
    "retired": BILLING_PROVIDER_PRICE_STATUS_RETIRED,
}


_DEFAULT_CLI_OPERATOR_USER_BID = "billing-cli"


def _normalize_cli_bid(value: object) -> str:
    return str(value or "").strip()


def _upsert_bootstrap_rows(
    *,
    model: object,
    key_field: str,
    rows: list[dict[str, object]],
) -> dict[str, int]:
    inserted = 0
    updated = 0
    for payload in rows:
        if _upsert_bootstrap_row(model=model, key_field=key_field, payload=payload):
            inserted += 1
        else:
            updated += 1
    return {
        "count": len(rows),
        "inserted": inserted,
        "updated": updated,
    }


def _upsert_bootstrap_row(
    *,
    model: object,
    key_field: str,
    payload: dict[str, object],
) -> bool:
    key_value = payload[key_field]
    instance = (
        model.query.filter(getattr(model, key_field) == key_value)
        .order_by(model.id.desc())
        .first()
    )
    if instance is None:
        db.session.add(model(**payload))
        return True

    for field_name, field_value in payload.items():
        setattr(instance, field_name, field_value)
    return False


def _parse_optional_json_object(
    raw_value: str, *, option_name: str
) -> dict[str, object] | None:
    normalized_value = str(raw_value or "").strip()
    if not normalized_value:
        return None

    try:
        parsed = json.loads(normalized_value)
    except json.JSONDecodeError as exc:
        message = f"--{option_name} must be valid JSON."
        raise click.ClickException(message) from exc
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        message = f"--{option_name} must decode to a JSON object."
        raise click.ClickException(message)
    return parsed


def _serialize_cli_payload(payload: object) -> object:
    if hasattr(payload, "to_task_payload"):
        return payload.to_task_payload()
    if hasattr(payload, "to_payload"):
        return payload.to_payload()
    if hasattr(payload, "to_response_dict"):
        return payload.to_response_dict()
    if hasattr(payload, "__json__"):
        return payload.__json__()
    return payload


def _echo_payload(payload: object) -> None:
    click.echo(
        json.dumps(
            _serialize_cli_payload(payload),
            sort_keys=True,
            ensure_ascii=False,
            default=_serialize_json_value,
        )
    )


def _serialize_json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return str(value)

"""Manual operator/admin credit grant helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from flaskr.dao.uow import app_context_scope
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .credit_notifications import stage_credit_granted_notification
from .grant_results import ManualCreditGrantResult
from .primitives import (
    credit_decimal_to_number as _credit_decimal_to_number,
)
from .primitives import (
    normalize_bid as _normalize_bid,
)
from .primitives import (
    quantize_credit_amount as _quantize_credit_amount,
)
from .queries import add_months as _add_months
from .queries import add_years as _add_years
from .wallets import grant_manual_credit_wallet_balance

if TYPE_CHECKING:
    from flask import Flask

MANUAL_CREDIT_GRANT_SOURCE_REWARD = "reward"
MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION = "compensation"
MANUAL_CREDIT_GRANT_SOURCES = (
    MANUAL_CREDIT_GRANT_SOURCE_REWARD,
    MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
)


def _normalize_credit_amount(value: object) -> Decimal:
    normalized = str(value or "").strip()
    if not normalized:
        raise_param_error("amount")
    try:
        parsed = _quantize_credit_amount(Decimal(normalized))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        raise_param_error("amount")
    if not parsed.is_finite() or parsed <= Decimal(0):
        raise_param_error("amount")
    return parsed


def _resolve_manual_credit_grant_expiry(
    *,
    granted_at: datetime,
    validity_value: int,
    validity_unit: str,
) -> datetime:
    if type(validity_value) is not int or validity_value <= 0:
        raise_param_error("validity_value")
    if validity_unit not in ("day", "month", "year"):
        raise_param_error("validity_unit")
    try:
        if validity_unit == "day":
            return granted_at + timedelta(days=validity_value)
        if validity_unit == "month":
            return _add_months(granted_at, validity_value)
        return _add_years(granted_at, validity_value)
    except (OverflowError, ValueError):
        raise_param_error("validity_value")


def grant_manual_credits_to_user(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    request_id: str,
    amount: str,
    grant_source: str,
    validity_value: int,
    validity_unit: str,
    display_name: str = "",
    note: str = "",
    grant_channel: str = "operator_user_management",
) -> ManualCreditGrantResult:
    """Grant immediately usable credits for a positive calendar duration."""
    granted_at = now_utc()
    expires_at = _resolve_manual_credit_grant_expiry(
        granted_at=granted_at,
        validity_value=validity_value,
        validity_unit=validity_unit,
    )
    return _grant_manual_credits(
        app,
        user_bid=user_bid,
        operator_user_bid=operator_user_bid,
        request_id=request_id,
        amount=amount,
        grant_source=grant_source,
        granted_at=granted_at,
        expires_at=expires_at,
        validity_metadata={
            "validity_value": validity_value,
            "validity_unit": validity_unit,
        },
        display_name=display_name,
        note=note,
        grant_channel=grant_channel,
    )


def grant_manual_credits_with_expiry(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    request_id: str,
    amount: str,
    grant_source: str,
    expires_at: datetime,
    display_name: str = "",
    note: str = "",
    grant_channel: str,
) -> ManualCreditGrantResult:
    """Grant internal compensation with an authoritative absolute UTC expiry.

    Stored naive timestamps are UTC; aware values are normalized to UTC. This
    internal service entry point is not part of the operator API or CLI.
    """
    granted_at = now_utc()
    if not isinstance(expires_at, datetime):
        raise_param_error("expires_at")
    try:
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
    except (OverflowError, ValueError):
        raise_param_error("expires_at")
    if expires_at <= granted_at:
        raise_param_error("expires_at")
    return _grant_manual_credits(
        app,
        user_bid=user_bid,
        operator_user_bid=operator_user_bid,
        request_id=request_id,
        amount=amount,
        grant_source=grant_source,
        granted_at=granted_at,
        expires_at=expires_at,
        validity_metadata={},
        display_name=display_name,
        note=note,
        grant_channel=grant_channel,
    )


def _grant_manual_credits(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    request_id: str,
    amount: str,
    grant_source: str,
    granted_at: datetime,
    expires_at: datetime,
    validity_metadata: dict[str, object],
    display_name: str,
    note: str,
    grant_channel: str,
) -> ManualCreditGrantResult:
    with app_context_scope(app):
        normalized_user_bid = _normalize_bid(user_bid)
        normalized_operator_user_bid = _normalize_bid(operator_user_bid)
        normalized_request_id = _normalize_bid(request_id)
        normalized_grant_source = _normalize_bid(grant_source).lower()
        normalized_display_name = str(display_name or "").strip()
        normalized_note = str(note or "").strip()

        if not normalized_user_bid:
            raise_param_error("user_bid")
        if not normalized_operator_user_bid:
            raise_param_error("operator_user_bid")
        if not normalized_request_id:
            raise_param_error("request_id")
        if normalized_grant_source not in MANUAL_CREDIT_GRANT_SOURCES:
            raise_param_error("grant_source")
        if len(normalized_display_name) > 128:
            raise_param_error("display_name")
        if len(normalized_note) > 255:
            raise_param_error("note")

        granted_amount = _normalize_credit_amount(amount)
        grant_result = grant_manual_credit_wallet_balance(
            app,
            creator_bid=normalized_user_bid,
            amount=granted_amount,
            source_bid=generate_id(app),
            effective_from=granted_at,
            effective_to=expires_at,
            idempotency_key=f"operator_manual_grant:{normalized_request_id}",
            metadata={
                "checkout_type": "manual_grant",
                "grant_type": "manual_grant",
                "grant_source": normalized_grant_source,
                **validity_metadata,
                "operator_user_bid": normalized_operator_user_bid,
                "grant_channel": grant_channel,
            },
            ledger_metadata={
                "display_name": normalized_display_name,
                "name": normalized_display_name,
                "note": normalized_note,
            },
        )
        if grant_result.status not in {"granted", "noop_existing"}:
            raise_error("server.billing.manualCreditGrantFailed")
        if grant_result.status == "granted" and grant_result.ledger_bid:
            stage_credit_granted_notification(
                app,
                ledger_bid=grant_result.ledger_bid,
                commit=True,
                enqueue=True,
            )

        persisted_metadata = dict(grant_result.metadata_json or {})
        return ManualCreditGrantResult(
            status=str(grant_result.status or "granted"),
            user_bid=normalized_user_bid,
            amount=_credit_decimal_to_number(grant_result.amount),
            grant_source=str(
                persisted_metadata.get("grant_source") or normalized_grant_source
            ).strip(),
            expires_at=grant_result.expires_at,
            validity_value=persisted_metadata.get("validity_value"),
            validity_unit=persisted_metadata.get("validity_unit"),
            display_name=str(persisted_metadata.get("display_name") or "").strip(),
            note=str(persisted_metadata.get("note") or "").strip(),
            wallet_bucket_bid=str(grant_result.wallet_bucket_bid or "").strip(),
            ledger_bid=str(grant_result.ledger_bid or "").strip(),
            metadata_json=persisted_metadata,
        )

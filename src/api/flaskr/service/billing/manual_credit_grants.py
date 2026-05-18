"""Manual operator/admin credit grant helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Flask

from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.uuid import generate_id

from .primitives import (
    credit_decimal_to_number as _credit_decimal_to_number,
    normalize_bid as _normalize_bid,
    quantize_credit_amount as _quantize_credit_amount,
)
from .queries import add_months as _add_months
from .queries import add_years as _add_years
from .queries import load_primary_active_subscription
from .wallets import grant_manual_credit_wallet_balance

MANUAL_CREDIT_GRANT_SOURCE_REWARD = "reward"
MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION = "compensation"
MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION = "align_subscription"
MANUAL_CREDIT_VALIDITY_1D = "1d"
MANUAL_CREDIT_VALIDITY_7D = "7d"
MANUAL_CREDIT_VALIDITY_1M = "1m"
MANUAL_CREDIT_VALIDITY_3M = "3m"
MANUAL_CREDIT_VALIDITY_1Y = "1y"

MANUAL_CREDIT_GRANT_SOURCES = (
    MANUAL_CREDIT_GRANT_SOURCE_REWARD,
    MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
)
MANUAL_CREDIT_VALIDITY_PRESETS = (
    MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
    MANUAL_CREDIT_VALIDITY_1D,
    MANUAL_CREDIT_VALIDITY_7D,
    MANUAL_CREDIT_VALIDITY_1M,
    MANUAL_CREDIT_VALIDITY_3M,
    MANUAL_CREDIT_VALIDITY_1Y,
)


@dataclass(slots=True, frozen=True)
class ManualCreditGrantResult:
    """Resolved state for one manual credit grant request."""

    status: str
    user_bid: str
    amount: int | float
    grant_source: str
    validity_preset: str
    expires_at: datetime | None
    wallet_bucket_bid: str
    ledger_bid: str
    display_name: str = ""
    note: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "user_bid": self.user_bid,
            "amount": self.amount,
            "grant_source": self.grant_source,
            "validity_preset": self.validity_preset,
            "expires_at": self.expires_at,
            "display_name": self.display_name,
            "note": self.note,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "ledger_bid": self.ledger_bid,
            "metadata_json": self.metadata_json,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]


def _normalize_credit_amount(value: Any) -> Decimal:
    normalized = str(value or "").strip()
    if not normalized:
        raise_param_error("amount")
    try:
        parsed = _quantize_credit_amount(Decimal(normalized))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        raise_param_error("amount")
    if not parsed.is_finite() or parsed <= Decimal("0"):
        raise_param_error("amount")
    return parsed


def _resolve_manual_credit_grant_expiry(
    *,
    creator_bid: str,
    validity_preset: str,
    granted_at: datetime,
) -> datetime | None:
    normalized_preset = _normalize_bid(validity_preset)
    if normalized_preset == MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION:
        subscription = load_primary_active_subscription(
            creator_bid,
            as_of=granted_at,
        )
        if (
            subscription is None
            or subscription.current_period_end_at is None
            or subscription.current_period_end_at <= granted_at
        ):
            raise_error("server.billing.subscriptionInactive")
        return subscription.current_period_end_at
    if normalized_preset == MANUAL_CREDIT_VALIDITY_1D:
        return granted_at + timedelta(days=1)
    if normalized_preset == MANUAL_CREDIT_VALIDITY_7D:
        return granted_at + timedelta(days=7)
    if normalized_preset == MANUAL_CREDIT_VALIDITY_1M:
        return _add_months(granted_at, 1)
    if normalized_preset == MANUAL_CREDIT_VALIDITY_3M:
        return _add_months(granted_at, 3)
    if normalized_preset == MANUAL_CREDIT_VALIDITY_1Y:
        return _add_years(granted_at, 1)
    raise_param_error("validity_preset")


def grant_manual_credits_to_user(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    request_id: str,
    amount: str,
    grant_source: str,
    validity_preset: str,
    display_name: str = "",
    note: str = "",
    grant_channel: str = "operator_user_management",
) -> ManualCreditGrantResult:
    """Grant manual credits to one user through the shared operator semantics."""

    with app.app_context():
        normalized_user_bid = _normalize_bid(user_bid)
        normalized_operator_user_bid = _normalize_bid(operator_user_bid)
        normalized_request_id = _normalize_bid(request_id)
        normalized_grant_source = _normalize_bid(grant_source).lower()
        normalized_validity_preset = _normalize_bid(validity_preset).lower()
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
        if normalized_validity_preset not in MANUAL_CREDIT_VALIDITY_PRESETS:
            raise_param_error("validity_preset")
        if len(normalized_display_name) > 128:
            raise_param_error("display_name")
        if len(normalized_note) > 255:
            raise_param_error("note")

        granted_amount = _normalize_credit_amount(amount)
        granted_at = datetime.now()
        expires_at = _resolve_manual_credit_grant_expiry(
            creator_bid=normalized_user_bid,
            validity_preset=normalized_validity_preset,
            granted_at=granted_at,
        )
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
                "validity_preset": normalized_validity_preset,
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
            raise_error("server.common.systemError")

        persisted_metadata = dict(grant_result.metadata_json or {})
        return ManualCreditGrantResult(
            status=str(grant_result.status or "granted"),
            user_bid=normalized_user_bid,
            amount=_credit_decimal_to_number(grant_result.amount),
            grant_source=str(
                persisted_metadata.get("grant_source") or normalized_grant_source
            ).strip(),
            validity_preset=str(
                persisted_metadata.get("validity_preset") or normalized_validity_preset
            ).strip(),
            expires_at=grant_result.expires_at,
            display_name=str(persisted_metadata.get("display_name") or "").strip(),
            note=str(persisted_metadata.get("note") or "").strip(),
            wallet_bucket_bid=str(grant_result.wallet_bucket_bid or "").strip(),
            ledger_bid=str(grant_result.ledger_bid or "").strip(),
            metadata_json=persisted_metadata,
        )

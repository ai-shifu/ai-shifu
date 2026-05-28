"""Referral reward credit grant helpers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Flask
from sqlalchemy.exc import IntegrityError

from flaskr.dao import db
from flaskr.service.common.models import raise_param_error
from flaskr.util.uuid import generate_id

from .bucket_categories import resolve_credit_bucket_priority
from .consts import (
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from .credit_notifications import (
    stage_credit_granted_notification,
    suppress_pending_expiring_notifications_for_bucket,
)
from .grant_results import ManualCreditGrantResult, ReferralRewardSummary
from .models import CreditLedgerEntry, CreditWalletBucket
from .primitives import (
    credit_decimal_to_number as _credit_decimal_to_number,
    normalize_bid as _normalize_bid,
    quantize_credit_amount as _quantize_credit_amount,
    to_decimal as _to_decimal,
)
from .queries import add_months as _add_months
from .wallets import (
    _expire_credit_wallet_buckets_in_session,
    _load_or_create_credit_wallet,
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)

REFERRAL_REWARD_GRANT_TYPE = "referral_reward"
REFERRAL_REWARD_SCENE = "referral"
REFERRAL_REWARD_PROGRAM = "referral_reward"
REFERRAL_REWARD_VALIDITY_STRATEGY = "stack_by_reward_scene"
REFERRAL_REWARD_VALIDITY_MONTHS = 1
REFERRAL_REWARD_GRANT_SOURCE = "reward"
REFERRAL_REWARD_VALIDITY_PRESET = "1m"


def _normalize_referral_reward_amount(value: Any) -> Decimal:
    normalized = str(value or "").strip()
    if not normalized or not normalized.isdigit():
        raise_param_error("amount")
    try:
        parsed = _quantize_credit_amount(Decimal(normalized))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        raise_param_error("amount")
    if not parsed.is_finite() or parsed <= Decimal("0"):
        raise_param_error("amount")
    return parsed


def _serialize_metadata_datetime(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _is_referral_reward_metadata(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    return str(metadata.get("grant_type") or "").strip() == REFERRAL_REWARD_GRANT_TYPE


def _base_referral_reward_metadata() -> dict[str, str]:
    return {
        "grant_type": REFERRAL_REWARD_GRANT_TYPE,
        "reward_scene": REFERRAL_REWARD_SCENE,
        "reward_program": REFERRAL_REWARD_PROGRAM,
        "validity_strategy": REFERRAL_REWARD_VALIDITY_STRATEGY,
    }


def _load_active_referral_reward_buckets(
    creator_bid: str,
    *,
    as_of: datetime,
    for_update: bool = False,
) -> list[CreditWalletBucket]:
    query = CreditWalletBucket.query.filter(
        CreditWalletBucket.deleted == 0,
        CreditWalletBucket.creator_bid == _normalize_bid(creator_bid),
        CreditWalletBucket.source_type == CREDIT_SOURCE_TYPE_MANUAL,
        CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
        CreditWalletBucket.effective_to.isnot(None),
        CreditWalletBucket.effective_to > as_of,
    ).order_by(
        CreditWalletBucket.effective_to.desc(),
        CreditWalletBucket.id.desc(),
    )
    if for_update:
        query = query.with_for_update()
    return [
        bucket
        for bucket in query.all()
        if _is_referral_reward_metadata(bucket.metadata_json)
    ]


def _count_referral_reward_grants(creator_bid: str) -> int:
    return int(
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == _normalize_bid(creator_bid),
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_MANUAL,
            CreditLedgerEntry.source_bid == REFERRAL_REWARD_PROGRAM,
        ).count()
        or 0
    )


def load_referral_reward_summary(
    app: Flask,
    *,
    creator_bid: str,
    as_of: datetime | None = None,
) -> ReferralRewardSummary:
    with app.app_context():
        scan_at = as_of or datetime.now()
        buckets = _load_active_referral_reward_buckets(
            creator_bid,
            as_of=scan_at,
        )
        available = sum(
            (_to_decimal(bucket.available_credits) for bucket in buckets),
            start=Decimal("0"),
        )
        expires_at = buckets[0].effective_to if buckets else None
        wallet_bucket_bid = str(buckets[0].wallet_bucket_bid or "") if buckets else ""
        return ReferralRewardSummary(
            available_credits=_credit_decimal_to_number(available),
            expires_at=expires_at,
            wallet_bucket_bid=wallet_bucket_bid,
            grant_count=_count_referral_reward_grants(creator_bid),
        )


def _load_existing_referral_reward_result(
    *,
    creator_bid: str,
    ledger_key: str,
) -> ManualCreditGrantResult | None:
    existing_entry = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == creator_bid,
            CreditLedgerEntry.idempotency_key == ledger_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if existing_entry is None:
        return None
    return ManualCreditGrantResult(
        status="noop_existing",
        user_bid=str(existing_entry.creator_bid or "").strip(),
        amount=_credit_decimal_to_number(_to_decimal(existing_entry.amount)),
        grant_source=str(
            (existing_entry.metadata_json or {}).get("grant_source")
            or REFERRAL_REWARD_GRANT_SOURCE
        ),
        validity_preset=REFERRAL_REWARD_VALIDITY_PRESET,
        expires_at=existing_entry.expires_at,
        wallet_bucket_bid=str(existing_entry.wallet_bucket_bid or "").strip(),
        ledger_bid=str(existing_entry.ledger_bid or "").strip(),
        note=str((existing_entry.metadata_json or {}).get("note") or "").strip(),
        metadata_json=dict(existing_entry.metadata_json or {}),
    )


def grant_referral_reward_credits_to_user(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    request_id: str,
    amount: str,
    note: str = "",
    grant_channel: str = "operator_user_management",
) -> ManualCreditGrantResult:
    """Grant referral reward credits and extend the referral reward pool."""

    with app.app_context():
        normalized_user_bid = _normalize_bid(user_bid)
        normalized_operator_user_bid = _normalize_bid(operator_user_bid)
        normalized_request_id = _normalize_bid(request_id)
        normalized_note = str(note or "").strip()

        if not normalized_user_bid:
            raise_param_error("user_bid")
        if not normalized_operator_user_bid:
            raise_param_error("operator_user_bid")
        if not normalized_request_id:
            raise_param_error("request_id")
        if len(normalized_note) > 255:
            raise_param_error("note")

        granted_amount = _normalize_referral_reward_amount(amount)
        granted_at = datetime.now()
        ledger_key = f"operator_referral_reward:{normalized_request_id}"
        existing_result = _load_existing_referral_reward_result(
            creator_bid=normalized_user_bid,
            ledger_key=ledger_key,
        )
        if existing_result is not None:
            return existing_result

        _expire_credit_wallet_buckets_in_session(
            app,
            creator_bid=normalized_user_bid,
            expire_before=granted_at,
        )
        wallet = _load_or_create_credit_wallet(app, normalized_user_bid)
        db.session.refresh(wallet, with_for_update=True)
        buckets = _load_active_referral_reward_buckets(
            normalized_user_bid,
            as_of=granted_at,
            for_update=True,
        )
        bucket = buckets[0] if buckets else None
        previous_effective_to = bucket.effective_to if bucket is not None else None
        base_effective_to = (
            previous_effective_to
            if previous_effective_to is not None and previous_effective_to > granted_at
            else granted_at
        )
        new_effective_to = _add_months(
            base_effective_to,
            REFERRAL_REWARD_VALIDITY_MONTHS,
        )

        base_metadata = _base_referral_reward_metadata()
        if bucket is None:
            bucket = CreditWalletBucket(
                wallet_bucket_bid=generate_id(app),
                wallet_bid=wallet.wallet_bid,
                creator_bid=normalized_user_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid=REFERRAL_REWARD_PROGRAM,
                priority=resolve_credit_bucket_priority(
                    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
                ),
                original_credits=granted_amount,
                available_credits=granted_amount,
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=granted_at,
                effective_to=new_effective_to,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json=base_metadata,
            )
            db.session.add(bucket)
            db.session.flush()
        else:
            bucket.original_credits = _quantize_credit_amount(
                _to_decimal(bucket.original_credits) + granted_amount
            )
            bucket.available_credits = _quantize_credit_amount(
                _to_decimal(bucket.available_credits) + granted_amount
            )
            bucket.effective_to = new_effective_to
            bucket.metadata_json = {
                **(
                    bucket.metadata_json
                    if isinstance(bucket.metadata_json, dict)
                    else {}
                ),
                **base_metadata,
            }
            bucket.updated_at = granted_at
            sync_credit_bucket_status(bucket)
            suppress_pending_expiring_notifications_for_bucket(
                app,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                effective_to=new_effective_to,
            )
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
                CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_MANUAL,
            ).update(
                {"expires_at": new_effective_to},
                synchronize_session=False,
            )

        refresh_credit_wallet_snapshot(wallet)
        balance_after = _quantize_credit_amount(wallet.available_credits)
        next_lifetime_granted = _quantize_credit_amount(
            _to_decimal(wallet.lifetime_granted_credits) + granted_amount
        )
        ledger_metadata = {
            **base_metadata,
            "grant_source": REFERRAL_REWARD_GRANT_SOURCE,
            "validity_preset": REFERRAL_REWARD_VALIDITY_PRESET,
            "reward_credits": str(granted_amount),
            "previous_effective_to": _serialize_metadata_datetime(
                previous_effective_to
            ),
            "new_effective_to": _serialize_metadata_datetime(new_effective_to),
            "operator_user_bid": normalized_operator_user_bid,
            "grant_channel": grant_channel,
            "note": normalized_note,
        }
        ledger_entry = CreditLedgerEntry(
            ledger_bid=generate_id(app),
            creator_bid=normalized_user_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=REFERRAL_REWARD_PROGRAM,
            idempotency_key=ledger_key,
            amount=granted_amount,
            balance_after=balance_after,
            expires_at=new_effective_to,
            consumable_from=granted_at,
            metadata_json=ledger_metadata,
        )
        persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            lifetime_granted_credits=next_lifetime_granted,
            updated_at=granted_at,
        )
        db.session.add(ledger_entry)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing_result = _load_existing_referral_reward_result(
                creator_bid=normalized_user_bid,
                ledger_key=ledger_key,
            )
            if existing_result is not None:
                return existing_result
            raise

        stage_credit_granted_notification(
            app,
            ledger_bid=ledger_entry.ledger_bid,
            commit=True,
            enqueue=True,
        )
        return ManualCreditGrantResult(
            status="granted",
            user_bid=normalized_user_bid,
            amount=_credit_decimal_to_number(granted_amount),
            grant_source=REFERRAL_REWARD_GRANT_SOURCE,
            validity_preset=REFERRAL_REWARD_VALIDITY_PRESET,
            expires_at=new_effective_to,
            wallet_bucket_bid=str(bucket.wallet_bucket_bid or "").strip(),
            ledger_bid=str(ledger_entry.ledger_bid or "").strip(),
            note=normalized_note,
            metadata_json=ledger_metadata,
        )

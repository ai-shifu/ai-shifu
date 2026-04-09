"""New creator trial helpers for billing overview and first grant."""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from flask import Flask
from sqlalchemy.exc import IntegrityError

from flaskr.dao import db
from flaskr.service.config import get_config
from flaskr.service.user.repository import (
    get_first_verified_credential_created_at,
    get_user_entity_by_bid,
)
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_CONFIG_KEY_NEW_CREATOR_TRIAL_CONFIG,
    BILLING_NEW_CREATOR_TRIAL_CONFIG_DEFAULT,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_GIFT,
)
from .dtos import BillingTrialOfferDTO
from .models import CreditLedgerEntry, CreditWalletBucket
from .primitives import coerce_bool as _coerce_bool
from .primitives import decimal_to_number as _decimal_to_number
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import parse_config_datetime as _parse_config_datetime
from .primitives import safe_to_decimal as _safe_to_decimal
from .primitives import safe_to_positive_int as _safe_to_positive_int
from .primitives import serialize_dt as _serialize_dt
from .primitives import to_decimal as _to_decimal
from .subscriptions import load_or_create_credit_wallet as _load_or_create_credit_wallet
from .wallets import (
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)

_BUCKET_PRIORITY_BY_CATEGORY = {
    CREDIT_BUCKET_CATEGORY_FREE: 10,
}


@dataclass(slots=True, frozen=True)
class NewCreatorTrialConfig:
    enabled: bool
    program_code: str
    credit_amount: str
    valid_days: int
    eligible_registered_after: str
    grant_trigger: str


@dataclass(slots=True, frozen=True)
class TrialOfferState:
    enabled: bool
    status: str
    credit_amount: Decimal
    valid_days: int
    starts_on_first_grant: bool
    granted_at: datetime | None = None
    expires_at: datetime | None = None

    def to_dto(
        self, app: Flask, *, timezone_name: str | None = None
    ) -> BillingTrialOfferDTO:
        return BillingTrialOfferDTO(
            enabled=bool(self.enabled),
            status=str(self.status),
            credit_amount=_decimal_to_number(self.credit_amount),
            valid_days=int(self.valid_days),
            starts_on_first_grant=bool(self.starts_on_first_grant),
            granted_at=_serialize_dt(
                app,
                self.granted_at,
                timezone_name=timezone_name,
            ),
            expires_at=_serialize_dt(
                app,
                self.expires_at,
                timezone_name=timezone_name,
            ),
        )


def _resolve_new_creator_trial_offer(
    app: Flask,
    creator_bid: str,
    *,
    trigger: str,
    timezone_name: str | None = None,
) -> BillingTrialOfferDTO:
    config = _load_new_creator_trial_config(app)
    existing_entry = _load_new_creator_trial_entry(
        creator_bid,
        program_code=config.program_code,
    )
    if existing_entry is not None:
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state_from_entry(
                existing_entry,
                enabled=bool(config.enabled),
                config=config,
            ),
            timezone_name=timezone_name,
        )

    if not config.enabled:
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                enabled=False,
                status="disabled",
                config=config,
            ),
            timezone_name=timezone_name,
        )

    eligible_registered_after = _parse_config_datetime(config.eligible_registered_after)
    if eligible_registered_after is None:
        app.logger.warning(
            "New creator trial config enabled without eligible_registered_after"
        )
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                enabled=True,
                status="ineligible",
                config=config,
            ),
            timezone_name=timezone_name,
        )

    creator = get_user_entity_by_bid(creator_bid)
    if creator is None or not bool(creator.is_creator):
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                enabled=True,
                status="ineligible",
                config=config,
            ),
            timezone_name=timezone_name,
        )

    registered_at = get_first_verified_credential_created_at(user_bid=creator_bid)
    if registered_at is None or registered_at < eligible_registered_after:
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                enabled=True,
                status="ineligible",
                config=config,
            ),
            timezone_name=timezone_name,
        )

    if str(config.grant_trigger) != trigger:
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                enabled=True,
                status="eligible",
                config=config,
            ),
            timezone_name=timezone_name,
        )

    grant_result = _grant_new_creator_trial_credits(
        app,
        creator_bid=creator_bid,
        config=config,
        registered_at=registered_at,
        trigger=trigger,
    )
    return _serialize_trial_offer(
        app,
        grant_result,
        timezone_name=timezone_name,
    )


def _grant_new_creator_trial_credits(
    app: Flask,
    *,
    creator_bid: str,
    config: NewCreatorTrialConfig,
    registered_at: datetime,
    trigger: str,
) -> TrialOfferState:
    amount = _to_decimal(config.credit_amount)
    valid_days = int(config.valid_days)
    if amount <= 0 or valid_days <= 0:
        return _build_trial_offer_state(
            enabled=True,
            status="ineligible",
            config=config,
        )

    idempotency_key = _build_new_creator_trial_idempotency_key(
        creator_bid=creator_bid,
        program_code=config.program_code,
    )
    existing_entry = _load_new_creator_trial_entry(
        creator_bid,
        program_code=config.program_code,
    )
    if existing_entry is not None:
        return _build_trial_offer_state_from_entry(
            existing_entry,
            enabled=True,
            config=config,
        )

    wallet = _load_or_create_credit_wallet(app, creator_bid)
    granted_at = datetime.now()
    expires_at = granted_at + timedelta(days=valid_days)
    trial_metadata = _normalize_json_object(
        {
            "trial_program": config.program_code,
            "grant_trigger": trigger,
            "registered_at": registered_at,
            "trial_config": {
                "credit_amount": amount,
                "eligible_registered_after": config.eligible_registered_after,
                "grant_trigger": config.grant_trigger,
                "program_code": config.program_code,
                "valid_days": valid_days,
            },
        }
    ).to_metadata_json()

    bucket = CreditWalletBucket(
        wallet_bucket_bid=generate_id(app),
        wallet_bid=wallet.wallet_bid,
        creator_bid=creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        source_bid=config.program_code,
        priority=_BUCKET_PRIORITY_BY_CATEGORY[CREDIT_BUCKET_CATEGORY_FREE],
        original_credits=amount,
        available_credits=amount,
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=granted_at,
        effective_to=expires_at,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json=trial_metadata,
    )

    try:
        db.session.add(bucket)
        sync_credit_bucket_status(bucket)
        refresh_credit_wallet_snapshot(wallet)
        balance_after = _to_decimal(wallet.available_credits)
        next_lifetime_granted = _to_decimal(wallet.lifetime_granted_credits) + amount
        ledger_entry = CreditLedgerEntry(
            ledger_bid=generate_id(app),
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_GIFT,
            source_bid=config.program_code,
            idempotency_key=idempotency_key,
            amount=amount,
            balance_after=balance_after,
            expires_at=expires_at,
            consumable_from=granted_at,
            metadata_json=trial_metadata,
        )
        persist_credit_wallet_snapshot(
            wallet,
            available_credits=wallet.available_credits,
            reserved_credits=wallet.reserved_credits,
            lifetime_granted_credits=next_lifetime_granted,
            updated_at=granted_at,
        )
        db.session.add(ledger_entry)
        db.session.commit()
        return _build_trial_offer_state_from_entry(
            ledger_entry,
            enabled=True,
            config=config,
        )
    except IntegrityError:
        db.session.rollback()
        existing_entry = _load_new_creator_trial_entry(
            creator_bid,
            program_code=config.program_code,
        )
        if existing_entry is not None:
            return _build_trial_offer_state_from_entry(
                existing_entry,
                enabled=True,
                config=config,
            )
        raise


def _load_new_creator_trial_entry(
    creator_bid: str,
    *,
    program_code: str,
) -> CreditLedgerEntry | None:
    if not creator_bid or not program_code:
        return None
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == creator_bid,
            CreditLedgerEntry.idempotency_key
            == _build_new_creator_trial_idempotency_key(
                creator_bid=creator_bid,
                program_code=program_code,
            ),
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )


def _build_new_creator_trial_idempotency_key(
    *,
    creator_bid: str,
    program_code: str,
) -> str:
    return f"trial:{program_code}:{creator_bid}"


def _load_new_creator_trial_config(app: Flask) -> NewCreatorTrialConfig:
    raw_value = get_config(BILLING_CONFIG_KEY_NEW_CREATOR_TRIAL_CONFIG, "")
    payload = dict(BILLING_NEW_CREATOR_TRIAL_CONFIG_DEFAULT)
    if isinstance(raw_value, dict):
        candidate = raw_value
    else:
        raw_text = str(raw_value or "").strip()
        candidate: dict[str, Any] = {}
        if raw_text:
            try:
                loaded = json.loads(raw_text)
            except json.JSONDecodeError:
                app.logger.warning(
                    "Invalid new creator trial config JSON: %s", raw_text
                )
                loaded = {}
            if isinstance(loaded, dict):
                candidate = loaded
    payload.update(candidate)
    return NewCreatorTrialConfig(
        enabled=_coerce_bool(payload.get("enabled")),
        program_code=str(
            payload.get("program_code")
            or BILLING_NEW_CREATOR_TRIAL_CONFIG_DEFAULT["program_code"]
        ).strip(),
        credit_amount=str(
            _safe_to_decimal(
                payload.get("credit_amount"),
                default=BILLING_NEW_CREATOR_TRIAL_CONFIG_DEFAULT["credit_amount"],
            )
        ),
        valid_days=_safe_to_positive_int(
            payload.get("valid_days"),
            default=int(BILLING_NEW_CREATOR_TRIAL_CONFIG_DEFAULT["valid_days"]),
        ),
        eligible_registered_after=str(
            payload.get("eligible_registered_after") or ""
        ).strip(),
        grant_trigger=str(
            payload.get("grant_trigger")
            or BILLING_NEW_CREATOR_TRIAL_CONFIG_DEFAULT["grant_trigger"]
        ).strip(),
    )


def _build_trial_offer_state(
    *,
    enabled: bool,
    status: str,
    config: NewCreatorTrialConfig,
    granted_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> TrialOfferState:
    return TrialOfferState(
        enabled=enabled,
        status=status,
        credit_amount=_to_decimal(config.credit_amount),
        valid_days=int(config.valid_days),
        starts_on_first_grant=True,
        granted_at=granted_at,
        expires_at=expires_at,
    )


def _build_trial_offer_state_from_entry(
    entry: CreditLedgerEntry,
    *,
    enabled: bool,
    config: NewCreatorTrialConfig,
) -> TrialOfferState:
    metadata = entry.metadata_json if isinstance(entry.metadata_json, dict) else {}
    config_snapshot = (
        metadata.get("trial_config")
        if isinstance(metadata.get("trial_config"), dict)
        else {}
    )
    offer_config = NewCreatorTrialConfig(
        enabled=enabled,
        program_code=config.program_code,
        credit_amount=str(
            _safe_to_decimal(
                config_snapshot.get("credit_amount"),
                default=config.credit_amount,
            )
        ),
        valid_days=_safe_to_positive_int(
            config_snapshot.get("valid_days"),
            default=int(config.valid_days),
        ),
        eligible_registered_after=config.eligible_registered_after,
        grant_trigger=config.grant_trigger,
    )
    return _build_trial_offer_state(
        enabled=enabled,
        status="granted",
        config=offer_config,
        granted_at=entry.created_at,
        expires_at=entry.expires_at,
    )


def _serialize_trial_offer(
    app: Flask,
    state: TrialOfferState,
    *,
    timezone_name: str | None = None,
) -> BillingTrialOfferDTO:
    return state.to_dto(app, timezone_name=timezone_name)


resolve_new_creator_trial_offer = _resolve_new_creator_trial_offer

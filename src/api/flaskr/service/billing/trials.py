"""New creator trial helpers for billing overview state and first grant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
from typing import Any

from flask import Flask
from sqlalchemy.exc import IntegrityError

from flaskr.dao import db
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import get_user_entity_by_bid

from .consts import (
    BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_TRIAL_PRODUCT_BID,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
    BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT,
    BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS,
)
from .dtos import BillingTrialOfferDTO, BillingTrialWelcomeAckDTO
from .models import BillingOrder, BillingProduct, BillingSubscription, CreditLedgerEntry
from .primitives import coerce_bool as _coerce_bool
from .primitives import credit_decimal_to_number as _credit_decimal_to_number
from .primitives import is_billing_enabled as _is_billing_enabled
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import safe_to_positive_int as _safe_to_positive_int
from .primitives import serialize_dt as _serialize_dt
from .subscriptions import grant_paid_order_credits as _grant_paid_order_credits

_ACTIVE_SUBSCRIPTION_STATUSES = (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
)
_TRIAL_WELCOME_ACK_KEY = "welcome_trial_dialog_acknowledged_at"


@dataclass(slots=True, frozen=True)
class TrialOfferState:
    enabled: bool
    status: str
    product_bid: str
    product_code: str
    display_name: str
    description: str
    currency: str
    price_amount: int
    credit_amount: Decimal
    highlights: tuple[str, ...]
    valid_days: int
    starts_on_first_grant: bool
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    welcome_dialog_acknowledged_at: datetime | None = None

    def to_dto(
        self, app: Flask, *, timezone_name: str | None = None
    ) -> BillingTrialOfferDTO:
        return BillingTrialOfferDTO(
            enabled=bool(self.enabled),
            status=str(self.status),
            product_bid=str(self.product_bid),
            product_code=str(self.product_code),
            display_name=str(self.display_name),
            description=str(self.description),
            currency=str(self.currency),
            price_amount=int(self.price_amount),
            credit_amount=_credit_decimal_to_number(self.credit_amount),
            highlights=list(self.highlights),
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
            welcome_dialog_acknowledged_at=_serialize_dt(
                app,
                self.welcome_dialog_acknowledged_at,
                timezone_name=timezone_name,
            ),
        )


def _trial_product_field(product_ref: Any, field: str, default: Any = "") -> Any:
    if isinstance(product_ref, BillingProduct):
        return getattr(product_ref, field, default)
    if isinstance(product_ref, dict):
        return product_ref.get(field, default)
    return default


def _trial_product_metadata(product_ref: Any) -> dict[str, Any]:
    if isinstance(product_ref, BillingProduct):
        payload = product_ref.metadata_json
    elif isinstance(product_ref, dict):
        payload = product_ref.get("metadata_json")
        if payload is None:
            payload = product_ref.get("metadata")
    else:
        payload = None
    return dict(payload) if isinstance(payload, dict) else {}


def _resolve_trial_valid_days(product_ref: Any) -> int:
    metadata = _trial_product_metadata(product_ref)
    return _safe_to_positive_int(
        metadata.get(BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS),
        default=15,
    )


def _resolve_trial_highlights(product_ref: Any) -> tuple[str, ...]:
    metadata = _trial_product_metadata(product_ref)
    highlights = metadata.get("highlights")
    if not isinstance(highlights, list):
        return ()
    return tuple(str(item) for item in highlights if str(item or "").strip())


def _trial_product_public_enabled(product_ref: Any) -> bool:
    metadata = _trial_product_metadata(product_ref)
    return _coerce_bool(
        metadata.get(BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG),
        default=False,
    )


def _resolve_trial_product_reference() -> BillingProduct | dict[str, Any] | None:
    return (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_code == BILLING_TRIAL_PRODUCT_CODE,
            BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )


def _build_trial_offer_state(
    product_ref: BillingProduct | dict[str, Any] | None,
    *,
    enabled: bool,
    status: str,
    granted_at: datetime | None = None,
    expires_at: datetime | None = None,
    welcome_dialog_acknowledged_at: datetime | None = None,
) -> TrialOfferState:
    metadata = _trial_product_metadata(product_ref)
    return TrialOfferState(
        enabled=bool(enabled),
        status=str(status),
        product_bid=str(
            _trial_product_field(product_ref, "product_bid", BILLING_TRIAL_PRODUCT_BID)
        ),
        product_code=str(
            _trial_product_field(
                product_ref,
                "product_code",
                BILLING_TRIAL_PRODUCT_CODE,
            )
        ),
        display_name=str(
            _trial_product_field(product_ref, "display_name_i18n_key", "")
        ),
        description=str(_trial_product_field(product_ref, "description_i18n_key", "")),
        currency=str(_trial_product_field(product_ref, "currency", "CNY")),
        price_amount=int(_trial_product_field(product_ref, "price_amount", 0) or 0),
        credit_amount=_quantize_credit_amount(
            _trial_product_field(product_ref, "credit_amount", 0)
        ),
        highlights=_resolve_trial_highlights(product_ref),
        valid_days=_resolve_trial_valid_days(product_ref),
        starts_on_first_grant=_coerce_bool(
            metadata.get(BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT),
            default=True,
        ),
        granted_at=granted_at,
        expires_at=expires_at,
        welcome_dialog_acknowledged_at=welcome_dialog_acknowledged_at,
    )


def _load_trial_subscription(creator_bid: str) -> BillingSubscription | None:
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
            BillingSubscription.product_bid == BILLING_TRIAL_PRODUCT_BID,
        )
        .order_by(
            BillingSubscription.current_period_end_at.desc(),
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        )
        .first()
    )


def _load_trial_order(creator_bid: str) -> BillingOrder | None:
    return (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == creator_bid,
            BillingOrder.product_bid == BILLING_TRIAL_PRODUCT_BID,
            BillingOrder.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        )
        .order_by(BillingOrder.paid_at.desc(), BillingOrder.created_at.desc())
        .first()
    )


def _load_active_creator_subscription(creator_bid: str) -> BillingSubscription | None:
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
            BillingSubscription.status.in_(_ACTIVE_SUBSCRIPTION_STATUSES),
        )
        .order_by(
            BillingSubscription.current_period_end_at.desc(),
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        )
        .first()
    )


def _load_legacy_trial_entry(creator_bid: str) -> CreditLedgerEntry | None:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return None
    legacy_idempotency_key = f"trial:{BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE}:{normalized_creator_bid}"
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == normalized_creator_bid,
        )
        .filter(
            (CreditLedgerEntry.idempotency_key == legacy_idempotency_key)
            | (
                CreditLedgerEntry.source_bid
                == BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE
            )
        )
        .order_by(CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc())
        .first()
    )


def _resolve_trial_period_from_history(
    *,
    subscription: BillingSubscription | None,
    order: BillingOrder | None,
    legacy_entry: CreditLedgerEntry | None,
) -> tuple[datetime | None, datetime | None]:
    if subscription is not None:
        granted_at = subscription.current_period_start_at or subscription.created_at
        expires_at = subscription.current_period_end_at
        return granted_at, expires_at
    if order is not None:
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        granted_at = order.paid_at or order.created_at
        expires_at = None
        raw_expires_at = metadata.get("trial_expires_at")
        if isinstance(raw_expires_at, str) and raw_expires_at.strip():
            try:
                expires_at = datetime.fromisoformat(raw_expires_at)
            except ValueError:
                expires_at = None
        return granted_at, expires_at
    if legacy_entry is not None:
        granted_at = legacy_entry.consumable_from or legacy_entry.created_at
        expires_at = legacy_entry.expires_at
        return granted_at, expires_at
    return None, None


def _extract_trial_welcome_acknowledged_at_from_metadata(
    record: BillingSubscription | BillingOrder | CreditLedgerEntry | None,
) -> datetime | None:
    if record is None or not isinstance(record.metadata_json, dict):
        return None
    raw_value = record.metadata_json.get(_TRIAL_WELCOME_ACK_KEY)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def _resolve_trial_welcome_acknowledged_at_from_history(
    *,
    subscription: BillingSubscription | None,
    order: BillingOrder | None,
    legacy_entry: CreditLedgerEntry | None,
) -> datetime | None:
    for record in (subscription, order, legacy_entry):
        acknowledged_at = _extract_trial_welcome_acknowledged_at_from_metadata(record)
        if acknowledged_at is not None:
            return acknowledged_at
    return None


def _set_trial_welcome_acknowledged_at(
    record: BillingSubscription | BillingOrder | CreditLedgerEntry,
    *,
    acknowledged_at: datetime,
) -> None:
    metadata = (
        _normalize_json_object(record.metadata_json).to_metadata_json()
        if isinstance(record.metadata_json, dict)
        else {}
    )
    metadata[_TRIAL_WELCOME_ACK_KEY] = acknowledged_at.isoformat()
    record.metadata_json = _normalize_json_object(metadata).to_metadata_json()


def _build_trial_subscription_bid(creator_bid: str) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_DNS,
        f"bill-trial-subscription:{creator_bid}",
    ).hex


def _build_trial_order_bid(creator_bid: str) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_DNS,
        f"bill-trial-order:{creator_bid}",
    ).hex


def _bootstrap_trial_subscription(
    app: Flask,
    *,
    creator_bid: str,
    product_ref: BillingProduct | dict[str, Any],
    trigger: str,
) -> None:
    valid_days = _resolve_trial_valid_days(product_ref)
    credit_amount = _quantize_credit_amount(
        _trial_product_field(product_ref, "credit_amount", 0)
    )
    if valid_days <= 0 or credit_amount <= 0:
        return

    now = datetime.now()
    expires_at = now + timedelta(days=valid_days)
    product_bid = str(
        _trial_product_field(product_ref, "product_bid", BILLING_TRIAL_PRODUCT_BID)
    )
    product_code = str(
        _trial_product_field(product_ref, "product_code", BILLING_TRIAL_PRODUCT_CODE)
    )

    subscription_metadata = _normalize_json_object(
        {
            "trial_bootstrap": True,
            "trial_trigger": trigger,
            "trial_product_code": product_code,
            "trial_valid_days": valid_days,
        }
    ).to_metadata_json()
    order_metadata = _normalize_json_object(
        {
            "checkout_type": "trial_bootstrap",
            "trial_bootstrap": True,
            "trial_trigger": trigger,
            "trial_product_code": product_code,
            "trial_valid_days": valid_days,
            "trial_starts_at": now.isoformat(),
            "trial_expires_at": expires_at.isoformat(),
        }
    ).to_metadata_json()

    subscription = BillingSubscription(
        subscription_bid=_build_trial_subscription_bid(creator_bid),
        creator_bid=creator_bid,
        product_bid=product_bid,
        status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
        billing_provider="manual",
        provider_subscription_id="",
        provider_customer_id="",
        billing_anchor_at=now,
        current_period_start_at=now,
        current_period_end_at=expires_at,
        grace_period_end_at=None,
        cancel_at_period_end=0,
        next_product_bid="",
        last_renewed_at=None,
        last_failed_at=None,
        metadata_json=subscription_metadata,
    )
    order = BillingOrder(
        bill_order_bid=_build_trial_order_bid(creator_bid),
        creator_bid=creator_bid,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        product_bid=product_bid,
        subscription_bid=subscription.subscription_bid,
        currency=str(_trial_product_field(product_ref, "currency", "CNY")),
        payable_amount=0,
        paid_amount=0,
        payment_provider="manual",
        channel="manual",
        provider_reference_id="",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=now,
        metadata_json=order_metadata,
    )

    db.session.add(subscription)
    db.session.flush()
    db.session.add(order)
    db.session.flush()

    granted = _grant_paid_order_credits(app, order)
    if not granted:
        raise RuntimeError("trial_order_credit_grant_failed")


def _resolve_trial_bootstrap_status(
    creator_bid: str,
    *,
    creator: UserEntity | None = None,
    product_ref: BillingProduct | dict[str, Any] | None = None,
) -> tuple[str, BillingProduct | dict[str, Any] | None]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return "invalid_creator_bid", None
    if not _is_billing_enabled():
        return "billing_disabled", None

    resolved_creator = creator or get_user_entity_by_bid(normalized_creator_bid)
    if resolved_creator is None:
        return "creator_not_found", None
    if not bool(resolved_creator.is_creator):
        return "not_creator", None

    resolved_product_ref = product_ref or _resolve_trial_product_reference()
    if resolved_product_ref is None:
        return "trial_product_missing", None
    if not _trial_product_public_enabled(resolved_product_ref):
        return "trial_product_not_public", resolved_product_ref

    if _load_active_creator_subscription(normalized_creator_bid) is not None:
        return "active_subscription_exists", resolved_product_ref
    if _load_trial_subscription(normalized_creator_bid) is not None:
        return "trial_subscription_exists", resolved_product_ref
    if _load_trial_order(normalized_creator_bid) is not None:
        return "trial_order_exists", resolved_product_ref
    if _load_legacy_trial_entry(normalized_creator_bid) is not None:
        return "legacy_trial_exists", resolved_product_ref

    return "grantable", resolved_product_ref


def _backfill_missing_creator_trial_credits(
    app: Flask,
    *,
    creator_bid: str = "",
    limit: int | None = None,
) -> dict[str, Any]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_limit = int(limit) if limit is not None and int(limit) > 0 else None

    with app.app_context():
        if not _is_billing_enabled():
            return {
                "status": "noop",
                "reason": "billing_disabled",
                "creator_bid": normalized_creator_bid or None,
                "limit": normalized_limit,
                "creator_count": 0,
                "granted_count": 0,
                "skipped_count": 0,
                "records": [],
            }

        product_ref = _resolve_trial_product_reference()
        if product_ref is None:
            return {
                "status": "noop",
                "reason": "trial_product_missing",
                "creator_bid": normalized_creator_bid or None,
                "limit": normalized_limit,
                "creator_count": 0,
                "granted_count": 0,
                "skipped_count": 0,
                "records": [],
            }
        if not _trial_product_public_enabled(product_ref):
            return {
                "status": "noop",
                "reason": "trial_product_not_public",
                "creator_bid": normalized_creator_bid or None,
                "limit": normalized_limit,
                "creator_count": 0,
                "granted_count": 0,
                "skipped_count": 0,
                "records": [],
            }

        creators: list[UserEntity] = []
        if normalized_creator_bid:
            creator = get_user_entity_by_bid(normalized_creator_bid)
            if creator is None:
                return {
                    "status": "completed",
                    "reason": None,
                    "creator_bid": normalized_creator_bid,
                    "limit": normalized_limit,
                    "trial_product_bid": str(
                        _trial_product_field(
                            product_ref,
                            "product_bid",
                            BILLING_TRIAL_PRODUCT_BID,
                        )
                    ),
                    "trial_product_code": str(
                        _trial_product_field(
                            product_ref,
                            "product_code",
                            BILLING_TRIAL_PRODUCT_CODE,
                        )
                    ),
                    "creator_count": 1,
                    "granted_count": 0,
                    "skipped_count": 1,
                    "records": [
                        {
                            "creator_bid": normalized_creator_bid,
                            "status": "skipped",
                            "reason": "creator_not_found",
                        }
                    ],
                }
            creators = [creator]
        else:
            creator_query = UserEntity.query.filter(
                UserEntity.deleted == 0,
                UserEntity.is_creator == 1,
            ).order_by(UserEntity.id.asc())
            if normalized_limit is not None:
                creator_query = creator_query.limit(normalized_limit)
            creators = creator_query.all()

        records: list[dict[str, Any]] = []
        granted_count = 0
        skipped_count = 0
        trial_product_bid = str(
            _trial_product_field(product_ref, "product_bid", BILLING_TRIAL_PRODUCT_BID)
        )
        trial_product_code = str(
            _trial_product_field(
                product_ref,
                "product_code",
                BILLING_TRIAL_PRODUCT_CODE,
            )
        )

        for creator in creators:
            current_creator_bid = _normalize_bid(getattr(creator, "user_bid", ""))
            status, resolved_product_ref = _resolve_trial_bootstrap_status(
                current_creator_bid,
                creator=creator,
                product_ref=product_ref,
            )
            if status != "grantable" or resolved_product_ref is None:
                records.append(
                    {
                        "creator_bid": current_creator_bid or None,
                        "status": "skipped",
                        "reason": status,
                    }
                )
                skipped_count += 1
                continue

            try:
                _bootstrap_trial_subscription(
                    app,
                    creator_bid=current_creator_bid,
                    product_ref=resolved_product_ref,
                    trigger="cli_backfill_missing_creator_trial",
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                records.append(
                    {
                        "creator_bid": current_creator_bid,
                        "status": "skipped",
                        "reason": "integrity_conflict",
                    }
                )
                skipped_count += 1
                continue

            records.append(
                {
                    "creator_bid": current_creator_bid,
                    "status": "granted",
                    "reason": None,
                }
            )
            granted_count += 1

        return {
            "status": "completed",
            "reason": None,
            "creator_bid": normalized_creator_bid or None,
            "limit": normalized_limit,
            "trial_product_bid": trial_product_bid,
            "trial_product_code": trial_product_code,
            "creator_count": len(creators) if not normalized_creator_bid else 1,
            "granted_count": granted_count,
            "skipped_count": skipped_count,
            "records": records,
        }


def _resolve_new_creator_trial_offer(
    app: Flask,
    creator_bid: str,
    *,
    trigger: str,
    timezone_name: str | None = None,
) -> BillingTrialOfferDTO:
    del trigger

    product_ref = _resolve_trial_product_reference()
    enabled = bool(product_ref) and _trial_product_public_enabled(product_ref)
    normalized_creator_bid = _normalize_bid(creator_bid)

    legacy_entry = _load_legacy_trial_entry(normalized_creator_bid)
    trial_subscription = _load_trial_subscription(normalized_creator_bid)
    trial_order = _load_trial_order(normalized_creator_bid)

    if (
        legacy_entry is not None
        or trial_subscription is not None
        or trial_order is not None
    ):
        granted_at, expires_at = _resolve_trial_period_from_history(
            subscription=trial_subscription,
            order=trial_order,
            legacy_entry=legacy_entry,
        )
        acknowledged_at = _resolve_trial_welcome_acknowledged_at_from_history(
            subscription=trial_subscription,
            order=trial_order,
            legacy_entry=legacy_entry,
        )
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                product_ref,
                enabled=enabled,
                status="granted",
                granted_at=granted_at,
                expires_at=expires_at,
                welcome_dialog_acknowledged_at=acknowledged_at,
            ),
            timezone_name=timezone_name,
        )

    if not enabled:
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                product_ref,
                enabled=False,
                status="disabled",
            ),
            timezone_name=timezone_name,
        )

    creator = get_user_entity_by_bid(normalized_creator_bid)
    if creator is None or not bool(creator.is_creator):
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                product_ref,
                enabled=True,
                status="ineligible",
            ),
            timezone_name=timezone_name,
        )

    current_subscription = _load_active_creator_subscription(normalized_creator_bid)
    if current_subscription is not None:
        return _serialize_trial_offer(
            app,
            _build_trial_offer_state(
                product_ref,
                enabled=True,
                status="ineligible",
            ),
            timezone_name=timezone_name,
        )

    return _serialize_trial_offer(
        app,
        _build_trial_offer_state(
            product_ref,
            enabled=True,
            status="eligible",
        ),
        timezone_name=timezone_name,
    )


def _serialize_trial_offer(
    app: Flask,
    state: TrialOfferState,
    *,
    timezone_name: str | None = None,
) -> BillingTrialOfferDTO:
    return state.to_dto(app, timezone_name=timezone_name)


def _acknowledge_trial_welcome_dialog(
    app: Flask,
    creator_bid: str,
    *,
    timezone_name: str | None = None,
) -> BillingTrialWelcomeAckDTO:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return BillingTrialWelcomeAckDTO(acknowledged=False, acknowledged_at=None)

    with app.app_context():
        trial_subscription = _load_trial_subscription(normalized_creator_bid)
        trial_order = _load_trial_order(normalized_creator_bid)
        legacy_entry = _load_legacy_trial_entry(normalized_creator_bid)

        if trial_subscription is None and trial_order is None and legacy_entry is None:
            return BillingTrialWelcomeAckDTO(
                acknowledged=False,
                acknowledged_at=None,
            )

        existing_acknowledged_at = _resolve_trial_welcome_acknowledged_at_from_history(
            subscription=trial_subscription,
            order=trial_order,
            legacy_entry=legacy_entry,
        )
        if existing_acknowledged_at is not None:
            return BillingTrialWelcomeAckDTO(
                acknowledged=True,
                acknowledged_at=_serialize_dt(
                    app,
                    existing_acknowledged_at,
                    timezone_name=timezone_name,
                ),
            )

        target_record = trial_subscription or trial_order or legacy_entry
        if target_record is None:
            return BillingTrialWelcomeAckDTO(
                acknowledged=False,
                acknowledged_at=None,
            )

        acknowledged_at = datetime.now()
        _set_trial_welcome_acknowledged_at(
            target_record,
            acknowledged_at=acknowledged_at,
        )
        db.session.add(target_record)
        db.session.commit()
        return BillingTrialWelcomeAckDTO(
            acknowledged=True,
            acknowledged_at=_serialize_dt(
                app,
                acknowledged_at,
                timezone_name=timezone_name,
            ),
        )


def _bootstrap_new_creator_trial_credits(app: Flask, creator_bid: str) -> None:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return

    with app.app_context():
        status, product_ref = _resolve_trial_bootstrap_status(normalized_creator_bid)
        if status != "grantable" or product_ref is None:
            return

        try:
            _bootstrap_trial_subscription(
                app,
                creator_bid=normalized_creator_bid,
                product_ref=product_ref,
                trigger="post_auth_creator_grant",
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        except Exception:
            db.session.rollback()
            raise


resolve_new_creator_trial_offer = _resolve_new_creator_trial_offer
bootstrap_new_creator_trial_credits = _bootstrap_new_creator_trial_credits
acknowledge_trial_welcome_dialog = _acknowledge_trial_welcome_dialog
backfill_missing_creator_trial_credits = _backfill_missing_creator_trial_credits

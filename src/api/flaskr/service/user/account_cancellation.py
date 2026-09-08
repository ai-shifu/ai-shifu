"""Operator-controlled user account cancellation lifecycle."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from flaskr.common.cache_provider import cache as redis
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.billing.api import (
    cancel_billing_subscription,
    cancel_subscription_renewal_events,
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    sync_credit_bucket_status,
)
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_INIT,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.consts import ORDER_STATUS_INIT, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order
from flaskr.service.profile.models import VariableValue
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import (
    AuthCredential,
    UserAccountCancellation,
    UserInfo,
    UserToken,
    UserVerifyCode,
)
from flaskr.util import generate_id
from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    from flask import Flask


REASON_MIN_LENGTH = 5
REASON_MAX_LENGTH = 500
ACTIVE_RENEWAL_STATUSES = {
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
}


def _mask_identifier(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if "@" in normalized:
        local, domain = normalized.split("@", maxsplit=1)
        return f"{local[:1]}***@{domain}" if local else f"***@{domain}"
    if len(normalized) >= 7:
        return f"{normalized[:3]}****{normalized[-4:]}"
    return f"{normalized[:1]}***"


def _latest_active_course_bids(model: object, user_bid: str) -> set[str]:
    rows = (
        db.session.query(model.shifu_bid)
        .filter(
            model.created_user_bid == user_bid,
            model.deleted == 0,
        )
        .distinct()
        .all()
    )
    return {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}


def _build_cancellation_state(user: UserInfo, operator_user_bid: str) -> dict[str, Any]:
    user_bid = str(user.user_bid or "").strip()
    draft_bids = _latest_active_course_bids(DraftShifu, user_bid)
    published_bids = _latest_active_course_bids(PublishedShifu, user_bid)
    draft_only_bids = draft_bids - published_bids

    published_rows = (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid.in_(published_bids),
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .all()
        if published_bids
        else []
    )
    published_courses: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in published_rows:
        shifu_bid = str(row.shifu_bid or "").strip()
        if not shifu_bid or shifu_bid in seen:
            continue
        seen.add(shifu_bid)
        published_courses.append(
            {"shifu_bid": shifu_bid, "course_name": str(row.title or "")}
        )

    renewal_count = BillingSubscription.query.filter(
        BillingSubscription.creator_bid == user_bid,
        BillingSubscription.status.in_(ACTIVE_RENEWAL_STATUSES),
        BillingSubscription.cancel_at_period_end == 0,
        BillingSubscription.deleted == 0,
    ).count()
    unsettled_billing_orders = BillingOrder.query.filter(
        BillingOrder.creator_bid == user_bid,
        BillingOrder.status.in_(
            [BILLING_ORDER_STATUS_INIT, BILLING_ORDER_STATUS_PENDING]
        ),
        BillingOrder.deleted == 0,
    ).count()
    unsettled_legacy_orders = Order.query.filter(
        Order.user_bid == user_bid,
        Order.status.in_([ORDER_STATUS_INIT, ORDER_STATUS_TO_BE_PAID]),
        Order.deleted == 0,
    ).count()
    wallet = CreditWallet.query.filter(
        CreditWallet.creator_bid == user_bid,
        CreditWallet.deleted == 0,
    ).first()
    available_credits = Decimal(str(getattr(wallet, "available_credits", 0) or 0))
    reserved_credits = Decimal(str(getattr(wallet, "reserved_credits", 0) or 0))
    active_session_count = UserToken.query.filter(UserToken.user_id == user_bid).count()

    blockers: list[dict[str, object]] = []
    if user_bid == str(operator_user_bid or "").strip():
        blockers.append({"code": "self", "count": 1})
    if bool(user.is_operator):
        blockers.append({"code": "operator", "count": 1})
    if published_courses:
        blockers.append(
            {
                "code": "published_course_transfer_required",
                "count": len(published_courses),
            }
        )
    if renewal_count:
        blockers.append(
            {"code": "subscription_cancellation_required", "count": renewal_count}
        )
    unsettled_order_count = unsettled_billing_orders + unsettled_legacy_orders
    if unsettled_order_count:
        blockers.append({"code": "unsettled_payment", "count": unsettled_order_count})

    warnings: list[dict[str, object]] = []
    if draft_only_bids:
        warnings.append({"code": "draft_courses_frozen", "count": len(draft_only_bids)})
    if available_credits > 0 or reserved_credits > 0:
        warnings.append({"code": "credits_forfeited", "count": 1})
    if active_session_count:
        warnings.append({"code": "sessions_revoked", "count": active_session_count})

    version_payload = {
        "user_bid": user_bid,
        "updated_at": user.updated_at.isoformat() if user.updated_at else "",
        "draft_only_bids": sorted(draft_only_bids),
        "published_bids": sorted(published_bids),
        "renewal_count": renewal_count,
        "unsettled_order_count": unsettled_order_count,
        "available_credits": str(available_credits),
        "reserved_credits": str(reserved_credits),
        "active_session_count": active_session_count,
    }
    preview_version = hashlib.sha256(
        json.dumps(version_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return {
        "user": {
            "user_bid": user_bid,
            "masked_identifier": _mask_identifier(user.user_identify),
            "nickname": str(user.nickname or ""),
            "is_creator": bool(user.is_creator),
            "is_operator": bool(user.is_operator),
        },
        "can_cancel": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "draft_course_count": len(draft_only_bids),
        "published_courses": published_courses,
        "subscription_renewal_count": renewal_count,
        "unsettled_order_count": unsettled_order_count,
        "available_credits": float(available_credits),
        "reserved_credits": float(reserved_credits),
        "active_session_count": active_session_count,
        "preview_version": preview_version,
    }


def get_account_cancellation_preview(
    app: Flask, *, user_bid: str, operator_user_bid: str
) -> dict[str, Any]:
    """Return the authoritative operator preflight for one active account."""
    with app_context_scope(app):
        normalized_user_bid = str(user_bid or "").strip()
        if not normalized_user_bid:
            raise_param_error("user_bid")
        user = UserInfo.query.filter(
            UserInfo.user_bid == normalized_user_bid,
            UserInfo.deleted == 0,
        ).first()
        if user is None:
            cancelled = UserAccountCancellation.query.filter_by(
                user_bid=normalized_user_bid
            ).first()
            if cancelled:
                raise_error("server.user.accountAlreadyCancelled")
            raise_error("server.user.userNotFound")
        return _build_cancellation_state(user, operator_user_bid)


def cancel_account_subscription_renewals(
    app: Flask, *, user_bid: str, operator_user_bid: str
) -> dict[str, Any]:
    """Cancel every future renewal before account cancellation can proceed."""
    with app_context_scope(app):
        preview = get_account_cancellation_preview(
            app, user_bid=user_bid, operator_user_bid=operator_user_bid
        )
        blocking_codes = {str(item.get("code") or "") for item in preview["blockers"]}
        if blocking_codes & {"self", "operator"}:
            raise_error("server.user.accountCancellationBlocked")

        subscriptions = BillingSubscription.query.filter(
            BillingSubscription.creator_bid == str(user_bid or "").strip(),
            BillingSubscription.status.in_(ACTIVE_RENEWAL_STATUSES),
            BillingSubscription.cancel_at_period_end == 0,
            BillingSubscription.deleted == 0,
        ).all()
        cancelled_count = 0
        for subscription in subscriptions:
            if str(subscription.billing_provider or "").strip().lower() == "manual":
                with unit_of_work():
                    subscription.cancel_at_period_end = 1
                    subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
                    subscription.updated_at = now_utc()
                    cancel_subscription_renewal_events(subscription.subscription_bid)
            else:
                cancel_billing_subscription(
                    app,
                    str(user_bid or "").strip(),
                    {"subscription_bid": subscription.subscription_bid},
                )
            cancelled_count += 1

        return {
            "cancelled_subscription_count": cancelled_count,
            "preview": get_account_cancellation_preview(
                app, user_bid=user_bid, operator_user_bid=operator_user_bid
            ),
        }


def _tombstone(prefix: str, business_id: object, max_length: int = 255) -> str:
    return f"cancelled:{prefix}:{business_id or ''!s}"[:max_length]


def cancel_user_account(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    cancellation_bid: str,
    idempotency_key: str,
    preview_version: str,
    reason: str,
) -> dict[str, Any]:
    """Cancel and de-identify one user after all preparatory work succeeds."""
    normalized_user_bid = str(user_bid or "").strip()
    normalized_operator_bid = str(operator_user_bid or "").strip()
    normalized_cancellation_bid = str(cancellation_bid or "").strip()
    normalized_idempotency_key = str(
        idempotency_key or normalized_cancellation_bid
    ).strip()
    normalized_reason = str(reason or "").strip()
    if not normalized_user_bid:
        raise_param_error("user_bid")
    if not normalized_operator_bid:
        raise_param_error("operator_user_bid")
    if not normalized_cancellation_bid:
        raise_param_error("cancellation_bid")
    if not normalized_idempotency_key:
        raise_param_error("idempotency_key")
    if not REASON_MIN_LENGTH <= len(normalized_reason) <= REASON_MAX_LENGTH:
        raise_param_error("reason")

    with app_context_scope(app):
        existing = UserAccountCancellation.query.filter(
            UserAccountCancellation.idempotency_key == normalized_idempotency_key
        ).first()
        if existing:
            if existing.user_bid != normalized_user_bid:
                raise_error("server.user.accountCancellationConflict")
            return {
                "cancellation_bid": existing.cancellation_bid,
                "user_bid": existing.user_bid,
                "status": existing.status,
                "cancelled_at": existing.completed_at,
            }

        tokens: list[str] = []
        completed_at = now_utc()
        with unit_of_work():
            user = (
                UserInfo.query.filter(UserInfo.user_bid == normalized_user_bid)
                .with_for_update()
                .first()
            )
            if user is None:
                raise_error("server.user.userNotFound")
            if user.deleted:
                if (
                    str(user.cancellation_bid or "").strip()
                    == normalized_cancellation_bid
                ):
                    return {
                        "cancellation_bid": normalized_cancellation_bid,
                        "user_bid": normalized_user_bid,
                        "status": "completed",
                        "cancelled_at": user.cancelled_at,
                    }
                raise_error("server.user.accountAlreadyCancelled")
            state = _build_cancellation_state(user, normalized_operator_bid)
            if state["preview_version"] != str(preview_version or "").strip():
                raise_error("server.user.accountCancellationPreviewStale")
            if state["blockers"]:
                raise_error("server.user.accountCancellationBlocked")

            token_rows = UserToken.query.filter(
                UserToken.user_id == normalized_user_bid
            ).all()
            tokens = [str(row.token or "") for row in token_rows if row.token]
            for row in token_rows:
                db.session.delete(row)

            credentials = AuthCredential.query.filter(
                AuthCredential.user_bid == normalized_user_bid
            ).all()
            verification_identifiers = {
                value
                for credential in credentials
                for value in (
                    str(credential.identifier or "").strip(),
                    str(credential.subject_id or "").strip(),
                )
                if value
            }
            original_identify = str(user.user_identify or "").strip()
            if original_identify:
                verification_identifiers.add(original_identify)
            if verification_identifiers:
                UserVerifyCode.query.filter(
                    db.or_(
                        UserVerifyCode.phone.in_(verification_identifiers),
                        UserVerifyCode.mail.in_(verification_identifiers),
                    )
                ).delete(synchronize_session=False)
            for credential in credentials:
                credential.subject_id = _tombstone("subject", credential.credential_bid)
                credential.identifier = _tombstone(
                    "identifier", credential.credential_bid
                )
                credential.raw_profile = "{}"
                credential.deleted = 1

            VariableValue.query.filter(
                VariableValue.user_bid == normalized_user_bid,
                VariableValue.shifu_bid == "",
            ).update(
                {VariableValue.value: "", VariableValue.deleted: 1},
                synchronize_session=False,
            )

            wallet = CreditWallet.query.filter(
                CreditWallet.creator_bid == normalized_user_bid,
                CreditWallet.deleted == 0,
            ).first()
            if wallet is not None:
                running_balance = Decimal(str(wallet.available_credits or 0))
                for bucket in CreditWalletBucket.query.filter(
                    CreditWalletBucket.creator_bid == normalized_user_bid,
                    CreditWalletBucket.deleted == 0,
                    CreditWalletBucket.available_credits > 0,
                ).all():
                    forfeited = Decimal(str(bucket.available_credits or 0))
                    bucket.available_credits = Decimal(0)
                    bucket.consumed_credits = (
                        Decimal(str(bucket.consumed_credits or 0)) + forfeited
                    )
                    running_balance -= forfeited
                    sync_credit_bucket_status(bucket)
                    db.session.add(
                        CreditLedgerEntry(
                            ledger_bid=generate_id(app),
                            creator_bid=normalized_user_bid,
                            wallet_bid=wallet.wallet_bid,
                            wallet_bucket_bid=bucket.wallet_bucket_bid,
                            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
                            source_type=CREDIT_SOURCE_TYPE_MANUAL,
                            source_bid=normalized_cancellation_bid,
                            idempotency_key=(
                                "account_cancellation:"
                                f"{normalized_cancellation_bid}:{bucket.wallet_bucket_bid}"
                            ),
                            amount=-forfeited,
                            balance_after=max(running_balance, Decimal(0)),
                            expires_at=bucket.effective_to,
                            consumable_from=bucket.effective_from,
                            metadata_json={
                                "reason": "account_cancellation",
                                "operator_user_bid": normalized_operator_bid,
                            },
                        )
                    )
                refresh_credit_wallet_snapshot(wallet)
                persist_credit_wallet_snapshot(
                    wallet,
                    available_credits=wallet.available_credits,
                    reserved_credits=wallet.reserved_credits,
                    updated_at=completed_at,
                )

            audit = UserAccountCancellation(
                cancellation_bid=normalized_cancellation_bid,
                user_bid=normalized_user_bid,
                operator_user_bid=normalized_operator_bid,
                actor_type="operator",
                reason=normalized_reason,
                status="completed",
                idempotency_key=normalized_idempotency_key,
                retention_snapshot={
                    "draft_course_count": state["draft_course_count"],
                    "published_course_count": len(state["published_courses"]),
                    "subscription_renewal_count": state["subscription_renewal_count"],
                    "unsettled_order_count": state["unsettled_order_count"],
                    "had_available_credits": state["available_credits"] > 0,
                    "had_reserved_credits": state["reserved_credits"] > 0,
                    "active_session_count": state["active_session_count"],
                },
                requested_at=completed_at,
                completed_at=completed_at,
            )
            db.session.add(audit)

            user.user_identify = _tombstone("user", normalized_user_bid)
            user.nickname = ""
            user.learner_profile = ""
            user.learner_profile_updated_at = None
            user.avatar = ""
            user.birthday = None
            user.language = ""
            user.is_creator = 0
            user.api_key = ""
            user.deleted = 1
            user.cancelled_at = completed_at
            user.cancellation_bid = normalized_cancellation_bid

        cache_prefix = app.config.get("REDIS_KEY_PREFIX_USER", "ai-shifu:user:")
        for token in tokens:
            try:
                redis.delete(f"{cache_prefix}{token}")
                redis.delete(f"{cache_prefix}{token}:row")
            except Exception:
                app.logger.exception(
                    "failed to evict a cancelled user's token cache entry"
                )

        return {
            "cancellation_bid": normalized_cancellation_bid,
            "user_bid": normalized_user_bid,
            "status": "completed",
            "cancelled_at": completed_at,
        }

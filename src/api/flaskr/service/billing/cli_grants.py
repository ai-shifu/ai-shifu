"""Operator plan and credit grants issued from the billing Flask CLI."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import click
from flask import current_app
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.user.repository import (
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    mark_user_roles,
)
from flaskr.util.uuid import generate_id

from .cli_support import _DEFAULT_CLI_OPERATOR_USER_BID, _serialize_cli_payload
from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
)
from .manual_credit_grants import grant_manual_credits_to_user
from .models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
)
from .notifications import stage_subscription_purchase_sms_for_paid_order
from .primitives import coerce_datetime
from .queries import (
    calculate_self_managed_billing_cycle_end,
    load_primary_active_subscription,
)
from .subscriptions import is_self_managed_billing_provider

if TYPE_CHECKING:
    from datetime import datetime
    from types import ModuleType


def _cli_facade() -> ModuleType:
    """Resolve collaborators through ``cli`` so its patch points stay live."""
    from . import cli

    return cli


def grant_billing_plan_by_identify(
    *,
    identify: str,
    product_bid: str = "",
    product_code: str = "",
    effective_to: str = "",
    note: str = "",
) -> dict[str, object]:
    """Grant billing plan by identify."""
    (
        normalized_identify,
        normalized_note,
        normalized_product_bid,
        normalized_product_code,
        normalized_effective_to,
    ) = _normalize_grant_plan_options(
        identify=identify,
        product_bid=product_bid,
        product_code=product_code,
        effective_to=effective_to,
        note=note,
    )
    cli = _cli_facade()

    with unit_of_work():
        aggregate = load_user_aggregate_by_identifier(normalized_identify)
        if aggregate is None:
            message = f"No user found for identify: {normalized_identify}"
            raise click.ClickException(message)

        product = _load_active_plan_product(
            product_bid=normalized_product_bid,
            product_code=normalized_product_code,
        )
        if product is None:
            error_message = "Active billing plan not found."
            raise click.ClickException(error_message)

        creator_role_granted = False
        if not bool(getattr(aggregate, "is_creator", False)):
            mark_user_roles(aggregate.user_bid, is_creator=True)
            creator_role_granted = True
            aggregate = load_user_aggregate(aggregate.user_bid) or aggregate

        existing_subscription = load_primary_active_subscription(
            aggregate.user_bid,
            as_of=cli.now_utc(),
        )
        order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_START
        if existing_subscription is not None:
            if (
                str(existing_subscription.product_bid or "").strip()
                == product.product_bid
            ):
                return _build_grant_plan_payload(
                    status="noop_active",
                    identify=normalized_identify,
                    aggregate=aggregate,
                    creator_role_granted=creator_role_granted,
                    product=product,
                    subscription=existing_subscription,
                    bill_order_bid=None,
                )
            _ensure_manual_grant_upgrade_allowed(existing_subscription, product)
            order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE

        granted_at = cli.now_utc()
        cycle_end_at = _resolve_manual_grant_cycle_end_at(
            product,
            normalized_effective_to=normalized_effective_to,
            granted_at=granted_at,
        )
        subscription_metadata, order_metadata = _build_manual_grant_metadata(
            cycle_end_at=cycle_end_at,
            normalized_effective_to=normalized_effective_to,
            normalized_note=normalized_note,
        )

        subscription = _stage_manual_grant_subscription(
            existing_subscription,
            creator_bid=aggregate.user_bid,
            product=product,
            granted_at=granted_at,
            cycle_end_at=cycle_end_at,
            subscription_metadata=subscription_metadata,
        )
        order = _stage_manual_grant_order(
            creator_bid=aggregate.user_bid,
            order_type=order_type,
            product=product,
            subscription=subscription,
            granted_at=granted_at,
            order_metadata=order_metadata,
        )

        granted = cli.grant_paid_order_credits(current_app, order)
        if not granted:
            error_message = "Manual plan grant did not create a new credit grant."
            raise click.ClickException(error_message)

        should_enqueue_subscription_purchase_sms = (
            stage_subscription_purchase_sms_for_paid_order(
                order,
                previous_status=None,
            )
        )
        cli._enforce_manual_subscription_expire_event(subscription)

    payload = _build_grant_plan_payload(
        status="granted",
        identify=normalized_identify,
        aggregate=aggregate,
        creator_role_granted=creator_role_granted,
        product=product,
        subscription=subscription,
        bill_order_bid=order.bill_order_bid,
    )
    if should_enqueue_subscription_purchase_sms:
        sms_payload = cli.enqueue_subscription_purchase_sms(
            current_app,
            bill_order_bid=order.bill_order_bid,
        )
        payload["sms_enqueue_status"] = str(sms_payload.get("status") or "")
        payload["sms_enqueued"] = bool(sms_payload.get("enqueued"))
    return payload


def _normalize_grant_plan_options(
    *,
    identify: str,
    product_bid: str,
    product_code: str,
    effective_to: str,
    note: str,
) -> tuple[str, str, str, str, str]:
    normalized_identify = str(identify or "").strip()
    if not normalized_identify:
        error_message = "--identify is required."
        raise click.ClickException(error_message)

    normalized_note = str(note or "").strip()
    if len(normalized_note) > 255:
        error_message = "--note must be 255 characters or fewer."
        raise click.ClickException(error_message)

    normalized_product_bid = str(product_bid or "").strip()
    normalized_product_code = str(product_code or "").strip()
    if bool(normalized_product_bid) == bool(normalized_product_code):
        error_message = "Pass exactly one of --product-bid or --product-code."
        raise click.ClickException(error_message)
    normalized_effective_to = str(effective_to or "").strip()
    return (
        normalized_identify,
        normalized_note,
        normalized_product_bid,
        normalized_product_code,
        normalized_effective_to,
    )


def _ensure_manual_grant_upgrade_allowed(
    existing_subscription: BillingSubscription,
    product: BillingProduct,
) -> None:
    current_product = _load_plan_product_by_bid(existing_subscription.product_bid)
    if not is_self_managed_billing_provider(existing_subscription.billing_provider):
        error_message = (
            "User already has an active provider-managed subscription. "
            "Use the normal checkout upgrade flow or wait for the current cycle to expire."
        )
        raise click.ClickException(error_message)
    if current_product is None:
        error_message = "Active billing plan not found for the current subscription."
        raise click.ClickException(error_message)
    if int(product.sort_order or 0) <= int(current_product.sort_order or 0):
        error_message = (
            "The current subscription is still active. "
            "Operator grant only supports upgrades to a higher-tier plan."
        )
        raise click.ClickException(error_message)


def _resolve_manual_grant_cycle_end_at(
    product: BillingProduct,
    *,
    normalized_effective_to: str,
    granted_at: datetime,
) -> datetime:
    cycle_end_at = (
        _parse_effective_to_option(normalized_effective_to)
        if normalized_effective_to
        else calculate_self_managed_billing_cycle_end(
            product,
            cycle_start_at=granted_at,
        )
    )
    if cycle_end_at is None:
        error_message = "Target product does not support one-cycle manual activation."
        raise click.ClickException(error_message)
    if cycle_end_at <= granted_at:
        error_message = "--effective-to must be later than now."
        raise click.ClickException(error_message)
    return cycle_end_at


def _build_manual_grant_metadata(
    *,
    cycle_end_at: datetime,
    normalized_effective_to: str,
    normalized_note: str,
) -> tuple[dict[str, object], dict[str, object]]:
    subscription_metadata = {
        "manual_grant": True,
        "manual_grant_source": "cli",
    }
    if normalized_effective_to:
        subscription_metadata["manual_grant_effective_to"] = cycle_end_at.isoformat()
    if normalized_note:
        subscription_metadata["manual_grant_note"] = normalized_note

    order_metadata = {
        "checkout_type": "manual_grant",
        "manual_grant": True,
        "manual_grant_source": "cli",
    }
    if normalized_effective_to:
        order_metadata["effective_to"] = cycle_end_at.isoformat()
        order_metadata["applied_cycle_end_at"] = cycle_end_at.isoformat()
    if normalized_note:
        order_metadata["note"] = normalized_note
    return subscription_metadata, order_metadata


def _stage_manual_grant_subscription(
    existing_subscription: BillingSubscription | None,
    *,
    creator_bid: str,
    product: BillingProduct,
    granted_at: datetime,
    cycle_end_at: datetime,
    subscription_metadata: dict[str, object],
) -> BillingSubscription:
    if existing_subscription is None:
        subscription = BillingSubscription(
            subscription_bid=generate_id(current_app),
            creator_bid=creator_bid,
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
            billing_provider="manual",
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=granted_at,
            current_period_start_at=granted_at,
            current_period_end_at=cycle_end_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=None,
            last_failed_at=None,
            metadata_json=subscription_metadata,
        )
    else:
        subscription = existing_subscription
        subscription.metadata_json = {
            **(
                subscription.metadata_json
                if isinstance(subscription.metadata_json, dict)
                else {}
            ),
            **subscription_metadata,
        }
        subscription.updated_at = granted_at
    db.session.add(subscription)
    db.session.flush()
    return subscription


def _stage_manual_grant_order(
    *,
    creator_bid: str,
    order_type: int,
    product: BillingProduct,
    subscription: BillingSubscription,
    granted_at: datetime,
    order_metadata: dict[str, object],
) -> BillingOrder:
    order = BillingOrder(
        bill_order_bid=generate_id(current_app),
        creator_bid=creator_bid,
        order_type=order_type,
        product_bid=product.product_bid,
        subscription_bid=subscription.subscription_bid,
        currency=product.currency,
        payable_amount=0,
        paid_amount=0,
        payment_provider="manual",
        channel="manual",
        provider_reference_id="",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=granted_at,
        metadata_json=order_metadata,
    )
    db.session.add(order)
    db.session.flush()
    return order


def _build_grant_plan_payload(
    *,
    status: str,
    identify: str,
    aggregate: object,
    creator_role_granted: bool,
    product: BillingProduct,
    subscription: BillingSubscription,
    bill_order_bid: str | None,
) -> dict[str, object]:
    return {
        "status": status,
        "identify": identify,
        "creator_bid": aggregate.user_bid,
        "creator_role_granted": creator_role_granted,
        "product_bid": product.product_bid,
        "product_code": product.product_code,
        "subscription_bid": subscription.subscription_bid,
        "bill_order_bid": bill_order_bid,
        "billing_provider": subscription.billing_provider,
        "current_period_start_at": subscription.current_period_start_at,
        "current_period_end_at": subscription.current_period_end_at,
        "email": aggregate.email,
        "mobile": aggregate.mobile,
    }


def grant_operator_credits_by_cli(
    *,
    identify: str = "",
    user_bid: str = "",
    amount: str,
    request_id: str,
    grant_source: str = "compensation",
    validity_value: int,
    validity_unit: str,
    display_name: str = "",
    note: str = "",
    operator_user_bid: str = "",
) -> dict[str, object]:
    """Grant operator credits by CLI."""
    normalized_identify = str(identify or "").strip()
    normalized_user_bid = str(user_bid or "").strip()
    if bool(normalized_identify) == bool(normalized_user_bid):
        error_message = "Pass exactly one of --identify or --user-bid."
        raise click.ClickException(error_message)

    normalized_request_id = str(request_id or "").strip()
    if len(normalized_request_id) > 100:
        error_message = "--request-id must be 100 characters or fewer."
        raise click.ClickException(error_message)

    normalized_display_name = str(display_name or "").strip()
    if len(normalized_display_name) > 128:
        error_message = "--name must be 128 characters or fewer."
        raise click.ClickException(error_message)

    normalized_note = str(note or "").strip()
    if len(normalized_note) > 255:
        error_message = "--note must be 255 characters or fewer."
        raise click.ClickException(error_message)

    normalized_operator_user_bid = (
        str(operator_user_bid or "").strip() or _DEFAULT_CLI_OPERATOR_USER_BID
    )

    # The manual grant owns its own idempotent unit of work; no outer block.
    aggregate = (
        load_user_aggregate(normalized_user_bid)
        if normalized_user_bid
        else load_user_aggregate_by_identifier(normalized_identify)
    )
    if aggregate is None:
        target = normalized_user_bid or normalized_identify
        message = f"No user found for target: {target}"
        raise click.ClickException(message)
    if not normalized_request_id:
        normalized_request_id = _build_cli_credit_grant_request_id(
            user_bid=aggregate.user_bid,
            amount=amount,
            grant_source=grant_source,
            validity_value=validity_value,
            validity_unit=validity_unit,
            display_name=normalized_display_name,
            note=normalized_note,
        )

    grant_result = grant_manual_credits_to_user(
        current_app,
        user_bid=aggregate.user_bid,
        operator_user_bid=normalized_operator_user_bid,
        request_id=normalized_request_id,
        amount=str(amount or "").strip(),
        grant_source=str(grant_source or "").strip(),
        validity_value=validity_value,
        validity_unit=validity_unit,
        display_name=normalized_display_name,
        note=normalized_note,
        grant_channel="operator_cli",
    )
    payload = dict(_serialize_cli_payload(grant_result))
    payload.update(
        {
            "identify": normalized_identify,
            "creator_bid": aggregate.user_bid,
            "operator_user_bid": normalized_operator_user_bid,
            "request_id": normalized_request_id,
            "email": getattr(aggregate, "email", ""),
            "mobile": getattr(aggregate, "mobile", ""),
        }
    )
    return payload


def _build_cli_credit_grant_request_id(
    *,
    user_bid: str,
    amount: str,
    grant_source: str,
    validity_value: int,
    validity_unit: str,
    display_name: str,
    note: str,
) -> str:
    fingerprint_payload = "|".join(
        [
            str(user_bid or "").strip(),
            str(amount or "").strip(),
            str(grant_source or "").strip().lower(),
            # Preserve existing duration-based IDs across the preset removal.
            "custom",
            str(validity_value),
            validity_unit,
            str(display_name or "").strip(),
            str(note or "").strip(),
        ]
    )
    fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()[:16]
    return f"cli:{_cli_facade().now_utc():%Y%m%d}:{fingerprint}"


def _load_active_plan_product(
    *,
    product_bid: str = "",
    product_code: str = "",
) -> BillingProduct | None:
    normalized_product_bid = str(product_bid or "").strip()
    normalized_product_code = str(product_code or "").strip()

    query = BillingProduct.query.filter(
        BillingProduct.deleted == 0,
        BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
        BillingProduct.product_type == BILLING_PRODUCT_TYPE_PLAN,
    )
    if normalized_product_bid:
        query = query.filter(BillingProduct.product_bid == normalized_product_bid)
    elif normalized_product_code:
        query = query.filter(BillingProduct.product_code == normalized_product_code)
    else:
        return None

    return query.order_by(BillingProduct.id.desc()).first()


def _load_plan_product_by_bid(product_bid: str) -> BillingProduct | None:
    normalized_product_bid = str(product_bid or "").strip()
    if not normalized_product_bid:
        return None

    return (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == normalized_product_bid,
            BillingProduct.product_type == BILLING_PRODUCT_TYPE_PLAN,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )


def _parse_effective_to_option(raw_value: str) -> datetime:
    parsed = coerce_datetime(raw_value)
    if parsed is None:
        message = "--effective-to must be a valid ISO-8601 datetime or YYYY-MM-DD."
        raise click.ClickException(message)
    return parsed


def _enforce_manual_subscription_expire_event(
    subscription: BillingSubscription,
) -> None:
    scheduled_at = subscription.current_period_end_at
    if scheduled_at is None:
        return

    pending_statuses = (
        BILLING_RENEWAL_EVENT_STATUS_PENDING,
        BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
        BILLING_RENEWAL_EVENT_STATUS_FAILED,
    )
    payload = {
        "subscription_bid": subscription.subscription_bid,
        "creator_bid": subscription.creator_bid,
        "product_bid": subscription.product_bid,
        "next_product_bid": str(subscription.next_product_bid or "").strip() or None,
        "status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(
            int(subscription.status or 0),
            "active",
        ),
        "cancel_at_period_end": bool(subscription.cancel_at_period_end),
        "manual_grant": True,
    }
    now = _cli_facade().now_utc()
    expire_event: BillingRenewalEvent | None = None
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription.subscription_bid,
            BillingRenewalEvent.status.in_(pending_statuses),
        )
        .order_by(BillingRenewalEvent.id.desc())
        .all()
    )

    for row in rows:
        if (
            row.event_type == BILLING_RENEWAL_EVENT_TYPE_EXPIRE
            and row.scheduled_at == scheduled_at
        ):
            expire_event = row
            continue
        row.status = BILLING_RENEWAL_EVENT_STATUS_CANCELED
        row.processed_at = now
        row.updated_at = now
        db.session.add(row)

    if expire_event is None:
        expire_event = BillingRenewalEvent(
            renewal_event_bid=generate_id(current_app),
            subscription_bid=subscription.subscription_bid,
            creator_bid=subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=scheduled_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json=payload,
            processed_at=None,
        )
    else:
        expire_event.creator_bid = subscription.creator_bid
        expire_event.status = BILLING_RENEWAL_EVENT_STATUS_PENDING
        expire_event.last_error = ""
        expire_event.payload_json = payload
        expire_event.processed_at = None
        expire_event.updated_at = now

    db.session.add(expire_event)

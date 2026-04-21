"""Flask CLI entrypoints for offline billing repair and replay work."""

from __future__ import annotations

from dataclasses import asdict
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import click
from flask import current_app
from flask.cli import with_appcontext
from flaskr.dao import db
from flaskr.service.config.models import Config
from flaskr.service.user.repository import (
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    mark_user_roles,
)
from flaskr.util.uuid import generate_id

from .checkout import reconcile_billing_provider_reference
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
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_STATUS_INACTIVE,
    BILLING_PRODUCT_TYPE_CUSTOM,
    BILLING_PRODUCT_TYPE_GRANT,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
    BILL_SYS_CONFIG_SEEDS,
    CREDIT_USAGE_RATE_SEEDS,
)
from .daily_aggregates import (
    detect_daily_aggregate_rebuild_range,
    rebuild_daily_aggregates,
)
from .models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditUsageRate,
)
from .notifications import (
    enqueue_subscription_purchase_sms,
    requeue_subscription_purchase_sms,
    stage_subscription_purchase_sms_for_paid_order,
)
from .primitives import coerce_datetime
from .queries import calculate_billing_cycle_end, load_primary_active_subscription
from .renewal import retry_billing_renewal_event, run_billing_renewal_event
from .settlement import backfill_bill_usage_settlement
from .subscriptions import (
    grant_paid_order_credits,
    repair_subscription_cycle_mismatches,
    repair_topup_grant_expiries,
)
from .trials import backfill_missing_creator_trial_credits
from .wallets import rebuild_credit_wallet_snapshots

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


def register_billing_commands(console) -> None:
    """Register offline billing maintenance commands under ``flask console``."""

    @console.group(name="billing")
    def billing_group():
        """Billing maintenance commands for offline repair and replay."""

    @billing_group.command(name="seed-bootstrap-data")
    @with_appcontext
    def seed_bootstrap_data_command() -> None:
        """Upsert billing bootstrap rates and config rows."""

        _echo_payload(seed_billing_bootstrap_data())

    @billing_group.command(name="upsert-product")
    @click.option("--product-bid", required=True, help="Bill product bid.")
    @click.option("--product-code", required=True, help="Product code.")
    @click.option(
        "--product-type",
        "product_type_label",
        required=True,
        type=click.Choice(sorted(_PRODUCT_TYPE_LABELS.keys()), case_sensitive=False),
        help="Product type label.",
    )
    @click.option(
        "--billing-mode",
        "billing_mode_label",
        required=True,
        type=click.Choice(sorted(_BILLING_MODE_LABELS.keys()), case_sensitive=False),
        help="Billing mode label.",
    )
    @click.option(
        "--billing-interval",
        "billing_interval_label",
        required=True,
        type=click.Choice(
            sorted(_BILLING_INTERVAL_LABELS.keys()), case_sensitive=False
        ),
        help="Billing interval label.",
    )
    @click.option(
        "--billing-interval-count",
        type=int,
        default=0,
        show_default=True,
        help="Billing interval count.",
    )
    @click.option("--display-name-i18n-key", required=True, help="Display title key.")
    @click.option(
        "--description-i18n-key",
        required=True,
        help="Display description key.",
    )
    @click.option("--currency", default="CNY", show_default=True, help="Currency.")
    @click.option("--price-amount", type=int, required=True, help="Price amount.")
    @click.option(
        "--credit-amount",
        required=True,
        help="Credit amount as decimal string.",
    )
    @click.option(
        "--allocation-interval",
        "allocation_interval_label",
        required=True,
        type=click.Choice(
            sorted(_ALLOCATION_INTERVAL_LABELS.keys()), case_sensitive=False
        ),
        help="Allocation interval label.",
    )
    @click.option(
        "--auto-renew-enabled",
        type=click.IntRange(0, 1),
        default=0,
        show_default=True,
        help="Whether auto renew is enabled.",
    )
    @click.option(
        "--status",
        "status_label",
        default="active",
        show_default=True,
        type=click.Choice(sorted(_PRODUCT_STATUS_LABELS.keys()), case_sensitive=False),
        help="Product status label.",
    )
    @click.option(
        "--sort-order",
        type=int,
        default=0,
        show_default=True,
        help="Catalog sort order.",
    )
    @click.option(
        "--entitlement-json",
        default="",
        help="Optional entitlement payload JSON object.",
    )
    @click.option(
        "--metadata-json",
        default="",
        help="Optional metadata JSON object.",
    )
    @with_appcontext
    def upsert_product_command(
        product_bid: str,
        product_code: str,
        product_type_label: str,
        billing_mode_label: str,
        billing_interval_label: str,
        billing_interval_count: int,
        display_name_i18n_key: str,
        description_i18n_key: str,
        currency: str,
        price_amount: int,
        credit_amount: str,
        allocation_interval_label: str,
        auto_renew_enabled: int,
        status_label: str,
        sort_order: int,
        entitlement_json: str,
        metadata_json: str,
    ) -> None:
        """Create or update one bill product from CLI-supplied values."""

        payload = upsert_billing_product(
            product_bid=product_bid,
            product_code=product_code,
            product_type_label=product_type_label,
            billing_mode_label=billing_mode_label,
            billing_interval_label=billing_interval_label,
            billing_interval_count=billing_interval_count,
            display_name_i18n_key=display_name_i18n_key,
            description_i18n_key=description_i18n_key,
            currency=currency,
            price_amount=price_amount,
            credit_amount=credit_amount,
            allocation_interval_label=allocation_interval_label,
            auto_renew_enabled=auto_renew_enabled,
            status_label=status_label,
            sort_order=sort_order,
            entitlement_json=entitlement_json,
            metadata_json=metadata_json,
        )
        _echo_payload(payload)

    @billing_group.command(name="grant-plan")
    @click.option(
        "--identify",
        required=True,
        help="User identify value, usually phone or email.",
    )
    @click.option("--product-bid", default="", help="Billing plan bid.")
    @click.option("--product-code", default="", help="Billing plan code.")
    @click.option(
        "--effective-to",
        default="",
        help="Optional end datetime (ISO-8601 or YYYY-MM-DD).",
    )
    @click.option("--note", default="", help="Optional audit note.")
    @with_appcontext
    def grant_plan_command(
        identify: str,
        product_bid: str,
        product_code: str,
        effective_to: str,
        note: str,
    ) -> None:
        """Grant one billing plan to a user resolved by phone or email."""

        payload = grant_billing_plan_by_identify(
            identify=identify,
            product_bid=product_bid,
            product_code=product_code,
            effective_to=effective_to,
            note=note,
        )
        _echo_payload(payload)

    @billing_group.command(name="backfill-trial-plans")
    @click.option("--creator-bid", default="", help="Grant one creator only.")
    @click.option(
        "--limit",
        type=click.IntRange(min=1),
        default=None,
        help="Maximum creator rows to scan when used with --all.",
    )
    @click.option(
        "--all",
        "process_all",
        is_flag=True,
        help="Scan creator users and grant the missing public trial plan.",
    )
    @with_appcontext
    def backfill_trial_plans_command(
        creator_bid: str,
        limit: int | None,
        process_all: bool,
    ) -> None:
        """Grant the configured public trial plan to creators who still miss it."""

        if not str(creator_bid or "").strip() and not process_all:
            raise click.ClickException(
                "Pass --creator-bid or --all for trial plan backfill."
            )

        payload = backfill_missing_creator_trial_credits(
            current_app,
            creator_bid=creator_bid,
            limit=limit if process_all else None,
        )
        _echo_payload(payload)

    @billing_group.command(name="backfill-settlement")
    @click.option("--creator-bid", default="", help="Limit to one creator.")
    @click.option("--usage-bid", default="", help="Replay one usage bid directly.")
    @click.option("--usage-id-start", type=int, default=None, help="Start usage id.")
    @click.option("--usage-id-end", type=int, default=None, help="End usage id.")
    @click.option(
        "--limit",
        type=int,
        default=None,
        help="Maximum usages to process for one range run.",
    )
    @click.option(
        "--all",
        "process_all",
        is_flag=True,
        help="Replay every usage when no usage filters are provided.",
    )
    @with_appcontext
    def backfill_settlement_command(
        creator_bid: str,
        usage_bid: str,
        usage_id_start: int | None,
        usage_id_end: int | None,
        limit: int | None,
        process_all: bool,
    ) -> None:
        """Backfill or manually replay usage settlement from the CLI."""

        if (
            not str(usage_bid or "").strip()
            and usage_id_start is None
            and usage_id_end is None
            and not process_all
        ):
            raise click.ClickException(
                "Pass --usage-bid, a usage id range, or --all for settlement backfill."
            )

        payload = backfill_bill_usage_settlement(
            current_app,
            creator_bid=creator_bid,
            usage_bid=usage_bid,
            usage_id_start=usage_id_start,
            usage_id_end=usage_id_end,
            limit=limit,
        )
        _echo_payload(payload)

    @billing_group.command(name="rebuild-wallets")
    @click.option("--creator-bid", default="", help="Limit to one creator.")
    @click.option("--wallet-bid", default="", help="Rebuild one wallet snapshot.")
    @click.option(
        "--all",
        "process_all",
        is_flag=True,
        help="Rebuild every billing wallet snapshot.",
    )
    @with_appcontext
    def rebuild_wallets_command(
        creator_bid: str,
        wallet_bid: str,
        process_all: bool,
    ) -> None:
        """Rebuild wallet snapshots from bucket balances."""

        if (
            not str(creator_bid or "").strip()
            and not str(wallet_bid or "").strip()
            and not process_all
        ):
            raise click.ClickException(
                "Pass --creator-bid, --wallet-bid, or --all for wallet rebuild."
            )

        payload = rebuild_credit_wallet_snapshots(
            current_app,
            creator_bid=creator_bid,
            wallet_bid=wallet_bid,
        )
        _echo_payload(payload)

    @billing_group.command(name="repair-topup-expiry")
    @click.option("--creator-bid", default="", help="Repair one creator.")
    @with_appcontext
    def repair_topup_expiry_command(creator_bid: str) -> None:
        """Repair one creator's topup grant expiry against the active paid plan."""

        if not str(creator_bid or "").strip():
            raise click.ClickException("Pass --creator-bid for topup expiry repair.")

        payload = repair_topup_grant_expiries(
            current_app,
            creator_bid=creator_bid,
        )
        _echo_payload(payload)

    @billing_group.command(name="repair-subscription-cycle")
    @click.option("--creator-bid", default="", help="Repair one creator.")
    @click.option("--subscription-bid", default="", help="Repair one subscription.")
    @with_appcontext
    def repair_subscription_cycle_command(
        creator_bid: str,
        subscription_bid: str,
    ) -> None:
        """Repair mismatched subscription cycle rows from paid billing grants."""

        if (
            not str(creator_bid or "").strip()
            and not str(subscription_bid or "").strip()
        ):
            raise click.ClickException(
                "Pass --creator-bid or --subscription-bid for subscription cycle repair."
            )

        payload = repair_subscription_cycle_mismatches(
            current_app,
            creator_bid=creator_bid,
            subscription_bid=subscription_bid,
        )
        _echo_payload(payload)

    @billing_group.command(name="rebuild-daily-aggregates")
    @click.option("--creator-bid", default="", help="Limit to one creator.")
    @click.option("--shifu-bid", default="", help="Limit usage aggregate to one shifu.")
    @click.option("--date-from", default="", help="Start date in YYYY-MM-DD.")
    @click.option("--date-to", default="", help="End date in YYYY-MM-DD.")
    @click.option(
        "--all",
        "process_all",
        is_flag=True,
        help="Infer the full available date range from raw usage / ledger data.",
    )
    @with_appcontext
    def rebuild_daily_aggregates_command(
        creator_bid: str,
        shifu_bid: str,
        date_from: str,
        date_to: str,
        process_all: bool,
    ) -> None:
        """Rebuild one daily aggregate date window from raw usage and ledger data."""

        normalized_date_from = str(date_from or "").strip()
        normalized_date_to = str(date_to or "").strip()
        if not process_all and not normalized_date_from and not normalized_date_to:
            raise click.ClickException(
                "Pass --date-from/--date-to or --all for daily aggregate rebuild."
            )

        if process_all:
            detected_date_from, detected_date_to = detect_daily_aggregate_rebuild_range(
                current_app,
                creator_bid=creator_bid,
                shifu_bid=shifu_bid,
            )
            normalized_date_from = normalized_date_from or str(detected_date_from or "")
            normalized_date_to = normalized_date_to or str(detected_date_to or "")
            if not normalized_date_from or not normalized_date_to:
                _echo_payload(
                    {
                        "status": "noop",
                        "creator_bid": str(creator_bid or "").strip() or None,
                        "shifu_bid": str(shifu_bid or "").strip() or None,
                        "date_from": None,
                        "date_to": None,
                        "day_count": 0,
                    }
                )
                return

        payload = rebuild_daily_aggregates(
            current_app,
            creator_bid=creator_bid,
            shifu_bid=shifu_bid,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
        )
        _echo_payload(payload)

    @billing_group.command(name="reconcile-order")
    @click.option("--creator-bid", default="", help="Limit to one creator.")
    @click.option("--payment-provider", default="", help="Provider name.")
    @click.option(
        "--provider-reference-id",
        default="",
        help="Provider reference such as Stripe session id.",
    )
    @click.option("--bill-order-bid", default="", help="Bill order bid.")
    @click.option("--session-id", default="", help="Optional Stripe session id.")
    @with_appcontext
    def reconcile_order_command(
        creator_bid: str,
        payment_provider: str,
        provider_reference_id: str,
        bill_order_bid: str,
        session_id: str,
    ) -> None:
        """Manually replay provider sync for one billing order."""

        if (
            not str(bill_order_bid or "").strip()
            and not str(provider_reference_id or "").strip()
        ):
            raise click.ClickException(
                "Pass --bill-order-bid or --provider-reference-id for reconciliation."
            )

        payload = reconcile_billing_provider_reference(
            current_app,
            creator_bid=creator_bid,
            payment_provider=payment_provider,
            provider_reference_id=provider_reference_id,
            bill_order_bid=bill_order_bid,
            session_id=session_id,
        )
        _echo_payload(payload)

    @billing_group.command(name="run-renewal-event")
    @click.option("--renewal-event-bid", default="", help="Renewal event bid.")
    @click.option("--subscription-bid", default="", help="Subscription bid.")
    @click.option("--creator-bid", default="", help="Creator bid.")
    @with_appcontext
    def run_renewal_event_command(
        renewal_event_bid: str,
        subscription_bid: str,
        creator_bid: str,
    ) -> None:
        """Run one renewal/reconcile event from the CLI."""

        if not any(
            (
                str(renewal_event_bid or "").strip(),
                str(subscription_bid or "").strip(),
                str(creator_bid or "").strip(),
            )
        ):
            raise click.ClickException(
                "Pass a renewal event, subscription, or creator target."
            )

        payload = run_billing_renewal_event(
            current_app,
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )
        _echo_payload(payload)

    @billing_group.command(name="retry-renewal")
    @click.option("--renewal-event-bid", default="", help="Renewal event bid.")
    @click.option("--subscription-bid", default="", help="Subscription bid.")
    @click.option("--creator-bid", default="", help="Creator bid.")
    @click.option("--bill-order-bid", default="", help="Bill order bid.")
    @with_appcontext
    def retry_renewal_command(
        renewal_event_bid: str,
        subscription_bid: str,
        creator_bid: str,
        bill_order_bid: str,
    ) -> None:
        """Retry a failed renewal using the shared billing compensation path."""

        if not any(
            (
                str(renewal_event_bid or "").strip(),
                str(subscription_bid or "").strip(),
                str(creator_bid or "").strip(),
                str(bill_order_bid or "").strip(),
            )
        ):
            raise click.ClickException(
                "Pass a renewal event, subscription, creator, or bill order target."
            )

        payload = retry_billing_renewal_event(
            current_app,
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            bill_order_bid=bill_order_bid,
        )
        _echo_payload(payload)

    @billing_group.command(name="requeue-subscription-purchase-sms")
    @click.option("--bill-order-bid", default="", help="Bill order bid.")
    @with_appcontext
    def requeue_subscription_purchase_sms_command(
        bill_order_bid: str,
    ) -> None:
        """Re-enqueue one pending or provider-failed subscription purchase SMS."""

        if not str(bill_order_bid or "").strip():
            raise click.ClickException(
                "Pass --bill-order-bid for subscription purchase SMS requeue."
            )

        payload = requeue_subscription_purchase_sms(
            current_app,
            bill_order_bid=bill_order_bid,
        )
        _echo_payload(payload)


def seed_billing_bootstrap_data() -> dict[str, Any]:
    rate_result = _upsert_bootstrap_rows(
        model=CreditUsageRate,
        key_field="rate_bid",
        rows=[asdict(row) for row in CREDIT_USAGE_RATE_SEEDS],
    )
    config_result = _upsert_bootstrap_rows(
        model=Config,
        key_field="key",
        rows=[dict(row) for row in BILL_SYS_CONFIG_SEEDS],
    )
    db.session.commit()
    return {
        "status": "seeded",
        "products": {"count": 0, "inserted": 0, "updated": 0},
        "rates": rate_result,
        "configs": config_result,
    }


def upsert_billing_product(
    *,
    product_bid: str,
    product_code: str,
    product_type_label: str,
    billing_mode_label: str,
    billing_interval_label: str,
    billing_interval_count: int,
    display_name_i18n_key: str,
    description_i18n_key: str,
    currency: str,
    price_amount: int,
    credit_amount: str,
    allocation_interval_label: str,
    auto_renew_enabled: int,
    status_label: str,
    sort_order: int,
    entitlement_json: str,
    metadata_json: str,
) -> dict[str, Any]:
    payload = {
        "product_bid": str(product_bid or "").strip(),
        "product_code": str(product_code or "").strip(),
        "product_type": _PRODUCT_TYPE_LABELS[str(product_type_label or "").lower()],
        "billing_mode": _BILLING_MODE_LABELS[str(billing_mode_label or "").lower()],
        "billing_interval": _BILLING_INTERVAL_LABELS[
            str(billing_interval_label or "").lower()
        ],
        "billing_interval_count": int(billing_interval_count or 0),
        "display_name_i18n_key": str(display_name_i18n_key or "").strip(),
        "description_i18n_key": str(description_i18n_key or "").strip(),
        "currency": str(currency or "").strip().upper() or "CNY",
        "price_amount": int(price_amount),
        "credit_amount": Decimal(str(credit_amount or "0").strip()),
        "allocation_interval": _ALLOCATION_INTERVAL_LABELS[
            str(allocation_interval_label or "").lower()
        ],
        "auto_renew_enabled": int(auto_renew_enabled),
        "entitlement_payload": _parse_optional_json_object(
            entitlement_json,
            option_name="entitlement-json",
        ),
        "metadata_json": _parse_optional_json_object(
            metadata_json,
            option_name="metadata-json",
        ),
        "status": _PRODUCT_STATUS_LABELS[str(status_label or "").lower()],
        "sort_order": int(sort_order),
        "deleted": 0,
    }

    if not payload["product_bid"]:
        raise click.ClickException("--product-bid is required.")
    if not payload["product_code"]:
        raise click.ClickException("--product-code is required.")
    if not payload["display_name_i18n_key"]:
        raise click.ClickException("--display-name-i18n-key is required.")
    if not payload["description_i18n_key"]:
        raise click.ClickException("--description-i18n-key is required.")

    created = _upsert_bootstrap_row(
        model=BillingProduct,
        key_field="product_bid",
        payload=payload,
    )
    db.session.commit()
    return {
        "status": "upserted",
        "created": created,
        "product_bid": payload["product_bid"],
        "product_code": payload["product_code"],
    }


def grant_billing_plan_by_identify(
    *,
    identify: str,
    product_bid: str = "",
    product_code: str = "",
    effective_to: str = "",
    note: str = "",
) -> dict[str, Any]:
    normalized_identify = str(identify or "").strip()
    if not normalized_identify:
        raise click.ClickException("--identify is required.")

    normalized_note = str(note or "").strip()
    if len(normalized_note) > 255:
        raise click.ClickException("--note must be 255 characters or fewer.")

    normalized_product_bid = str(product_bid or "").strip()
    normalized_product_code = str(product_code or "").strip()
    if bool(normalized_product_bid) == bool(normalized_product_code):
        raise click.ClickException(
            "Pass exactly one of --product-bid or --product-code."
        )
    normalized_effective_to = str(effective_to or "").strip()

    try:
        aggregate = load_user_aggregate_by_identifier(normalized_identify)
        if aggregate is None:
            raise click.ClickException(
                f"No user found for identify: {normalized_identify}"
            )

        product = _load_active_plan_product(
            product_bid=normalized_product_bid,
            product_code=normalized_product_code,
        )
        if product is None:
            raise click.ClickException("Active billing plan not found.")

        creator_role_granted = False
        if not bool(getattr(aggregate, "is_creator", False)):
            mark_user_roles(aggregate.user_bid, is_creator=True)
            creator_role_granted = True
            aggregate = load_user_aggregate(aggregate.user_bid) or aggregate

        existing_subscription = load_primary_active_subscription(
            aggregate.user_bid,
            as_of=datetime.now(),
        )
        order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_START
        if existing_subscription is not None:
            if (
                str(existing_subscription.product_bid or "").strip()
                == product.product_bid
            ):
                db.session.commit()
                return {
                    "status": "noop_active",
                    "identify": normalized_identify,
                    "creator_bid": aggregate.user_bid,
                    "creator_role_granted": creator_role_granted,
                    "product_bid": product.product_bid,
                    "product_code": product.product_code,
                    "subscription_bid": existing_subscription.subscription_bid,
                    "bill_order_bid": None,
                    "billing_provider": existing_subscription.billing_provider,
                    "current_period_start_at": (
                        existing_subscription.current_period_start_at
                    ),
                    "current_period_end_at": existing_subscription.current_period_end_at,
                    "email": aggregate.email,
                    "mobile": aggregate.mobile,
                }
            current_product = _load_plan_product_by_bid(
                existing_subscription.product_bid
            )
            if (
                str(existing_subscription.billing_provider or "").strip().lower()
                != "manual"
            ):
                raise click.ClickException(
                    "User already has an active provider-managed subscription. "
                    "Use the normal checkout upgrade flow or wait for the current cycle to expire."
                )
            if current_product is None:
                raise click.ClickException(
                    "Active billing plan not found for the current subscription."
                )
            if int(product.sort_order or 0) <= int(current_product.sort_order or 0):
                raise click.ClickException(
                    "The current manual subscription is still active. "
                    "Manual grant only supports upgrades to a higher-tier plan."
                )
            order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE

        granted_at = datetime.now()
        cycle_end_at = (
            _parse_effective_to_option(normalized_effective_to)
            if normalized_effective_to
            else calculate_billing_cycle_end(product, cycle_start_at=granted_at)
        )
        if cycle_end_at is None:
            raise click.ClickException(
                "Target product does not support one-cycle manual activation."
            )
        if cycle_end_at <= granted_at:
            raise click.ClickException("--effective-to must be later than now.")

        subscription_metadata = {
            "manual_grant": True,
            "manual_grant_source": "cli",
        }
        if normalized_effective_to:
            subscription_metadata["manual_grant_effective_to"] = (
                cycle_end_at.isoformat()
            )
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

        if existing_subscription is None:
            subscription = BillingSubscription(
                subscription_bid=generate_id(current_app),
                creator_bid=aggregate.user_bid,
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

        order = BillingOrder(
            bill_order_bid=generate_id(current_app),
            creator_bid=aggregate.user_bid,
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

        granted = grant_paid_order_credits(current_app, order)
        if not granted:
            raise click.ClickException(
                "Manual plan grant did not create a new credit grant."
            )

        should_enqueue_subscription_purchase_sms = (
            stage_subscription_purchase_sms_for_paid_order(
                order,
                previous_status=None,
            )
        )
        _enforce_manual_subscription_expire_event(subscription)
        db.session.commit()

        payload = {
            "status": "granted",
            "identify": normalized_identify,
            "creator_bid": aggregate.user_bid,
            "creator_role_granted": creator_role_granted,
            "product_bid": product.product_bid,
            "product_code": product.product_code,
            "subscription_bid": subscription.subscription_bid,
            "bill_order_bid": order.bill_order_bid,
            "billing_provider": subscription.billing_provider,
            "current_period_start_at": subscription.current_period_start_at,
            "current_period_end_at": subscription.current_period_end_at,
            "email": aggregate.email,
            "mobile": aggregate.mobile,
        }
        if should_enqueue_subscription_purchase_sms:
            sms_payload = enqueue_subscription_purchase_sms(
                current_app,
                bill_order_bid=order.bill_order_bid,
            )
            payload["sms_enqueue_status"] = str(sms_payload.get("status") or "")
            payload["sms_enqueued"] = bool(sms_payload.get("enqueued"))
        return payload
    except Exception:
        db.session.rollback()
        raise


def _upsert_bootstrap_rows(
    *,
    model,
    key_field: str,
    rows: list[dict[str, Any]],
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
    model,
    key_field: str,
    payload: dict[str, Any],
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
) -> dict[str, Any] | None:
    normalized_value = str(raw_value or "").strip()
    if not normalized_value:
        return None

    try:
        parsed = json.loads(normalized_value)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"--{option_name} must be valid JSON.") from exc
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        raise click.ClickException(f"--{option_name} must decode to a JSON object.")
    return parsed


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
        raise click.ClickException(
            "--effective-to must be a valid ISO-8601 datetime or YYYY-MM-DD."
        )
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
    now = datetime.now()
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


def _serialize_cli_payload(payload: Any) -> Any:
    if hasattr(payload, "to_task_payload"):
        return payload.to_task_payload()
    if hasattr(payload, "to_payload"):
        return payload.to_payload()
    if hasattr(payload, "to_response_dict"):
        return payload.to_response_dict()
    if hasattr(payload, "__json__"):
        return payload.__json__()
    return payload


def _echo_payload(payload: Any) -> None:
    click.echo(
        json.dumps(
            _serialize_cli_payload(payload),
            sort_keys=True,
            ensure_ascii=False,
            default=_serialize_json_value,
        )
    )


def _serialize_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return str(value)

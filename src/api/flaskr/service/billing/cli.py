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
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_STATUS_INACTIVE,
    BILLING_PRODUCT_TYPE_CUSTOM,
    BILLING_PRODUCT_TYPE_GRANT,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILL_SYS_CONFIG_SEEDS,
    CREDIT_USAGE_RATE_SEEDS,
)
from .daily_aggregates import (
    detect_daily_aggregate_rebuild_range,
    rebuild_daily_aggregates,
)
from .models import BillingProduct, CreditUsageRate
from .notifications import requeue_subscription_purchase_sms
from .renewal import retry_billing_renewal_event, run_billing_renewal_event
from .settlement import backfill_bill_usage_settlement
from .subscriptions import (
    repair_subscription_cycle_mismatches,
    repair_topup_grant_expiries,
)
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

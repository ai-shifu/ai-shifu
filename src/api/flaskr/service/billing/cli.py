"""Flask CLI entrypoints for offline billing repair and replay work."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import click
from flask import current_app
from flask.cli import with_appcontext

from .checkout import reconcile_billing_provider_reference
from .daily_aggregates import (
    detect_daily_aggregate_rebuild_range,
    rebuild_daily_aggregates,
)
from .renewal import retry_billing_renewal_event, run_billing_renewal_event
from .settlement import backfill_bill_usage_settlement
from .wallets import rebuild_credit_wallet_snapshots


def register_billing_commands(console) -> None:
    """Register offline billing maintenance commands under ``flask console``."""

    @console.group(name="billing")
    def billing_group():
        """Billing maintenance commands for offline repair and replay."""

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
    @click.option("--billing-order-bid", default="", help="Billing order bid.")
    @click.option("--session-id", default="", help="Optional Stripe session id.")
    @with_appcontext
    def reconcile_order_command(
        creator_bid: str,
        payment_provider: str,
        provider_reference_id: str,
        billing_order_bid: str,
        session_id: str,
    ) -> None:
        """Manually replay provider sync for one billing order."""

        if (
            not str(billing_order_bid or "").strip()
            and not str(provider_reference_id or "").strip()
        ):
            raise click.ClickException(
                "Pass --billing-order-bid or --provider-reference-id for reconciliation."
            )

        payload = reconcile_billing_provider_reference(
            current_app,
            creator_bid=creator_bid,
            payment_provider=payment_provider,
            provider_reference_id=provider_reference_id,
            billing_order_bid=billing_order_bid,
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
    @click.option("--billing-order-bid", default="", help="Billing order bid.")
    @with_appcontext
    def retry_renewal_command(
        renewal_event_bid: str,
        subscription_bid: str,
        creator_bid: str,
        billing_order_bid: str,
    ) -> None:
        """Retry a failed renewal using the shared billing compensation path."""

        if not any(
            (
                str(renewal_event_bid or "").strip(),
                str(subscription_bid or "").strip(),
                str(creator_bid or "").strip(),
                str(billing_order_bid or "").strip(),
            )
        ):
            raise click.ClickException(
                "Pass a renewal event, subscription, creator, or billing order target."
            )

        payload = retry_billing_renewal_event(
            current_app,
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            billing_order_bid=billing_order_bid,
        )
        _echo_payload(payload)


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

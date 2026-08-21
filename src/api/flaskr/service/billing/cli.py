"""Flask CLI entrypoints for offline billing repair and replay work."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import click
from flask import current_app
from flask.cli import with_appcontext
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.config.models import Config
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.repository import (
    create_user_entity,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    mark_user_roles,
    update_user_entity_fields,
    upsert_credential,
)
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .checkout import reconcile_billing_provider_reference
from .consts import (
    ALLOCATION_INTERVAL_MANUAL,
    ALLOCATION_INTERVAL_ONE_TIME,
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILL_SYS_CONFIG_SEEDS,
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_NONE,
    BILLING_INTERVAL_YEAR,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_MODE_MANUAL,
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
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
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    CREDIT_USAGE_RATE_SEEDS,
)
from .credit_audit import audit_credit_state
from .daily_aggregates import (
    detect_daily_aggregate_rebuild_range,
    rebuild_daily_aggregates,
)
from .manual_credit_grants import (
    MANUAL_CREDIT_GRANT_SOURCES,
    MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
    MANUAL_CREDIT_VALIDITY_PRESETS,
    grant_manual_credits_to_user,
)
from .models import (
    BillingDailyUsageMetric,
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
from .queries import (
    calculate_self_managed_billing_cycle_end,
    load_primary_active_subscription,
)
from .renewal import retry_billing_renewal_event, run_billing_renewal_event
from .settlement import backfill_bill_usage_settlement
from .subscriptions import (
    grant_paid_order_credits,
    is_self_managed_billing_provider,
    repair_subscription_cycle_mismatches,
    repair_topup_grant_expiries,
)
from .trials import backfill_missing_creator_trial_credits
from .wallets import (
    rebuild_credit_wallet_snapshots,
    repair_credit_bucket_runtime_statuses,
    repair_expire_ledger_bucket_drift,
    repair_renewal_state_drift,
    restore_wrongly_expired_credit_pack_buckets,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

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

_DEFAULT_CLI_OPERATOR_USER_BID = "billing-cli"


def _normalize_cli_bid(value: object) -> str:
    return str(value or "").strip()


def _auth_type_values(raw_auth_type: object) -> set[str]:
    if raw_auth_type is None:
        return set()
    if isinstance(raw_auth_type, (list, tuple, set)):
        return {
            str(item).strip().lower() for item in raw_auth_type if str(item).strip()
        }

    text = str(raw_auth_type or "").strip()
    if not text or text in {"[]", "null"}:
        return set()
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {item.strip().lower() for item in text.split(",") if item.strip()}

    if isinstance(parsed, list):
        return {str(item).strip().lower() for item in parsed if str(item).strip()}
    if isinstance(parsed, str):
        return {parsed.strip().lower()} if parsed.strip() else set()
    return set()


def _has_authoring_permission(raw_auth_type: object) -> bool:
    return bool(_auth_type_values(raw_auth_type).intersection({"edit", "publish"}))


def backfill_authoring_permission_creators(
    app: object,
    *,
    course_bid: str = "",
    user_bid: str = "",
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backfill authoring permission creators."""
    normalized_course_bid = _normalize_cli_bid(course_bid)
    normalized_user_bid = _normalize_cli_bid(user_bid)
    normalized_limit = int(limit) if limit is not None and int(limit) > 0 else None

    with app.app_context():
        auth_query = AiCourseAuth.query.filter(AiCourseAuth.status == 1)
        if normalized_course_bid:
            auth_query = auth_query.filter(
                AiCourseAuth.course_id == normalized_course_bid
            )
        if normalized_user_bid:
            auth_query = auth_query.filter(AiCourseAuth.user_id == normalized_user_bid)
        auth_query = auth_query.order_by(AiCourseAuth.id.asc())
        if normalized_limit is not None:
            auth_query = auth_query.limit(normalized_limit)

        auth_rows = auth_query.all()
        candidates: dict[str, dict[str, Any]] = {}
        for auth in auth_rows:
            current_user_bid = _normalize_cli_bid(auth.user_id)
            if not current_user_bid:
                continue
            candidate = candidates.setdefault(
                current_user_bid,
                {
                    "course_bids": set(),
                    "has_authoring_permission": False,
                },
            )
            current_course_bid = _normalize_cli_bid(auth.course_id)
            if current_course_bid:
                candidate["course_bids"].add(current_course_bid)
            if _has_authoring_permission(auth.auth_type):
                candidate["has_authoring_permission"] = True

        records: list[dict[str, Any]] = []
        role_granted_count = 0
        role_would_grant_count = 0
        role_skipped_count = 0
        trial_granted_count = 0
        trial_skipped_count = 0

        for current_user_bid, candidate in sorted(candidates.items()):
            record: dict[str, Any] = {
                "creator_bid": current_user_bid,
                "course_bids": sorted(candidate["course_bids"]),
            }
            if not bool(candidate["has_authoring_permission"]):
                record.update(
                    {
                        "role_status": "skipped",
                        "role_reason": "non_authoring_permission",
                        "trial_status": "skipped",
                        "trial_reason": "non_authoring_permission",
                    }
                )
                role_skipped_count += 1
                trial_skipped_count += 1
                records.append(record)
                continue

            aggregate = load_user_aggregate(current_user_bid, with_credentials=False)
            if aggregate is None:
                record.update(
                    {
                        "role_status": "skipped",
                        "role_reason": "user_not_found",
                        "trial_status": "skipped",
                        "trial_reason": "user_not_found",
                    }
                )
                role_skipped_count += 1
                trial_skipped_count += 1
                records.append(record)
                continue

            if aggregate.is_creator:
                record.update(
                    {
                        "role_status": "skipped",
                        "role_reason": "already_creator",
                    }
                )
                role_skipped_count += 1
            elif dry_run:
                record.update(
                    {
                        "role_status": "would_grant",
                        "role_reason": None,
                    }
                )
                role_would_grant_count += 1
            else:
                mark_user_roles(current_user_bid, is_creator=True)
                db.session.commit()
                record.update(
                    {
                        "role_status": "granted",
                        "role_reason": None,
                    }
                )
                role_granted_count += 1

            if dry_run:
                record.update(
                    {
                        "trial_status": "dry_run",
                        "trial_reason": "dry_run",
                    }
                )
                records.append(record)
                continue

            trial_payload = backfill_missing_creator_trial_credits(
                app,
                creator_bid=current_user_bid,
            )
            trial_record = (trial_payload.get("records") or [{}])[0] or {}
            trial_status = trial_record.get("status") or trial_payload.get("status")
            trial_reason = trial_record.get("reason") or trial_payload.get("reason")
            record.update(
                {
                    "trial_status": trial_status,
                    "trial_reason": trial_reason,
                }
            )
            if int(trial_payload.get("granted_count") or 0) > 0:
                trial_granted_count += 1
            else:
                trial_skipped_count += 1
            records.append(record)

        return {
            "status": "completed",
            "dry_run": dry_run,
            "course_bid": normalized_course_bid or None,
            "user_bid": normalized_user_bid or None,
            "limit": normalized_limit,
            "auth_count": len(auth_rows),
            "creator_count": len(candidates),
            "role_granted_count": role_granted_count,
            "role_would_grant_count": role_would_grant_count,
            "role_skipped_count": role_skipped_count,
            "trial_granted_count": trial_granted_count,
            "trial_skipped_count": trial_skipped_count,
            "records": records,
        }


def register_billing_commands(console: object) -> None:
    """Register offline billing maintenance commands under ``flask console``."""

    @console.group(name="billing")
    def billing_group() -> None:
        """Billing maintenance commands for offline repair and replay."""

    @billing_group.command(name="seed-bootstrap-data")
    @with_appcontext
    def seed_bootstrap_data_command() -> None:
        """Upsert billing bootstrap rates and config rows."""
        _echo_payload(seed_billing_bootstrap_data())

    @billing_group.command(name="seed-sample-exception-orders")
    @with_appcontext
    def seed_sample_exception_orders_command() -> None:
        """Upsert sample abnormal orders for local admin billing debugging."""
        _echo_payload(seed_sample_exception_orders())

    @billing_group.command(name="seed-sample-focus-teachers")
    @with_appcontext
    def seed_sample_focus_teachers_command() -> None:
        """Upsert sample focus-teacher usage metrics for local admin billing."""
        _echo_payload(seed_sample_focus_teachers())

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

    @billing_group.command(name="grant-credits")
    @click.option(
        "--identify",
        default="",
        help="User identify value, usually phone or email.",
    )
    @click.option("--user-bid", default="", help="Target user business identifier.")
    @click.option("--amount", required=True, help="Granted credits amount.")
    @click.option(
        "--request-id",
        default="",
        help=(
            "Optional idempotency request id. When omitted, the CLI derives one "
            "from the grant inputs and the current date."
        ),
    )
    @click.option(
        "--grant-source",
        type=click.Choice(MANUAL_CREDIT_GRANT_SOURCES),
        default="compensation",
        show_default=True,
        help="Operator grant source.",
    )
    @click.option(
        "--validity-preset",
        type=click.Choice(MANUAL_CREDIT_VALIDITY_PRESETS),
        default=MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
        show_default=True,
        help="Grant validity preset. Defaults to the current subscription period.",
    )
    @click.option("--name", "display_name", default="", help="User-visible name.")
    @click.option("--note", default="", help="User-visible note.")
    @click.option(
        "--operator-user-bid",
        default="",
        help="Optional operator user bid for audit metadata.",
    )
    @with_appcontext
    def grant_credits_command(
        identify: str,
        user_bid: str,
        amount: str,
        request_id: str,
        grant_source: str,
        validity_preset: str,
        display_name: str,
        note: str,
        operator_user_bid: str,
    ) -> None:
        """Grant manual credits through the operator credit grant service."""
        payload = grant_operator_credits_by_cli(
            identify=identify,
            user_bid=user_bid,
            amount=amount,
            request_id=request_id,
            grant_source=grant_source,
            validity_preset=validity_preset,
            display_name=display_name,
            note=note,
            operator_user_bid=operator_user_bid,
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
            message = "Pass --creator-bid or --all for trial plan backfill."
            raise click.ClickException(message)

        payload = backfill_missing_creator_trial_credits(
            current_app,
            creator_bid=creator_bid,
            limit=limit if process_all else None,
        )
        _echo_payload(payload)

    @billing_group.command(name="backfill-authoring-permission-creators")
    @click.option("--course-bid", default="", help="Limit to one shared course.")
    @click.option("--user-bid", default="", help="Limit to one shared user.")
    @click.option(
        "--limit",
        type=click.IntRange(min=1),
        default=None,
        help="Maximum active permission rows to scan.",
    )
    @click.option(
        "--all",
        "process_all",
        is_flag=True,
        help=(
            "Scan active shared permissions and grant creator role for "
            "edit/publish users."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Report role/trial changes without writing creator roles or trial grants.",
    )
    @with_appcontext
    def backfill_authoring_permission_creators_command(
        course_bid: str,
        user_bid: str,
        limit: int | None,
        process_all: bool,
        dry_run: bool,
    ) -> None:
        """Grant creator role to users with edit/publish shared permissions."""
        has_course_scope = bool(str(course_bid or "").strip())
        has_user_scope = bool(str(user_bid or "").strip())
        if not has_course_scope and not has_user_scope and not process_all:
            message = (
                "Pass --user-bid, --course-bid, or --all for "
                "authoring-permission creator backfill."
            )
            raise click.ClickException(message)

        payload = backfill_authoring_permission_creators(
            current_app,
            course_bid=course_bid,
            user_bid=user_bid,
            limit=limit,
            dry_run=dry_run,
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
            message = (
                "Pass --usage-bid, a usage id range, or --all for settlement backfill."
            )
            raise click.ClickException(message)

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
    @click.option(
        "--apply",
        "apply_changes",
        is_flag=True,
        help="Persist rebuilt wallet snapshots. Defaults to dry-run.",
    )
    @with_appcontext
    def rebuild_wallets_command(
        creator_bid: str,
        wallet_bid: str,
        process_all: bool,
        apply_changes: bool,
    ) -> None:
        """Rebuild wallet snapshots from bucket balances."""
        if (
            not str(creator_bid or "").strip()
            and not str(wallet_bid or "").strip()
            and not process_all
        ):
            message = "Pass --creator-bid, --wallet-bid, or --all for wallet rebuild."
            raise click.ClickException(message)

        payload = rebuild_credit_wallet_snapshots(
            current_app,
            creator_bid=creator_bid,
            wallet_bid=wallet_bid,
            dry_run=not apply_changes,
        )
        _echo_payload(payload)

    @billing_group.command(name="audit-credit-state")
    @click.option("--creator-bid", default="", help="Audit one creator.")
    @click.option(
        "--limit",
        type=click.IntRange(min=1),
        default=None,
        help="Maximum creator candidates to scan when used with --all.",
    )
    @click.option(
        "--as-of",
        "as_of",
        default="",
        help="UTC timestamp used for time-sensitive diagnostics.",
    )
    @click.option(
        "--all",
        "process_all",
        is_flag=True,
        help="Scan all creator billing credit state.",
    )
    @with_appcontext
    def audit_credit_state_command(
        creator_bid: str,
        limit: int | None,
        as_of: str,
        process_all: bool,
    ) -> None:
        """Run read-only billing credit invariant diagnostics."""
        if not str(creator_bid or "").strip() and not process_all:
            message = "Pass --creator-bid or --all for credit state audit."
            raise click.ClickException(message)

        try:
            report = audit_credit_state(
                creator_bid=creator_bid,
                as_of=as_of or None,
                limit=limit if process_all else None,
            )
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        _echo_payload(report.to_payload())

    @billing_group.command(name="repair-expire-ledger-bucket-drift")
    @click.option("--creator-bid", default="", help="Repair one creator.")
    @click.option(
        "--wallet-bucket-bid",
        default="",
        help="Repair one wallet bucket directly.",
    )
    @click.option(
        "--limit",
        type=click.IntRange(min=1),
        default=None,
        help="Maximum bucket rows to scan when used with --all.",
    )
    @click.option(
        "--all",
        "process_all",
        is_flag=True,
        help="Scan every billing wallet bucket.",
    )
    @click.option(
        "--apply",
        "apply_changes",
        is_flag=True,
        help="Persist bucket and wallet snapshot repairs. Defaults to dry-run.",
    )
    @with_appcontext
    def repair_expire_ledger_bucket_drift_command(
        creator_bid: str,
        wallet_bucket_bid: str,
        limit: int | None,
        process_all: bool,
        apply_changes: bool,
    ) -> None:
        """Repair buckets skipped because an expire ledger already exists."""
        if (
            not str(creator_bid or "").strip()
            and not str(wallet_bucket_bid or "").strip()
            and not process_all
        ):
            message = (
                "Pass --creator-bid, --wallet-bucket-bid, or --all for "
                "expire-ledger bucket drift repair."
            )
            raise click.ClickException(message)

        payload = repair_expire_ledger_bucket_drift(
            current_app,
            creator_bid=creator_bid,
            wallet_bucket_bid=wallet_bucket_bid,
            limit=limit if process_all else None,
            dry_run=not apply_changes,
        )
        _echo_payload(payload)

    @billing_group.command(name="repair-renewal-state-drift")
    @click.option("--creator-bid", default="", help="Repair one creator.")
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
        help="Scan every creator billing state for past-end drift.",
    )
    @click.option(
        "--apply",
        "apply_changes",
        is_flag=True,
        help="Persist drift repairs. Defaults to dry-run.",
    )
    @with_appcontext
    def repair_renewal_state_drift_command(
        creator_bid: str,
        limit: int | None,
        process_all: bool,
        apply_changes: bool,
    ) -> None:
        """Repair lingering subscription or bucket state after cycle end."""
        if not str(creator_bid or "").strip() and not process_all:
            message = "Pass --creator-bid or --all for renewal state drift repair."
            raise click.ClickException(message)

        payload = repair_renewal_state_drift(
            current_app,
            creator_bid=creator_bid,
            limit=limit if process_all else None,
            dry_run=not apply_changes,
        )
        _echo_payload(payload)

    @billing_group.command(name="repair-topup-expiry")
    @click.option("--creator-bid", default="", help="Repair one creator.")
    @with_appcontext
    def repair_topup_expiry_command(creator_bid: str) -> None:
        """Repair one creator's topup grant expiry against the active paid plan."""
        if not str(creator_bid or "").strip():
            message = "Pass --creator-bid for topup expiry repair."
            raise click.ClickException(message)

        payload = repair_topup_grant_expiries(
            current_app,
            creator_bid=creator_bid,
        )
        _echo_payload(payload)

    @billing_group.command(name="restore-expired-topup-buckets")
    @click.option(
        "--bill-order-bid",
        "bill_order_bids",
        multiple=True,
        help="Paid topup order bid to restore. Repeat for multiple orders.",
    )
    @click.option(
        "--apply",
        "apply_changes",
        is_flag=True,
        help="Persist bucket and wallet repairs. Defaults to dry-run.",
    )
    @with_appcontext
    def restore_expired_topup_buckets_command(
        bill_order_bids: tuple[str, ...],
        apply_changes: bool,
    ) -> None:
        """Restore explicitly listed credit pack buckets expired by old logic."""
        if not any(str(bid or "").strip() for bid in bill_order_bids):
            message = (
                "Pass at least one --bill-order-bid for expired topup bucket restore."
            )
            raise click.ClickException(message)

        payload = restore_wrongly_expired_credit_pack_buckets(
            current_app,
            bill_order_bids=list(bill_order_bids),
            dry_run=not apply_changes,
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
            message = "Pass --creator-bid or --subscription-bid for subscription cycle repair."
            raise click.ClickException(message)

        payload = repair_subscription_cycle_mismatches(
            current_app,
            creator_bid=creator_bid,
            subscription_bid=subscription_bid,
        )
        _echo_payload(payload)

    @billing_group.command(name="repair-bucket-status")
    @click.option("--creator-bid", default="", help="Repair one creator.")
    @click.option(
        "--wallet-bucket-bid",
        default="",
        help="Repair one wallet bucket directly.",
    )
    @with_appcontext
    def repair_bucket_status_command(
        creator_bid: str,
        wallet_bucket_bid: str,
    ) -> None:
        """Repair expired bucket rows that still carry live credits."""
        if (
            not str(creator_bid or "").strip()
            and not str(wallet_bucket_bid or "").strip()
        ):
            message = (
                "Pass --creator-bid or --wallet-bucket-bid for bucket status repair."
            )
            raise click.ClickException(message)

        payload = repair_credit_bucket_runtime_statuses(
            current_app,
            creator_bid=creator_bid,
            wallet_bucket_bid=wallet_bucket_bid,
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
            message = "Pass --date-from/--date-to or --all for daily aggregate rebuild."
            raise click.ClickException(message)

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
            message = (
                "Pass --bill-order-bid or --provider-reference-id for reconciliation."
            )
            raise click.ClickException(message)

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
            message = "Pass a renewal event, subscription, or creator target."
            raise click.ClickException(message)

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
            message = (
                "Pass a renewal event, subscription, creator, or bill order target."
            )
            raise click.ClickException(message)

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
            message = "Pass --bill-order-bid for subscription purchase SMS requeue."
            raise click.ClickException(message)

        payload = requeue_subscription_purchase_sms(
            current_app,
            bill_order_bid=bill_order_bid,
        )
        _echo_payload(payload)


def seed_billing_bootstrap_data() -> dict[str, Any]:
    """Seed billing bootstrap data."""
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


def seed_sample_exception_orders() -> dict[str, Any]:
    """Seed sample exception orders."""
    current_time = now_utc().replace(microsecond=0)
    plan_product_bid = _load_first_active_product_bid(BILLING_PRODUCT_TYPE_PLAN)
    topup_product_bid = _load_first_active_product_bid(BILLING_PRODUCT_TYPE_TOPUP)

    if not plan_product_bid or not topup_product_bid:
        message = (
            "Active billing plan/topup products are required before seeding "
            "sample exception orders."
        )
        raise click.ClickException(message)

    creator_specs = [
        {
            "user_bid": "billing-debug-creator-failed",
            "identify": "13900001001",
            "mobile": "13900001001",
            "nickname": "Teacher Failed",
        },
        {
            "user_bid": "billing-debug-creator-pending",
            "identify": "13900001002",
            "mobile": "13900001002",
            "nickname": "Teacher Pending",
        },
        {
            "user_bid": "billing-debug-creator-timeout",
            "identify": "13900001003",
            "mobile": "13900001003",
            "nickname": "",
        },
    ]

    creator_inserted = 0
    creator_updated = 0
    for creator_spec in creator_specs:
        if _upsert_sample_exception_creator(
            user_bid=creator_spec["user_bid"],
            identify=creator_spec["identify"],
            mobile=creator_spec["mobile"],
            nickname=creator_spec["nickname"],
        ):
            creator_inserted += 1
        else:
            creator_updated += 1

    subscription_result = _upsert_bootstrap_rows(
        model=BillingSubscription,
        key_field="subscription_bid",
        rows=[
            {
                "subscription_bid": "billing-debug-subscription-failed",
                "creator_bid": "billing-debug-creator-failed",
                "product_bid": plan_product_bid,
                "status": BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
                "billing_provider": "stripe",
                "provider_subscription_id": "billing-debug-subscription-failed-ref",
                "provider_customer_id": "billing-debug-customer-failed",
                "billing_anchor_at": current_time,
                "current_period_start_at": current_time,
                "current_period_end_at": current_time,
                "grace_period_end_at": current_time,
                "cancel_at_period_end": 0,
                "next_product_bid": "",
                "last_renewed_at": current_time,
                "last_failed_at": current_time,
                "metadata_json": {"seed_source": "sample_exception_orders"},
                "deleted": 0,
                "created_at": current_time,
                "updated_at": current_time,
            },
            {
                "subscription_bid": "billing-debug-subscription-pending",
                "creator_bid": "billing-debug-creator-pending",
                "product_bid": plan_product_bid,
                "status": BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
                "billing_provider": "pingxx",
                "provider_subscription_id": "billing-debug-subscription-pending-ref",
                "provider_customer_id": "billing-debug-customer-pending",
                "billing_anchor_at": current_time,
                "current_period_start_at": current_time,
                "current_period_end_at": current_time,
                "grace_period_end_at": None,
                "cancel_at_period_end": 1,
                "next_product_bid": "",
                "last_renewed_at": current_time,
                "last_failed_at": None,
                "metadata_json": {"seed_source": "sample_exception_orders"},
                "deleted": 0,
                "created_at": current_time,
                "updated_at": current_time,
            },
            {
                "subscription_bid": "billing-debug-subscription-paused",
                "creator_bid": "billing-debug-creator-timeout",
                "product_bid": plan_product_bid,
                "status": BILLING_SUBSCRIPTION_STATUS_PAUSED,
                "billing_provider": "manual",
                "provider_subscription_id": "billing-debug-subscription-paused-ref",
                "provider_customer_id": "billing-debug-customer-timeout",
                "billing_anchor_at": current_time,
                "current_period_start_at": current_time,
                "current_period_end_at": current_time,
                "grace_period_end_at": None,
                "cancel_at_period_end": 0,
                "next_product_bid": "",
                "last_renewed_at": current_time,
                "last_failed_at": None,
                "metadata_json": {"seed_source": "sample_exception_orders"},
                "deleted": 0,
                "created_at": current_time,
                "updated_at": current_time,
            },
        ],
    )
    renewal_result = _upsert_bootstrap_rows(
        model=BillingRenewalEvent,
        key_field="renewal_event_bid",
        rows=[
            {
                "renewal_event_bid": "billing-debug-renewal-failed",
                "subscription_bid": "billing-debug-subscription-failed",
                "creator_bid": "billing-debug-creator-failed",
                "event_type": BILLING_RENEWAL_EVENT_TYPE_RETRY,
                "scheduled_at": current_time,
                "status": BILLING_RENEWAL_EVENT_STATUS_FAILED,
                "attempt_count": 2,
                "last_error": "card_declined",
                "payload_json": {"bill_order_bid": "billing-debug-order-failed"},
                "processed_at": current_time,
                "deleted": 0,
                "created_at": current_time,
                "updated_at": current_time,
            },
            {
                "renewal_event_bid": "billing-debug-renewal-pending",
                "subscription_bid": "billing-debug-subscription-pending",
                "creator_bid": "billing-debug-creator-pending",
                "event_type": BILLING_RENEWAL_EVENT_TYPE_RETRY,
                "scheduled_at": current_time,
                "status": BILLING_RENEWAL_EVENT_STATUS_PENDING,
                "attempt_count": 1,
                "last_error": "",
                "payload_json": {"bill_order_bid": "billing-debug-order-pending"},
                "processed_at": None,
                "deleted": 0,
                "created_at": current_time,
                "updated_at": current_time,
            },
        ],
    )

    order_result = _upsert_bootstrap_rows(
        model=BillingOrder,
        key_field="bill_order_bid",
        rows=[
            {
                "bill_order_bid": "billing-debug-order-failed",
                "creator_bid": "billing-debug-creator-failed",
                "order_type": BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                "product_bid": plan_product_bid,
                "subscription_bid": "billing-debug-subscription-failed",
                "currency": "CNY",
                "payable_amount": 29900,
                "paid_amount": 0,
                "payment_provider": "stripe",
                "channel": "checkout_session",
                "provider_reference_id": "billing-debug-order-failed-ref",
                "status": BILLING_ORDER_STATUS_FAILED,
                "paid_at": None,
                "failed_at": current_time,
                "refunded_at": None,
                "expires_at": None,
                "failure_code": "card_declined",
                "failure_message": "Card was declined",
                "metadata_json": {"seed_source": "sample_exception_orders"},
                "campaign_bid": "",
                "campaign_benefit_type": 0,
                "campaign_discount_amount": 0,
                "campaign_bonus_credit_amount": Decimal(0),
                "deleted": 0,
                "created_at": current_time,
                "updated_at": current_time,
            },
            {
                "bill_order_bid": "billing-debug-order-pending",
                "creator_bid": "billing-debug-creator-pending",
                "order_type": BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                "product_bid": plan_product_bid,
                "subscription_bid": "",
                "currency": "CNY",
                "payable_amount": 9900,
                "paid_amount": 0,
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
                "provider_reference_id": "billing-debug-order-pending-ref",
                "status": BILLING_ORDER_STATUS_PENDING,
                "paid_at": None,
                "failed_at": None,
                "refunded_at": None,
                "expires_at": current_time,
                "failure_code": "",
                "failure_message": "",
                "metadata_json": {"seed_source": "sample_exception_orders"},
                "campaign_bid": "",
                "campaign_benefit_type": 0,
                "campaign_discount_amount": 0,
                "campaign_bonus_credit_amount": Decimal(0),
                "deleted": 0,
                "created_at": current_time,
                "updated_at": current_time,
            },
            {
                "bill_order_bid": "billing-debug-order-timeout",
                "creator_bid": "billing-debug-creator-timeout",
                "order_type": BILLING_ORDER_TYPE_TOPUP,
                "product_bid": topup_product_bid,
                "subscription_bid": "",
                "currency": "CNY",
                "payable_amount": 19900,
                "paid_amount": 0,
                "payment_provider": "pingxx",
                "channel": "wx_pub",
                "provider_reference_id": "billing-debug-order-timeout-ref",
                "status": BILLING_ORDER_STATUS_TIMEOUT,
                "paid_at": None,
                "failed_at": None,
                "refunded_at": None,
                "expires_at": current_time,
                "failure_code": "checkout_timeout",
                "failure_message": "Checkout expired",
                "metadata_json": {"seed_source": "sample_exception_orders"},
                "campaign_bid": "",
                "campaign_benefit_type": 0,
                "campaign_discount_amount": 0,
                "campaign_bonus_credit_amount": Decimal(0),
                "deleted": 0,
                "created_at": current_time,
                "updated_at": current_time,
            },
        ],
    )
    with unit_of_work():
        pass
    return {
        "status": "seeded",
        "creators": {
            "count": len(creator_specs),
            "inserted": creator_inserted,
            "updated": creator_updated,
        },
        "subscriptions": subscription_result,
        "renewal_events": renewal_result,
        "orders": order_result,
        "order_bids": [
            "billing-debug-order-failed",
            "billing-debug-order-pending",
            "billing-debug-order-timeout",
        ],
    }


def seed_sample_focus_teachers() -> dict[str, Any]:
    """Seed sample focus teachers."""
    current_time = now_utc().replace(microsecond=0)
    today = current_time.date()

    creator_specs = [
        {
            "user_bid": "billing-focus-creator-growth",
            "identify": "13900002001",
            "mobile": "13900002001",
            "nickname": "增长很快老师",
        },
        {
            "user_bid": "billing-focus-creator-debug",
            "identify": "13900002002",
            "mobile": "13900002002",
            "nickname": "调试偏高老师",
        },
        {
            "user_bid": "billing-focus-creator-steady",
            "identify": "13900002003",
            "mobile": "13900002003",
            "nickname": "稳定使用老师",
        },
        {
            "user_bid": "billing-focus-creator-recent",
            "identify": "13900002004",
            "mobile": "13900002004",
            "nickname": "近期活跃老师",
        },
    ]

    creator_inserted = 0
    creator_updated = 0
    for creator_spec in creator_specs:
        if _upsert_debug_creator(
            user_bid=creator_spec["user_bid"],
            identify=creator_spec["identify"],
            mobile=creator_spec["mobile"],
            nickname=creator_spec["nickname"],
            seed_source="sample_focus_teachers",
        ):
            creator_inserted += 1
        else:
            creator_updated += 1

    rows: list[dict[str, Any]] = []

    def add_metric(
        *,
        bid: str,
        stat_days_ago: int,
        creator_bid: str,
        shifu_bid: str,
        usage_scene: int,
        metric: int,
        credit_amount: str,
        record_count: int,
        raw_amount: int,
    ) -> None:
        stat_day = today - timedelta(days=stat_days_ago)
        window_started_at = current_time.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) - timedelta(days=stat_days_ago)
        window_ended_at = window_started_at + timedelta(days=1)
        rows.append(
            {
                "daily_usage_metric_bid": bid,
                "stat_date": stat_day.isoformat(),
                "creator_bid": creator_bid,
                "shifu_bid": shifu_bid,
                "usage_scene": usage_scene,
                "usage_type": BILL_USAGE_TYPE_LLM,
                "provider": "openai",
                "model": "gpt-4o-mini",
                "billing_metric": metric,
                "raw_amount": raw_amount,
                "record_count": record_count,
                "consumed_credits": Decimal(credit_amount),
                "window_started_at": window_started_at,
                "window_ended_at": window_ended_at,
                "created_at": current_time,
                "updated_at": current_time,
                "deleted": 0,
            }
        )

    add_metric(
        bid="billing-focus-growth-current-1",
        stat_days_ago=1,
        creator_bid="billing-focus-creator-growth",
        shifu_bid="billing-focus-shifu-growth",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="4.2",
        record_count=3,
        raw_amount=3200,
    )
    add_metric(
        bid="billing-focus-growth-current-2",
        stat_days_ago=3,
        creator_bid="billing-focus-creator-growth",
        shifu_bid="billing-focus-shifu-growth",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_INPUT_TOKENS,
        credit_amount="5.4",
        record_count=2,
        raw_amount=4100,
    )
    add_metric(
        bid="billing-focus-growth-current-3",
        stat_days_ago=5,
        creator_bid="billing-focus-creator-growth",
        shifu_bid="billing-focus-shifu-growth",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="3.8",
        record_count=2,
        raw_amount=2800,
    )
    add_metric(
        bid="billing-focus-growth-prev-1",
        stat_days_ago=10,
        creator_bid="billing-focus-creator-growth",
        shifu_bid="billing-focus-shifu-growth",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="1.4",
        record_count=1,
        raw_amount=1000,
    )

    add_metric(
        bid="billing-focus-debug-current-1",
        stat_days_ago=0,
        creator_bid="billing-focus-creator-debug",
        shifu_bid="billing-focus-shifu-debug",
        usage_scene=BILL_USAGE_SCENE_DEBUG,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="3.6",
        record_count=2,
        raw_amount=2600,
    )
    add_metric(
        bid="billing-focus-debug-current-2",
        stat_days_ago=2,
        creator_bid="billing-focus-creator-debug",
        shifu_bid="billing-focus-shifu-debug",
        usage_scene=BILL_USAGE_SCENE_PREVIEW,
        metric=BILLING_METRIC_LLM_INPUT_TOKENS,
        credit_amount="3.1",
        record_count=2,
        raw_amount=2200,
    )
    add_metric(
        bid="billing-focus-debug-current-3",
        stat_days_ago=6,
        creator_bid="billing-focus-creator-debug",
        shifu_bid="billing-focus-shifu-debug",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="1.6",
        record_count=2,
        raw_amount=1400,
    )
    add_metric(
        bid="billing-focus-debug-30d-1",
        stat_days_ago=12,
        creator_bid="billing-focus-creator-debug",
        shifu_bid="billing-focus-shifu-debug",
        usage_scene=BILL_USAGE_SCENE_DEBUG,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="2.4",
        record_count=1,
        raw_amount=1800,
    )

    add_metric(
        bid="billing-focus-steady-current-1",
        stat_days_ago=1,
        creator_bid="billing-focus-creator-steady",
        shifu_bid="billing-focus-shifu-steady",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="2.8",
        record_count=1,
        raw_amount=1900,
    )
    add_metric(
        bid="billing-focus-steady-current-2",
        stat_days_ago=3,
        creator_bid="billing-focus-creator-steady",
        shifu_bid="billing-focus-shifu-steady",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_INPUT_TOKENS,
        credit_amount="2.7",
        record_count=2,
        raw_amount=2000,
    )
    add_metric(
        bid="billing-focus-steady-current-3",
        stat_days_ago=6,
        creator_bid="billing-focus-creator-steady",
        shifu_bid="billing-focus-shifu-steady",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="3.4",
        record_count=2,
        raw_amount=2500,
    )

    add_metric(
        bid="billing-focus-recent-current-1",
        stat_days_ago=0,
        creator_bid="billing-focus-creator-recent",
        shifu_bid="billing-focus-shifu-recent",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="4.6",
        record_count=2,
        raw_amount=3300,
    )
    add_metric(
        bid="billing-focus-recent-current-2",
        stat_days_ago=4,
        creator_bid="billing-focus-creator-recent",
        shifu_bid="billing-focus-shifu-recent",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_INPUT_TOKENS,
        credit_amount="3.7",
        record_count=2,
        raw_amount=2600,
    )
    add_metric(
        bid="billing-focus-recent-prev-1",
        stat_days_ago=9,
        creator_bid="billing-focus-creator-recent",
        shifu_bid="billing-focus-shifu-recent",
        usage_scene=BILL_USAGE_SCENE_PROD,
        metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        credit_amount="0.8",
        record_count=1,
        raw_amount=700,
    )

    usage_metric_result = _upsert_bootstrap_rows(
        model=BillingDailyUsageMetric, key_field="daily_usage_metric_bid", rows=rows
    )

    with unit_of_work():
        pass
    return {
        "status": "seeded",
        "creators": {
            "count": len(creator_specs),
            "inserted": creator_inserted,
            "updated": creator_updated,
        },
        "usage_metrics": usage_metric_result,
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
    """Create or update billing product."""
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
        message = "--product-bid is required."
        raise click.ClickException(message)
    if not payload["product_code"]:
        message = "--product-code is required."
        raise click.ClickException(message)
    if not payload["display_name_i18n_key"]:
        message = "--display-name-i18n-key is required."
        raise click.ClickException(message)
    if not payload["description_i18n_key"]:
        message = "--description-i18n-key is required."
        raise click.ClickException(message)

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


@contextmanager
def _rollback_on_error() -> Iterator[None]:
    """Roll back the CLI transaction when the wrapped block raises."""
    try:
        yield
    except Exception:
        db.session.rollback()
        raise


def grant_billing_plan_by_identify(
    *,
    identify: str,
    product_bid: str = "",
    product_code: str = "",
    effective_to: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Grant billing plan by identify."""
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

    with _rollback_on_error():
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
            as_of=now_utc(),
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
            if not is_self_managed_billing_provider(
                existing_subscription.billing_provider
            ):
                error_message = (
                    "User already has an active provider-managed subscription. "
                    "Use the normal checkout upgrade flow or wait for the current cycle to expire."
                )
                raise click.ClickException(error_message)
            if current_product is None:
                error_message = (
                    "Active billing plan not found for the current subscription."
                )
                raise click.ClickException(error_message)
            if int(product.sort_order or 0) <= int(current_product.sort_order or 0):
                error_message = (
                    "The current subscription is still active. "
                    "Operator grant only supports upgrades to a higher-tier plan."
                )
                raise click.ClickException(error_message)
            order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE

        granted_at = now_utc()
        cycle_end_at = (
            _parse_effective_to_option(normalized_effective_to)
            if normalized_effective_to
            else calculate_self_managed_billing_cycle_end(
                product,
                cycle_start_at=granted_at,
            )
        )
        if cycle_end_at is None:
            error_message = (
                "Target product does not support one-cycle manual activation."
            )
            raise click.ClickException(error_message)
        if cycle_end_at <= granted_at:
            error_message = "--effective-to must be later than now."
            raise click.ClickException(error_message)

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
            error_message = "Manual plan grant did not create a new credit grant."
            raise click.ClickException(error_message)

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


def grant_operator_credits_by_cli(
    *,
    identify: str = "",
    user_bid: str = "",
    amount: str,
    request_id: str,
    grant_source: str = "compensation",
    validity_preset: str,
    display_name: str = "",
    note: str = "",
    operator_user_bid: str = "",
) -> dict[str, Any]:
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

    with _rollback_on_error():
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
                validity_preset=validity_preset,
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
            validity_preset=str(validity_preset or "").strip(),
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
    validity_preset: str,
    display_name: str,
    note: str,
) -> str:
    fingerprint_payload = "|".join(
        [
            str(user_bid or "").strip(),
            str(amount or "").strip(),
            str(grant_source or "").strip().lower(),
            str(validity_preset or "").strip().lower(),
            str(display_name or "").strip(),
            str(note or "").strip(),
        ]
    )
    fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()[:16]
    return f"cli:{now_utc():%Y%m%d}:{fingerprint}"


def _upsert_bootstrap_rows(
    *,
    model: object,
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
    model: object,
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
        message = f"--{option_name} must be valid JSON."
        raise click.ClickException(message) from exc
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        message = f"--{option_name} must decode to a JSON object."
        raise click.ClickException(message)
    return parsed


def _load_first_active_product_bid(product_type: int) -> str:
    row = (
        BillingProduct.query.filter(
            BillingProduct.product_type == product_type,
            BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
            BillingProduct.deleted == 0,
        )
        .order_by(BillingProduct.sort_order.asc(), BillingProduct.id.asc())
        .first()
    )
    return str(row.product_bid or "").strip() if row is not None else ""


def _upsert_debug_creator(
    *,
    user_bid: str,
    identify: str,
    mobile: str,
    nickname: str,
    seed_source: str,
) -> bool:
    entity = get_user_entity_by_bid(user_bid, include_deleted=True)
    created = entity is None

    if entity is None:
        create_user_entity(
            user_bid=user_bid,
            identify=identify,
            nickname=nickname,
            language="zh-CN",
            state=USER_STATE_REGISTERED,
        )
    else:
        update_user_entity_fields(
            entity,
            identify=identify,
            nickname=nickname,
            language="zh-CN",
            state=USER_STATE_REGISTERED,
            deleted=False,
        )

    mark_user_roles(user_bid, is_creator=True)
    upsert_credential(
        current_app,
        user_bid=user_bid,
        provider_name="phone",
        subject_id=mobile,
        subject_format="phone",
        identifier=mobile,
        metadata={"seed_source": seed_source},
        verified=True,
    )
    return created


def _upsert_sample_exception_creator(
    *,
    user_bid: str,
    identify: str,
    mobile: str,
    nickname: str,
) -> bool:
    return _upsert_debug_creator(
        user_bid=user_bid,
        identify=identify,
        mobile=mobile,
        nickname=nickname,
        seed_source="sample_exception_orders",
    )


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
    now = now_utc()
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


def _serialize_cli_payload(payload: object) -> object:
    if hasattr(payload, "to_task_payload"):
        return payload.to_task_payload()
    if hasattr(payload, "to_payload"):
        return payload.to_payload()
    if hasattr(payload, "to_response_dict"):
        return payload.to_response_dict()
    if hasattr(payload, "__json__"):
        return payload.__json__()
    return payload


def _echo_payload(payload: object) -> None:
    click.echo(
        json.dumps(
            _serialize_cli_payload(payload),
            sort_keys=True,
            ensure_ascii=False,
            default=_serialize_json_value,
        )
    )


def _serialize_json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return str(value)

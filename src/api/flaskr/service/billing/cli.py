"""Flask CLI entrypoints for offline billing repair and replay work."""

from __future__ import annotations

from dataclasses import asdict

import click
from flask import current_app
from flask.cli import with_appcontext
from flaskr.dao import db  # noqa: F401 - re-exported for import compatibility
from flaskr.dao.uow import unit_of_work
from flaskr.service.config.models import Config
from flaskr.service.shifu.models import (
    AiCourseAuth,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.service.user.consts import (
    USER_STATE_REGISTERED,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.service.user.repository import (  # noqa: F401 - re-exported for import compatibility
    create_user_entity,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    mark_user_roles,
    update_user_entity_fields,
    upsert_credential,
)
from flaskr.util.datetime import (
    now_utc,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.util.uuid import (
    generate_id,  # noqa: F401 - re-exported for import compatibility
)

from .checkout import reconcile_billing_provider_reference
from .cli_backfills import backfill_authoring_permission_creators
from .cli_catalog import (
    activate_cli_provider_price_mapping,
    bind_provider_price_mapping,
    inspect_cli_provider_price_mapping,
    list_cli_provider_price_mappings,
    retire_cli_provider_price_mapping,
    upsert_billing_product,
    validate_cli_provider_price_mapping,
)
from .cli_grants import (
    _enforce_manual_subscription_expire_event,  # noqa: F401 - patch point used by cli_grants
    grant_billing_plan_by_identify,
    grant_operator_credits_by_cli,
)
from .cli_sample_data import (
    seed_sample_exception_orders,
    seed_sample_focus_teachers,
)
from .cli_support import (
    _ALLOCATION_INTERVAL_LABELS,
    _BILLING_INTERVAL_LABELS,
    _BILLING_MODE_LABELS,
    _PRODUCT_STATUS_LABELS,
    _PRODUCT_TYPE_LABELS,
    _PROVIDER_PRICE_STATUS_LABELS,
    _echo_payload,
    _upsert_bootstrap_rows,
)
from .consts import (  # noqa: F401 - re-exported for import compatibility
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
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_DRAFT,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
    BILLING_PROVIDER_PRICE_STATUS_RETIRED,
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
    grant_manual_credits_to_user,  # noqa: F401 - re-exported for import compatibility
)
from .models import (  # noqa: F401 - re-exported for import compatibility
    BillingDailyUsageMetric,
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditUsageRate,
)
from .notifications import (  # noqa: F401 - re-exported for import compatibility
    enqueue_subscription_purchase_sms,
    requeue_subscription_purchase_sms,
    stage_subscription_purchase_sms_for_paid_order,
)
from .primitives import (
    coerce_datetime,  # noqa: F401 - re-exported for import compatibility
)
from .provider_price_mappings import (  # noqa: F401 - re-exported for import compatibility
    ProviderPriceMappingError,
    activate_provider_price_mapping,
    get_active_provider_price_mapping,
    get_provider_price_mapping,
    list_provider_price_mappings,
    retire_provider_price_mapping,
    serialize_provider_price_mapping,
    upsert_provider_price_mapping,
    validate_provider_price_mapping_by_bid,
)
from .queries import (  # noqa: F401 - re-exported for import compatibility
    calculate_self_managed_billing_cycle_end,
    load_primary_active_subscription,
)
from .renewal import retry_billing_renewal_event, run_billing_renewal_event
from .settlement import backfill_bill_usage_settlement
from .subscriptions import (  # noqa: F401 - re-exported for import compatibility
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


def register_billing_commands(console: object) -> None:
    """Register offline billing maintenance commands under ``flask console``."""

    @console.group(name="billing")
    def billing_group() -> None:
        """Billing maintenance commands for offline repair and replay."""

    _register_seed_commands(billing_group)
    _register_product_commands(billing_group)
    _register_provider_price_commands(billing_group)
    _register_grant_commands(billing_group)
    _register_backfill_commands(billing_group)
    _register_wallet_commands(billing_group)
    _register_drift_repair_commands(billing_group)
    _register_bucket_repair_commands(billing_group)
    _register_aggregate_and_order_commands(billing_group)
    _register_renewal_commands(billing_group)


def _register_seed_commands(billing_group: click.Group) -> None:
    """Register sample and bootstrap seeding commands."""

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


def _register_product_commands(billing_group: click.Group) -> None:
    """Register the billing product catalog upsert command."""

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


def _register_provider_price_commands(billing_group: click.Group) -> None:
    """Register the ``provider-price`` mapping subgroup."""

    @billing_group.group(name="provider-price")
    def provider_price_group() -> None:
        """Manage billing product provider price mappings."""

    _register_provider_price_write_commands(provider_price_group)
    _register_provider_price_read_commands(provider_price_group)


def _register_provider_price_write_commands(provider_price_group: click.Group) -> None:
    """Register provider price bind, activate and retire commands."""

    @provider_price_group.command(name="bind")
    @click.option("--product-bid", required=True, help="Bill product bid.")
    @click.option(
        "--provider-account-id",
        required=True,
        help="Stripe account identifier.",
    )
    @click.option(
        "--provider-product-id",
        required=True,
        help="Stripe product identifier.",
    )
    @click.option(
        "--provider-price-id",
        required=True,
        help="Stripe price identifier.",
    )
    @click.option(
        "--livemode/--testmode",
        default=False,
        show_default=True,
        help="Whether the Stripe objects are live-mode objects.",
    )
    @click.option(
        "--metadata-json",
        default="",
        help="Optional provider mapping metadata JSON object.",
    )
    @with_appcontext
    def provider_price_bind_command(
        product_bid: str,
        provider_account_id: str,
        provider_product_id: str,
        provider_price_id: str,
        livemode: bool,
        metadata_json: str,
    ) -> None:
        """Create or update a draft Stripe price mapping."""
        payload = bind_provider_price_mapping(
            product_bid=product_bid,
            provider_account_id=provider_account_id,
            provider_product_id=provider_product_id,
            provider_price_id=provider_price_id,
            livemode=livemode,
            metadata_json=metadata_json,
        )
        _echo_payload(payload)

    @provider_price_group.command(name="activate")
    @click.option(
        "--provider-price-bid",
        required=True,
        help="Provider price mapping bid.",
    )
    @with_appcontext
    def provider_price_activate_command(provider_price_bid: str) -> None:
        """Validate and activate a Stripe price mapping."""
        payload = activate_cli_provider_price_mapping(provider_price_bid)
        _echo_payload(payload)
        if payload["status"] == "invalid":
            raise click.exceptions.Exit(1)

    @provider_price_group.command(name="retire")
    @click.option(
        "--provider-price-bid",
        required=True,
        help="Provider price mapping bid.",
    )
    @with_appcontext
    def provider_price_retire_command(provider_price_bid: str) -> None:
        """Retire a Stripe price mapping."""
        _echo_payload(retire_cli_provider_price_mapping(provider_price_bid))


def _register_provider_price_read_commands(provider_price_group: click.Group) -> None:
    """Register provider price validate, list and inspect commands."""

    @provider_price_group.command(name="validate")
    @click.option(
        "--provider-price-bid",
        required=True,
        help="Provider price mapping bid.",
    )
    @with_appcontext
    def provider_price_validate_command(provider_price_bid: str) -> None:
        """Validate a Stripe price mapping without activating it."""
        payload = validate_cli_provider_price_mapping(provider_price_bid)
        _echo_payload(payload)
        if payload["status"] == "invalid":
            raise click.exceptions.Exit(1)

    @provider_price_group.command(name="list")
    @click.option("--product-bid", default="", help="Optional bill product bid.")
    @click.option(
        "--provider-account-id",
        default="",
        help="Optional Stripe account identifier.",
    )
    @click.option(
        "--status",
        "status_label",
        default="",
        type=click.Choice(
            ["", *sorted(_PROVIDER_PRICE_STATUS_LABELS.keys())],
            case_sensitive=False,
        ),
        help="Optional provider price mapping status label.",
    )
    @click.option(
        "--mode",
        default="all",
        show_default=True,
        type=click.Choice(["all", "test", "live"], case_sensitive=False),
        help="Filter by Stripe mode.",
    )
    @with_appcontext
    def provider_price_list_command(
        product_bid: str,
        provider_account_id: str,
        status_label: str,
        mode: str,
    ) -> None:
        """List Stripe price mappings."""
        normalized_mode = str(mode or "all").strip().lower()
        _echo_payload(
            list_cli_provider_price_mappings(
                product_bid=product_bid,
                provider_account_id=provider_account_id,
                status_label=status_label,
                livemode=(
                    True
                    if normalized_mode == "live"
                    else False
                    if normalized_mode == "test"
                    else None
                ),
            )
        )

    @provider_price_group.command(name="inspect")
    @click.option(
        "--provider-price-bid",
        required=True,
        help="Provider price mapping bid.",
    )
    @with_appcontext
    def provider_price_inspect_command(provider_price_bid: str) -> None:
        """Inspect one Stripe price mapping."""
        _echo_payload(inspect_cli_provider_price_mapping(provider_price_bid))


def _register_grant_commands(billing_group: click.Group) -> None:
    """Register operator plan and credit grant commands."""

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
        "--validity-value",
        type=click.IntRange(min=1),
        required=True,
        help="Positive whole-number duration, effective immediately.",
    )
    @click.option(
        "--validity-unit",
        type=click.Choice(("day", "month", "year")),
        required=True,
        help="Days are 24 hours; months and years use UTC calendar arithmetic.",
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
        validity_value: int,
        validity_unit: str,
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
            validity_value=validity_value,
            validity_unit=validity_unit,
            display_name=display_name,
            note=note,
            operator_user_bid=operator_user_bid,
        )
        _echo_payload(payload)


def _register_backfill_commands(billing_group: click.Group) -> None:
    """Register trial, creator-role and settlement backfills."""

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


def _register_wallet_commands(billing_group: click.Group) -> None:
    """Register wallet snapshot rebuild and credit-state audit commands."""

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


def _register_drift_repair_commands(billing_group: click.Group) -> None:
    """Register expire-ledger and renewal-state drift repair commands."""

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


def _register_bucket_repair_commands(billing_group: click.Group) -> None:
    """Register topup, subscription-cycle and bucket repairs."""

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


def _register_aggregate_and_order_commands(billing_group: click.Group) -> None:
    """Register daily aggregate rebuild and order reconcile."""

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


def _register_renewal_commands(billing_group: click.Group) -> None:
    """Register renewal replay and purchase SMS requeue commands."""

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


def seed_billing_bootstrap_data() -> dict[str, object]:
    """Seed billing bootstrap data."""
    with unit_of_work():
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
    return {
        "status": "seeded",
        "products": {"count": 0, "inserted": 0, "updated": 0},
        "rates": rate_result,
        "configs": config_result,
    }

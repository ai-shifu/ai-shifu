"""Capability registry for creator billing surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from .dtos import (
    BillingCapabilityDTO,
    BillingCapabilityEntryPointDTO,
    BillingRouteBootstrapDTO,
    BillingRouteItemDTO,
)


@dataclass(frozen=True, slots=True)
class BillingCapabilityDefinition:
    key: str
    status: str
    audience: str
    user_visible: bool
    default_enabled: bool
    route_entries: tuple[tuple[str, str], ...] = ()
    task_entries: tuple[str, ...] = ()
    cli_entries: tuple[str, ...] = ()
    config_entries: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


_CAPABILITIES: tuple[BillingCapabilityDefinition, ...] = (
    BillingCapabilityDefinition(
        key="creator_catalog",
        status="active",
        audience="creator",
        user_visible=True,
        default_enabled=True,
        route_entries=(("GET", "/catalog"),),
        notes=("Creator can inspect active billing plans and topups.",),
    ),
    BillingCapabilityDefinition(
        key="creator_subscription_checkout",
        status="active",
        audience="creator",
        user_visible=True,
        default_enabled=True,
        route_entries=(
            ("GET", "/overview"),
            ("POST", "/subscriptions/checkout"),
            ("POST", "/subscriptions/cancel"),
            ("POST", "/subscriptions/resume"),
        ),
        notes=("Creator subscription lifecycle and overview stay enabled.",),
    ),
    BillingCapabilityDefinition(
        key="creator_wallet_ledger",
        status="active",
        audience="creator",
        user_visible=True,
        default_enabled=True,
        route_entries=(
            ("GET", "/wallet-buckets"),
            ("GET", "/ledger"),
        ),
        notes=("Wallet buckets and ledger read models are live in the billing UI.",),
    ),
    BillingCapabilityDefinition(
        key="creator_orders",
        status="active",
        audience="creator",
        user_visible=True,
        default_enabled=True,
        route_entries=(
            ("POST", "/orders/{bill_order_bid}/sync"),
            ("POST", "/orders/{bill_order_bid}/checkout"),
            ("POST", "/orders/{bill_order_bid}/refund"),
            ("POST", "/topups/checkout"),
        ),
        notes=("Creator sync, refund, and topup flows stay enabled.",),
    ),
    BillingCapabilityDefinition(
        key="admin_subscriptions",
        status="active",
        audience="admin",
        user_visible=True,
        default_enabled=True,
        route_entries=(("GET", "/api/admin/billing/subscriptions"),),
        notes=("Admin subscription review remains enabled.",),
    ),
    BillingCapabilityDefinition(
        key="admin_orders",
        status="active",
        audience="admin",
        user_visible=True,
        default_enabled=True,
        route_entries=(("GET", "/api/admin/billing/orders"),),
        notes=("Admin billing order review remains enabled.",),
    ),
    BillingCapabilityDefinition(
        key="admin_ledger_adjust",
        status="active",
        audience="admin",
        user_visible=True,
        default_enabled=True,
        route_entries=(("POST", "/api/admin/billing/ledger/adjust"),),
        notes=("Admin ledger adjustment remains enabled.",),
    ),
    BillingCapabilityDefinition(
        key="admin_entitlements",
        status="active",
        audience="admin",
        user_visible=True,
        default_enabled=True,
        route_entries=(("GET", "/api/admin/billing/entitlements"),),
        notes=("Admin entitlement review remains enabled.",),
    ),
    BillingCapabilityDefinition(
        key="admin_domains",
        status="active",
        audience="admin",
        user_visible=True,
        default_enabled=True,
        route_entries=(("GET", "/api/admin/billing/domain-audits"),),
        notes=("Admin domain audit screens remain enabled.",),
    ),
    BillingCapabilityDefinition(
        key="admin_reports",
        status="active",
        audience="admin",
        user_visible=True,
        default_enabled=True,
        route_entries=(
            ("GET", "/api/admin/billing/reports/usage-daily"),
            ("GET", "/api/admin/billing/reports/ledger-daily"),
        ),
        notes=("Admin reports remain available from the billing console.",),
    ),
    BillingCapabilityDefinition(
        key="runtime_billing_extensions",
        status="active",
        audience="runtime",
        user_visible=False,
        default_enabled=True,
        route_entries=(("GET", "/api/runtime-config"),),
        notes=(
            "Runtime config currently includes billing entitlement and domain fields.",
        ),
    ),
    BillingCapabilityDefinition(
        key="billing_feature_flag",
        status="default_disabled",
        audience="ops",
        user_visible=False,
        default_enabled=False,
        config_entries=("BILL_ENABLED",),
        notes=("The billing feature flag seed defaults to disabled.",),
    ),
    BillingCapabilityDefinition(
        key="renewal_task_queue",
        status="default_disabled",
        audience="ops",
        user_visible=False,
        default_enabled=False,
        config_entries=("BILL_RENEWAL_TASK_CONFIG.enabled",),
        notes=("Renewal background execution seed defaults to disabled.",),
    ),
    BillingCapabilityDefinition(
        key="usage_settlement",
        status="internal_only",
        audience="worker",
        user_visible=False,
        default_enabled=True,
        task_entries=("billing.settle_usage", "billing.replay_usage_settlement"),
        cli_entries=("flask console billing backfill-settlement",),
        notes=("Usage settlement is an internal task and CLI repair surface.",),
    ),
    BillingCapabilityDefinition(
        key="renewal_compensation",
        status="internal_only",
        audience="worker",
        user_visible=False,
        default_enabled=True,
        task_entries=("billing.run_renewal_event", "billing.retry_failed_renewal"),
        cli_entries=(
            "flask console billing run-renewal-event",
            "flask console billing retry-renewal",
        ),
        notes=("Renewal and retry compensation stay internal-only.",),
    ),
    BillingCapabilityDefinition(
        key="provider_reconcile",
        status="internal_only",
        audience="worker",
        user_visible=False,
        default_enabled=True,
        task_entries=("billing.reconcile_provider_reference",),
        cli_entries=("flask console billing reconcile-order",),
        notes=("Provider reconcile is an internal recovery surface.",),
    ),
    BillingCapabilityDefinition(
        key="wallet_bucket_expiration",
        status="internal_only",
        audience="worker",
        user_visible=False,
        default_enabled=True,
        task_entries=("billing.expire_wallet_buckets",),
        notes=("Wallet bucket expiration remains internal-only.",),
    ),
    BillingCapabilityDefinition(
        key="low_balance_alerts",
        status="internal_only",
        audience="worker",
        user_visible=False,
        default_enabled=True,
        task_entries=("billing.send_low_balance_alert",),
        notes=("Low-balance alert generation remains internal-only.",),
    ),
    BillingCapabilityDefinition(
        key="daily_aggregate_rebuild",
        status="internal_only",
        audience="worker",
        user_visible=False,
        default_enabled=True,
        task_entries=(
            "billing.aggregate_daily_usage_metrics",
            "billing.aggregate_daily_ledger_summary",
            "billing.rebuild_daily_aggregates",
        ),
        cli_entries=("flask console billing rebuild-daily-aggregates",),
        notes=("Daily aggregate rebuild and finalize flows remain internal-only.",),
    ),
    BillingCapabilityDefinition(
        key="domain_verify_refresh",
        status="internal_only",
        audience="worker",
        user_visible=False,
        default_enabled=True,
        task_entries=("billing.verify_domain_binding",),
        notes=("Domain verification refresh stays internal-only.",),
    ),
)


def get_billing_capability_definitions() -> tuple[BillingCapabilityDefinition, ...]:
    return _CAPABILITIES


def iter_billing_capabilities() -> list[BillingCapabilityDTO]:
    payload: list[BillingCapabilityDTO] = []
    for capability in _CAPABILITIES:
        entry_points = [
            BillingCapabilityEntryPointDTO(kind="route", method=method, path=path)
            for method, path in capability.route_entries
        ]
        entry_points.extend(
            BillingCapabilityEntryPointDTO(kind="task", name=name)
            for name in capability.task_entries
        )
        entry_points.extend(
            BillingCapabilityEntryPointDTO(kind="cli", name=name)
            for name in capability.cli_entries
        )
        entry_points.extend(
            BillingCapabilityEntryPointDTO(kind="config", name=name)
            for name in capability.config_entries
        )
        payload.append(
            BillingCapabilityDTO(
                key=capability.key,
                status=capability.status,
                audience=capability.audience,
                user_visible=capability.user_visible,
                default_enabled=capability.default_enabled,
                entry_points=entry_points,
                notes=list(capability.notes),
            )
        )
    return payload


def build_billing_route_bootstrap(path_prefix: str) -> BillingRouteBootstrapDTO:
    """Return the billing route manifest and capability registry."""

    creator_routes: list[BillingRouteItemDTO] = []
    admin_routes: list[BillingRouteItemDTO] = []
    for capability in _CAPABILITIES:
        for method, raw_path in capability.route_entries:
            route = BillingRouteItemDTO(
                method=method,
                path=(
                    f"{path_prefix}{raw_path}"
                    if raw_path.startswith("/") and not raw_path.startswith("/api/")
                    else raw_path
                ),
            )
            if capability.audience == "creator":
                creator_routes.append(route)
            elif capability.audience == "admin":
                admin_routes.append(route)

    return BillingRouteBootstrapDTO(
        service="billing",
        status="bootstrap",
        path_prefix=path_prefix,
        creator_routes=creator_routes,
        admin_routes=admin_routes,
        capabilities=iter_billing_capabilities(),
        notes=[
            "Registered via plugin route loading from flaskr/service.",
            "Keeps creator billing separate from legacy /order tables and routes.",
            "Capability status is the source of truth for active, default-disabled, and internal-only billing surfaces.",
        ],
    )

"""Creator billing routes."""

from __future__ import annotations

from flask import Flask, request

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.billing.capabilities import build_billing_route_bootstrap
from flaskr.service.billing.checkout import (
    create_billing_order_checkout,
    create_billing_subscription_checkout,
    create_billing_topup_checkout,
    refund_billing_order,
    sync_billing_order,
)
from flaskr.service.billing.read_models import (
    adjust_admin_billing_ledger,
    build_admin_bill_daily_ledger_summary_page,
    build_admin_bill_daily_usage_metrics_page,
    build_admin_billing_domain_audits_page,
    build_admin_bill_entitlements_page,
    build_admin_bill_orders_page,
    build_admin_bill_subscriptions_page,
    build_billing_catalog,
    build_billing_ledger_page,
    build_billing_overview,
    build_billing_wallet_buckets,
)
from flaskr.service.billing.subscriptions import (
    cancel_billing_subscription,
    resume_billing_subscription,
)
from flaskr.service.billing.trials import acknowledge_trial_welcome_dialog
from flaskr.service.common.models import raise_error, raise_param_error
from .primitives import is_billing_enabled


def _require_creator() -> None:
    if not getattr(request.user, "is_creator", False):
        raise_error("server.shifu.noPermission")


def _require_billing_enabled(app: Flask) -> None:
    if is_billing_enabled():
        return
    app.logger.info("billing disabled for route %s", request.path)
    raise_error("server.billing.disabled")


def _require_billing_access(app: Flask) -> None:
    _require_billing_enabled(app)
    _require_creator()


def _get_creator_bid() -> str:
    return str(getattr(request.user, "user_id", "") or "").strip()


def _get_timezone_name() -> str | None:
    timezone_name = (request.args.get("timezone", "") or "").strip()
    if timezone_name and len(timezone_name) > 100:
        raise_param_error("timezone")
    return timezone_name or None


def _get_page_args() -> tuple[str, str]:
    return (
        request.args.get("page_index", "1"),
        request.args.get("page_size", "20"),
    )


def _get_optional_query_arg(name: str, *, max_length: int = 100) -> str:
    value = (request.args.get(name, "") or "").strip()
    if len(value) > max_length:
        raise_param_error(name)
    return value


@inject
def register_billing_routes(app: Flask, path_prefix: str = "/api/billing") -> None:
    """Register creator billing routes."""

    app.logger.info("register billing routes %s", path_prefix)
    admin_path_prefix = "/api/admin/billing"

    @app.route(path_prefix, methods=["GET"])
    def billing_bootstrap_api():
        _require_billing_access(app)
        return make_common_response(build_billing_route_bootstrap(path_prefix))

    @app.route(path_prefix + "/catalog", methods=["GET"])
    def billing_catalog_api():
        _require_billing_access(app)
        return make_common_response(build_billing_catalog(app))

    @app.route(path_prefix + "/overview", methods=["GET"])
    def billing_overview_api():
        _require_billing_access(app)
        return make_common_response(
            build_billing_overview(
                app,
                _get_creator_bid(),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/trial-offer/welcome/ack", methods=["POST"])
    def billing_trial_offer_welcome_ack_api():
        _require_billing_access(app)
        return make_common_response(
            acknowledge_trial_welcome_dialog(
                app,
                _get_creator_bid(),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/wallet-buckets", methods=["GET"])
    def billing_wallet_buckets_api():
        _require_billing_access(app)
        return make_common_response(
            build_billing_wallet_buckets(
                app,
                _get_creator_bid(),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/ledger", methods=["GET"])
    def billing_ledger_api():
        _require_billing_access(app)
        page_index, page_size = _get_page_args()
        return make_common_response(
            build_billing_ledger_page(
                app,
                _get_creator_bid(),
                page_index=page_index,
                page_size=page_size,
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/orders/<bill_order_bid>/sync", methods=["POST"])
    def billing_order_sync_api(bill_order_bid: str):
        _require_billing_access(app)
        return make_common_response(
            sync_billing_order(
                app,
                _get_creator_bid(),
                bill_order_bid,
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/orders/<bill_order_bid>/checkout", methods=["POST"])
    def billing_order_checkout_api(bill_order_bid: str):
        _require_billing_access(app)
        return make_common_response(
            create_billing_order_checkout(
                app,
                _get_creator_bid(),
                bill_order_bid,
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/orders/<bill_order_bid>/refund", methods=["POST"])
    def billing_order_refund_api(bill_order_bid: str):
        _require_billing_access(app)
        return make_common_response(
            refund_billing_order(
                app,
                _get_creator_bid(),
                bill_order_bid,
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/subscriptions/checkout", methods=["POST"])
    def billing_subscription_checkout_api():
        _require_billing_access(app)
        return make_common_response(
            create_billing_subscription_checkout(
                app,
                _get_creator_bid(),
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/subscriptions/cancel", methods=["POST"])
    def billing_subscription_cancel_api():
        _require_billing_access(app)
        return make_common_response(
            cancel_billing_subscription(
                app,
                _get_creator_bid(),
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/subscriptions/resume", methods=["POST"])
    def billing_subscription_resume_api():
        _require_billing_access(app)
        return make_common_response(
            resume_billing_subscription(
                app,
                _get_creator_bid(),
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/topups/checkout", methods=["POST"])
    def billing_topup_checkout_api():
        _require_billing_access(app)
        return make_common_response(
            create_billing_topup_checkout(
                app,
                _get_creator_bid(),
                request.get_json(silent=True) or {},
            )
        )

    @app.route(admin_path_prefix + "/subscriptions", methods=["GET"])
    def admin_bill_subscriptions_api():
        _require_billing_access(app)
        page_index, page_size = _get_page_args()
        return make_common_response(
            build_admin_bill_subscriptions_page(
                app,
                page_index=page_index,
                page_size=page_size,
                creator_bid=_get_optional_query_arg("creator_bid"),
                status=_get_optional_query_arg("status"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(admin_path_prefix + "/domain-audits", methods=["GET"])
    def admin_billing_domain_audits_api():
        _require_billing_access(app)
        page_index, page_size = _get_page_args()
        return make_common_response(
            build_admin_billing_domain_audits_page(
                app,
                page_index=page_index,
                page_size=page_size,
                creator_bid=_get_optional_query_arg("creator_bid"),
                status=_get_optional_query_arg("status"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(admin_path_prefix + "/entitlements", methods=["GET"])
    def admin_bill_entitlements_api():
        _require_billing_access(app)
        page_index, page_size = _get_page_args()
        return make_common_response(
            build_admin_bill_entitlements_page(
                app,
                page_index=page_index,
                page_size=page_size,
                creator_bid=_get_optional_query_arg("creator_bid"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(admin_path_prefix + "/orders", methods=["GET"])
    def admin_bill_orders_api():
        _require_billing_access(app)
        page_index, page_size = _get_page_args()
        return make_common_response(
            build_admin_bill_orders_page(
                app,
                page_index=page_index,
                page_size=page_size,
                creator_bid=_get_optional_query_arg("creator_bid"),
                status=_get_optional_query_arg("status"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(admin_path_prefix + "/reports/usage-daily", methods=["GET"])
    def admin_billing_daily_usage_reports_api():
        _require_billing_access(app)
        page_index, page_size = _get_page_args()
        return make_common_response(
            build_admin_bill_daily_usage_metrics_page(
                app,
                page_index=page_index,
                page_size=page_size,
                creator_bid=_get_optional_query_arg("creator_bid"),
                stat_date_from=_get_optional_query_arg("date_from"),
                stat_date_to=_get_optional_query_arg("date_to"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(admin_path_prefix + "/reports/ledger-daily", methods=["GET"])
    def admin_billing_daily_ledger_reports_api():
        _require_billing_access(app)
        page_index, page_size = _get_page_args()
        return make_common_response(
            build_admin_bill_daily_ledger_summary_page(
                app,
                page_index=page_index,
                page_size=page_size,
                creator_bid=_get_optional_query_arg("creator_bid"),
                stat_date_from=_get_optional_query_arg("date_from"),
                stat_date_to=_get_optional_query_arg("date_to"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(admin_path_prefix + "/ledger/adjust", methods=["POST"])
    def admin_billing_ledger_adjust_api():
        _require_billing_access(app)
        return make_common_response(
            adjust_admin_billing_ledger(
                app,
                operator_user_bid=_get_creator_bid(),
                payload=request.get_json(silent=True) or {},
            )
        )

    return None

"""Creator billing routes."""

from __future__ import annotations

import json

from flask import Flask, request

from flaskr.framework.plugin.inject import inject
from flaskr.service.billing.funcs import (
    cancel_billing_subscription,
    build_billing_catalog,
    build_billing_ledger_page,
    build_billing_order_detail,
    build_billing_orders_page,
    build_billing_overview,
    build_billing_route_bootstrap,
    build_billing_wallet_buckets,
    create_billing_subscription_checkout,
    create_billing_topup_checkout,
    resume_billing_subscription,
    sync_billing_order,
)
from flaskr.service.common.models import raise_error, raise_param_error


def _make_common_response(data):
    return json.dumps(
        {"code": 0, "message": "success", "data": data or {}},
        ensure_ascii=False,
    )


def _require_creator() -> None:
    if not getattr(request.user, "is_creator", False):
        raise_error("server.shifu.noPermission")


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


@inject
def register_billing_routes(app: Flask, path_prefix: str = "/api/billing") -> None:
    """Register creator billing routes."""

    app.logger.info("register billing routes %s", path_prefix)

    @app.route(path_prefix, methods=["GET"])
    def billing_bootstrap_api():
        _require_creator()
        return _make_common_response(build_billing_route_bootstrap(path_prefix))

    @app.route(path_prefix + "/catalog", methods=["GET"])
    def billing_catalog_api():
        _require_creator()
        return _make_common_response(build_billing_catalog(app))

    @app.route(path_prefix + "/overview", methods=["GET"])
    def billing_overview_api():
        _require_creator()
        return _make_common_response(
            build_billing_overview(
                app,
                _get_creator_bid(),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/wallet-buckets", methods=["GET"])
    def billing_wallet_buckets_api():
        _require_creator()
        return _make_common_response(
            build_billing_wallet_buckets(
                app,
                _get_creator_bid(),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/ledger", methods=["GET"])
    def billing_ledger_api():
        _require_creator()
        page_index, page_size = _get_page_args()
        return _make_common_response(
            build_billing_ledger_page(
                app,
                _get_creator_bid(),
                page_index=page_index,
                page_size=page_size,
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/orders", methods=["GET"])
    def billing_orders_api():
        _require_creator()
        page_index, page_size = _get_page_args()
        return _make_common_response(
            build_billing_orders_page(
                app,
                _get_creator_bid(),
                page_index=page_index,
                page_size=page_size,
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/orders/<billing_order_bid>", methods=["GET"])
    def billing_order_detail_api(billing_order_bid: str):
        _require_creator()
        return _make_common_response(
            build_billing_order_detail(
                app,
                _get_creator_bid(),
                billing_order_bid,
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/orders/<billing_order_bid>/sync", methods=["POST"])
    def billing_order_sync_api(billing_order_bid: str):
        _require_creator()
        return _make_common_response(
            sync_billing_order(
                app,
                _get_creator_bid(),
                billing_order_bid,
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/subscriptions/checkout", methods=["POST"])
    def billing_subscription_checkout_api():
        _require_creator()
        return _make_common_response(
            create_billing_subscription_checkout(
                app,
                _get_creator_bid(),
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/subscriptions/cancel", methods=["POST"])
    def billing_subscription_cancel_api():
        _require_creator()
        return _make_common_response(
            cancel_billing_subscription(
                app,
                _get_creator_bid(),
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/subscriptions/resume", methods=["POST"])
    def billing_subscription_resume_api():
        _require_creator()
        return _make_common_response(
            resume_billing_subscription(
                app,
                _get_creator_bid(),
                request.get_json(silent=True) or {},
            )
        )

    @app.route(path_prefix + "/topups/checkout", methods=["POST"])
    def billing_topup_checkout_api():
        _require_creator()
        return _make_common_response(
            create_billing_topup_checkout(
                app,
                _get_creator_bid(),
                request.get_json(silent=True) or {},
            )
        )

    return None

"""Register operator promotion coupon and campaign routes.

Service calls resolve through the route module so its patch targets stay effective.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.service.shifu.admin_operations.route_helpers import (
    PROMOTION_CAMPAIGN_STATUS_VALUES,
    PROMOTION_COUPON_STATUS_VALUES,
    PROMOTION_COUPON_USAGE_STATUS_VALUES,
    _normalize_query_text,
    _parse_choice_query_param,
    _parse_datetime_filter,
    _parse_positive_query_int,
    _require_operator,
    _validate_datetime_range,
)

if TYPE_CHECKING:
    from flask import Flask


def register_admin_operations_promotion_coupon_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register promotion coupon list, create, and update routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/promotions/coupons", methods=["GET"])
    def admin_operations_promotion_coupons() -> str:
        """Operator coupon batch list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )

        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
            "name": _normalize_query_text(request.args.get("name")),
            "course_query": _normalize_query_text(request.args.get("course_query")),
            "shifu_bid": _normalize_query_text(request.args.get("shifu_bid")),
            "course_name": _normalize_query_text(request.args.get("course_name")),
            "usage_type": _normalize_query_text(request.args.get("usage_type")),
            "ops_state": _normalize_query_text(request.args.get("ops_state")),
            "discount_type": _normalize_query_text(request.args.get("discount_type")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=PROMOTION_COUPON_STATUS_VALUES,
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            ops_route.list_operator_promotion_coupons(
                app, page_index, page_size, filters
            )
        )

    @app.route(path_prefix + "/admin/operations/promotions/coupons", methods=["POST"])
    def admin_create_operations_promotion_coupon() -> str:
        """Create operator coupon batch."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        return make_common_response(
            ops_route.create_operator_promotion_coupon(
                app, request.user.user_id, payload
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>",
        methods=["POST"],
    )
    def admin_update_operations_promotion_coupon(coupon_bid: str) -> str:
        """Update operator coupon batch."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        return make_common_response(
            ops_route.update_operator_promotion_coupon(
                app, request.user.user_id, coupon_bid, payload
            )
        )


def register_admin_operations_promotion_coupon_detail_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register promotion coupon detail, status, usage, and code routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>",
        methods=["GET"],
    )
    def admin_operations_promotion_coupon_detail(coupon_bid: str) -> str:
        """Get operator coupon batch detail."""
        _require_operator()
        return make_common_response(
            ops_route.get_operator_promotion_coupon_detail(app, coupon_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>/status",
        methods=["POST"],
    )
    def admin_operations_promotion_coupon_status(coupon_bid: str) -> str:
        """Update operator coupon batch status."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        enabled = payload.get("enabled")
        return make_common_response(
            ops_route.update_operator_promotion_coupon_status(
                app,
                request.user.user_id,
                coupon_bid,
                enabled,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>/usages",
        methods=["GET"],
    )
    def admin_operations_promotion_coupon_usages(coupon_bid: str) -> str:
        """Get operator coupon usage list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=PROMOTION_COUPON_USAGE_STATUS_VALUES,
            ),
        }
        return make_common_response(
            ops_route.list_operator_promotion_coupon_usages(
                app, coupon_bid, page_index, page_size, filters
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/coupons/<coupon_bid>/codes",
        methods=["GET"],
    )
    def admin_operations_promotion_coupon_codes(coupon_bid: str) -> str:
        """Get operator coupon code pool list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
        }
        return make_common_response(
            ops_route.list_operator_promotion_coupon_codes(
                app, coupon_bid, page_index, page_size, filters
            )
        )


def register_admin_operations_promotion_campaign_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register promotion campaign routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/promotions/campaigns", methods=["GET"])
    def admin_operations_promotion_campaigns() -> str:
        """Operator campaign list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )

        filters = {
            "keyword": _normalize_query_text(request.args.get("keyword")),
            "course_query": _normalize_query_text(request.args.get("course_query")),
            "shifu_bid": _normalize_query_text(request.args.get("shifu_bid")),
            "course_name": _normalize_query_text(request.args.get("course_name")),
            "apply_type": _normalize_query_text(request.args.get("apply_type")),
            "channel": _normalize_query_text(request.args.get("channel")),
            "discount_type": _normalize_query_text(request.args.get("discount_type")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=PROMOTION_CAMPAIGN_STATUS_VALUES,
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            ops_route.list_operator_promotion_campaigns(
                app, page_index, page_size, filters
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns",
        methods=["POST"],
    )
    def admin_create_operations_promotion_campaign() -> str:
        """Create operator campaign."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        return make_common_response(
            ops_route.create_operator_promotion_campaign(
                app, request.user.user_id, payload
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns/<promo_bid>",
        methods=["GET"],
    )
    def admin_operations_promotion_campaign_detail(promo_bid: str) -> str:
        """Get operator campaign detail."""
        _require_operator()
        return make_common_response(
            ops_route.get_operator_promotion_campaign_detail(app, promo_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns/<promo_bid>",
        methods=["POST"],
    )
    def admin_update_operations_promotion_campaign(promo_bid: str) -> str:
        """Update operator campaign."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        return make_common_response(
            ops_route.update_operator_promotion_campaign(
                app, request.user.user_id, promo_bid, payload
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns/<promo_bid>/status",
        methods=["POST"],
    )
    def admin_operations_promotion_campaign_status(promo_bid: str) -> str:
        """Update operator campaign status."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        enabled = payload.get("enabled")
        return make_common_response(
            ops_route.update_operator_promotion_campaign_status(
                app,
                request.user.user_id,
                promo_bid,
                enabled,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/campaigns/<promo_bid>/redemptions",
        methods=["GET"],
    )
    def admin_operations_promotion_campaign_redemptions(promo_bid: str) -> str:
        """Get operator campaign redemption list."""
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
        }
        return make_common_response(
            ops_route.list_operator_promotion_campaign_redemptions(
                app,
                promo_bid,
                page_index,
                page_size,
                filters,
            )
        )

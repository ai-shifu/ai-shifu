"""Register operator order routes.

Service calls resolve through the route module so its patch targets stay effective.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.admin_operations.courses_shared import (
    OPERATOR_ORDER_LIST_MAX_PAGE_SIZE,
)
from flaskr.service.shifu.admin_operations.route_helpers import (
    _normalize_query_text,
    _parse_boolean_query_param,
    _parse_datetime_filter,
    _parse_digit_query_param,
    _parse_positive_query_int,
    _require_operator,
    _validate_datetime_range,
)

if TYPE_CHECKING:
    from flask import Flask


def register_admin_operations_order_list_routes(app: Flask, path_prefix: str) -> None:
    """Register operator order list and overview routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/orders", methods=["GET"])
    def admin_operations_orders() -> str:
        """Operator global order list.

        ---
        tags:
            - Order
        parameters:
            - name: page_index
              type: integer
              required: true
            - name: page_size
              type: integer
              required: true
            - name: user_keyword
              type: string
              required: false
              description: Exact match on user bid, phone, or email
            - name: order_bid
              type: string
              required: false
            - name: course_query
              type: string
              required: false
              description: Matches exact course ID or fuzzy course name
            - name: shifu_bid
              type: string
              required: false
              description: Deprecated exact course ID filter
            - name: course_name
              type: string
              required: false
              description: Deprecated fuzzy course name filter
            - name: status
              type: string
              required: false
            - name: order_source
              type: string
              required: false
              description: user_purchase, coupon_redeem, import_activation, or open_api
            - name: payment_channel
              type: string
              required: false
            - name: start_time
              type: string
              required: false
              description: Order created start date (YYYY-MM-DD)
            - name: end_time
              type: string
              required: false
              description: Order created end date (YYYY-MM-DD)
        responses:
            200:
                description: List global operator-visible orders
        """
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
        page_size = min(page_size, OPERATOR_ORDER_LIST_MAX_PAGE_SIZE)

        filters = {
            "user_keyword": _normalize_query_text(request.args.get("user_keyword")),
            "order_bid": _normalize_query_text(request.args.get("order_bid")),
            "course_query": _normalize_query_text(request.args.get("course_query")),
            "shifu_bid": _normalize_query_text(request.args.get("shifu_bid")),
            "course_name": _normalize_query_text(request.args.get("course_name")),
            "status": _parse_digit_query_param(
                request.args.get("status"),
                field_name="status",
            ),
            "order_source": _normalize_query_text(request.args.get("order_source")),
            "payment_channel": _normalize_query_text(
                request.args.get("payment_channel")
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
            ops_route.list_operator_orders(app, page_index, page_size, filters)
        )

    @app.route(path_prefix + "/admin/operations/orders/overview", methods=["GET"])
    def admin_operations_order_overview() -> str:
        """Operator learning order overview.

        ---
        tags:
            - Order
        responses:
            200:
                description: Operator-visible learning order overview metrics
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/OrderAdminOverviewDTO"
        """
        _require_operator()
        return make_common_response(ops_route.get_operator_order_overview(app))


def register_admin_operations_order_detail_routes(app: Flask, path_prefix: str) -> None:
    """Register the operator order detail route."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/orders/<order_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_order_detail(order_bid: str) -> str:
        """Get operator order detail.

        ---
        tags:
            - Order
        parameters:
            - name: order_bid
              in: path
              type: string
              required: true
              description: Order business identifier
        responses:
            200:
                description: Operator order detail
        """
        _require_operator()
        if not str(order_bid or "").strip():
            raise_param_error("order_bid")
        return make_common_response(ops_route.get_operator_order_detail(app, order_bid))


def register_admin_operations_credit_order_routes(app: Flask, path_prefix: str) -> None:
    """Register operator credit order list and overview routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/orders/credits", methods=["GET"])
    def admin_operations_credit_orders() -> str:
        """Operator global credit order list.

        ---
        tags:
            - Order
        parameters:
            - name: page_index
              type: integer
              required: false
              description: Page index, defaults to 1 when omitted
            - name: page_size
              type: integer
              required: false
              description: Page size, defaults to 20 when omitted and is capped by OPERATOR_ORDER_LIST_MAX_PAGE_SIZE
            - name: creator_keyword
              type: string
              required: false
            - name: product_keyword
              type: string
              required: false
            - name: bill_order_bid
              type: string
              required: false
            - name: credit_order_kind
              type: string
              required: false
              description: plan or topup
            - name: status
              type: string
              required: false
            - name: payment_provider
              type: string
              required: false
            - name: has_available_credits
              type: boolean
              required: false
              description: Only include orders whose granted credits still have remaining balance
            - name: start_time
              type: string
              required: false
            - name: end_time
              type: string
              required: false
        responses:
            200:
                description: List global operator-visible credit orders
        """
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
        page_size = min(page_size, OPERATOR_ORDER_LIST_MAX_PAGE_SIZE)
        start_time = _parse_datetime_filter(
            request.args.get("start_time", ""),
            field_name="start_time",
            is_end=False,
        )
        end_time = _parse_datetime_filter(
            request.args.get("end_time", ""),
            field_name="end_time",
            is_end=True,
        )
        _validate_datetime_range(start_time, end_time, field_name="start_time")
        return make_common_response(
            ops_route.build_operator_credit_orders_page(
                app,
                page_index=page_index,
                page_size=page_size,
                creator_keyword=_normalize_query_text(
                    request.args.get("creator_keyword")
                ),
                product_keyword=_normalize_query_text(
                    request.args.get("product_keyword")
                ),
                bill_order_bid=_normalize_query_text(
                    request.args.get("bill_order_bid")
                ),
                credit_order_kind=_normalize_query_text(
                    request.args.get("credit_order_kind")
                ),
                status=_normalize_query_text(request.args.get("status")),
                has_available_credits=_parse_boolean_query_param(
                    request.args.get("has_available_credits"),
                    field_name="has_available_credits",
                ),
                payment_provider=_normalize_query_text(
                    request.args.get("payment_provider")
                ),
                start_time=start_time,
                end_time=end_time,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/orders/credits/overview",
        methods=["GET"],
    )
    def admin_operations_credit_order_overview() -> str:
        """Operator credit order overview.

        ---
        tags:
            - Order
        responses:
            200:
                description: Operator-visible credit order overview metrics
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/OperatorCreditOrderOverviewDTO"
        """
        _require_operator()
        return make_common_response(
            ops_route.build_operator_credit_orders_overview(app)
        )


def register_admin_operations_credit_order_detail_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register the operator credit order detail route."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/orders/credits/<bill_order_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_credit_order_detail(bill_order_bid: str) -> str:
        """Get operator credit order detail.

        ---
        tags:
            - Order
        parameters:
            - name: bill_order_bid
              in: path
              type: string
              required: true
              description: Billing order business identifier
        responses:
            200:
                description: Operator credit order detail
        """
        _require_operator()
        if not str(bill_order_bid or "").strip():
            raise_param_error("bill_order_bid")
        return make_common_response(
            ops_route.get_operator_credit_order_detail(
                app,
                bill_order_bid=bill_order_bid,
            )
        )

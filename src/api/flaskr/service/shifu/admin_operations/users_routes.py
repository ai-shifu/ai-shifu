"""Register operator user-administration routes.

Service calls resolve through the route module so its patch targets stay effective.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response, sensitive_body
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.admin_dtos import (
    AdminOperationUserContactChangeRequestDTO,
    AdminOperationUserCreditDeductionRequestDTO,
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationUserPackageGrantRequestDTO,
)
from flaskr.service.shifu.admin_operations.route_helpers import (
    OPERATOR_USER_ROLE_VALUES,
    OPERATOR_USER_STATUS_VALUES,
    _normalize_contact_type,
    _normalize_contacts,
    _normalize_query_text,
    _parse_choice_query_param,
    _parse_datetime_filter,
    _parse_positive_query_int,
    _require_operator,
    _validate_contacts,
    _validate_datetime_range,
)
from pydantic import ValidationError

if TYPE_CHECKING:
    from flask import Flask


def register_admin_operations_user_list_routes(app: Flask, path_prefix: str) -> None:
    """Register operator user list and overview routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/users", methods=["GET"])
    def admin_operations_users() -> str:
        """Operator user list.

        ---
        tags:
            - User
        parameters:
            - name: page_index
              type: integer
              required: true
            - name: page_size
              type: integer
              required: true
            - name: user_bid
              type: string
              required: false
            - name: user_query
              type: string
              required: false
              description: Matches user phone, email, identify, user_bid, or nickname
            - name: identifier
              type: string
              required: false
              description: Deprecated user phone, email, identify, or user_bid keyword
            - name: mobile
              type: string
              required: false
              description: Deprecated alias for identifier
            - name: nickname
              type: string
              required: false
            - name: user_status
              type: string
              required: false
              description: unregistered, registered, or paid
            - name: user_role
              type: string
              required: false
              description: regular, creator, learner, or operator
            - name: quick_filter
              type: string
              required: false
              description: creator, learner, registered, paid, created_last_30d, registered_last_30d, learning_active_30d, paid_last_30d, guest
            - name: start_time
              type: string
              required: false
              description: User created start date (YYYY-MM-DD)
            - name: end_time
              type: string
              required: false
              description: User created end date (YYYY-MM-DD)
        responses:
            200:
                description: List active users for operators
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationUserListDTO"
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

        filters = {
            "user_bid": _normalize_query_text(request.args.get("user_bid")),
            "user_query": _normalize_query_text(request.args.get("user_query")),
            "identifier": _normalize_query_text(request.args.get("identifier")),
            "mobile": _normalize_query_text(request.args.get("mobile")),
            "nickname": _normalize_query_text(request.args.get("nickname")),
            "user_status": _parse_choice_query_param(
                request.args.get("user_status"),
                field_name="user_status",
                allowed_values=OPERATOR_USER_STATUS_VALUES,
            ),
            "user_role": _parse_choice_query_param(
                request.args.get("user_role"),
                field_name="user_role",
                allowed_values=OPERATOR_USER_ROLE_VALUES,
            ),
            "quick_filter": _normalize_query_text(request.args.get("quick_filter")),
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
            ops_route.list_operator_users(app, page_index, page_size, filters)
        )

    @app.route(path_prefix + "/admin/operations/users/overview", methods=["GET"])
    def admin_operations_user_overview() -> str:
        """Operator user overview.

        ---
        tags:
            - User
        responses:
            200:
                description: Operator-visible user overview metrics
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationUserOverviewDTO"
        """
        _require_operator()
        return make_common_response(ops_route.get_operator_user_overview(app))


def register_admin_operations_user_detail_routes(app: Flask, path_prefix: str) -> None:
    """Register operator user detail and contact routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/detail", methods=["GET"]
    )
    def admin_operation_user_detail(user_bid: str) -> str:
        """Get operator user detail.

        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
        responses:
            200:
                description: Operator user detail
        """
        _require_operator()
        return make_common_response(ops_route.get_operator_user_detail(app, user_bid))

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/contact",
        methods=["POST"],
    )
    @sensitive_body(max_bytes=4096)
    def admin_operation_user_contact_change(user_bid: str) -> str:
        """Replace an operator-managed user's configured login contact."""
        _require_operator()
        try:
            payload = AdminOperationUserContactChangeRequestDTO.model_validate(
                request.get_json(silent=True) or {}
            )
        except ValidationError:
            raise_param_error("contact_change_payload")
        return make_common_response(
            ops_route.change_operator_user_contact(
                app,
                user_bid=user_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                contact_type=payload.contact_type,
                new_identifier=payload.identifier,
                reason=payload.reason,
            )
        )


def register_admin_operations_user_cancellation_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register operator account-cancellation routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/cancellation-preview",
        methods=["GET"],
    )
    def admin_operation_user_cancellation_preview(user_bid: str) -> str:
        """Preview blockers and warnings for operator account cancellation."""
        _require_operator()
        operator_user_bid = str(getattr(request.user, "user_id", "") or "")
        return make_common_response(
            ops_route.get_account_cancellation_preview(
                app,
                user_bid=user_bid,
                operator_user_bid=operator_user_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/transfer-published-courses",
        methods=["POST"],
    )
    def admin_operation_user_transfer_published_courses(user_bid: str) -> str:
        """Transfer every published course before cancelling its owner."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("payload")
        contact_type = _normalize_contact_type(payload.get("contact_type", ""))
        allowed_methods = ops_route._get_login_methods_enabled()
        if contact_type not in {"phone", "email"}:
            raise_param_error("contact_type")
        if allowed_methods and contact_type not in allowed_methods:
            raise_param_error("contact_type")
        identifiers = _validate_contacts(
            contact_type,
            _normalize_contacts(payload.get("identifier", "")),
        )
        if len(identifiers) != 1:
            raise_param_error("contact")
        return make_common_response(
            ops_route.transfer_operator_published_courses(
                app,
                previous_creator_user_bid=user_bid,
                contact_type=contact_type,
                identifier=identifiers[0],
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/cancel-subscription-renewals",
        methods=["POST"],
    )
    def admin_operation_user_cancel_subscription_renewals(user_bid: str) -> str:
        """Cancel future renewals before final account cancellation."""
        _require_operator()
        return make_common_response(
            ops_route.cancel_account_subscription_renewals(
                app,
                user_bid=user_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/cancel",
        methods=["POST"],
    )
    def admin_operation_user_cancel(user_bid: str) -> str:
        """Cancel and de-identify one user account."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("payload")
        return make_common_response(
            ops_route.request_user_account_cancellation(
                app,
                user_bid=user_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                cancellation_bid=str(payload.get("cancellation_bid", "") or ""),
                idempotency_key=str(
                    payload.get("idempotency_key")
                    or payload.get("cancellation_bid")
                    or ""
                ),
                preview_version=str(payload.get("preview_version", "") or ""),
                reason=str(payload.get("reason", "") or ""),
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/users/<user_bid>/cancellations/<cancellation_bid>",
        methods=["GET"],
    )
    def admin_operation_user_cancellation_status(
        user_bid: str, cancellation_bid: str
    ) -> str:
        """Return the durable account-cancellation task state."""
        _require_operator()
        return make_common_response(
            ops_route.get_account_cancellation_status(
                app,
                user_bid=user_bid,
                cancellation_bid=cancellation_bid,
            )
        )


def register_admin_operations_user_credit_routes(app: Flask, path_prefix: str) -> None:
    """Register operator user credit ledger routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/credits", methods=["GET"]
    )
    def admin_operation_user_credits(user_bid: str) -> str:
        """Get operator user credits detail.

        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
            - name: page_index
              type: integer
              required: false
            - name: page_size
              type: integer
              required: false
            - name: credit_type
              in: query
              type: string
              required: false
              description: Credit ledger type filter
            - name: grant_source
              in: query
              type: string
              required: false
              description: Grant source filter
            - name: course_query
              in: query
              type: string
              required: false
              description: Course ID exact match or course name fuzzy match for consume rows
            - name: usage_scene
              in: query
              type: string
              required: false
              description: Consume scene filter
            - name: usage_mode
              in: query
              type: string
              required: false
              description: Consume mode filter
            - name: start_time
              in: query
              type: string
              required: false
              description: Inclusive filter start time
            - name: end_time
              in: query
              type: string
              required: false
              description: Inclusive filter end time
        responses:
            200:
                description: Operator user credits detail
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

        filters = {
            "credit_type": request.args.get("credit_type", ""),
            "grant_source": request.args.get("grant_source", ""),
            "course_query": request.args.get("course_query", ""),
            "usage_scene": request.args.get("usage_scene", ""),
            "usage_mode": request.args.get("usage_mode", ""),
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
            ops_route.get_operator_user_credits(
                app,
                user_bid=user_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/users/<user_bid>/credits/usages/<usage_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_user_credit_usage_detail(user_bid: str, usage_bid: str) -> str:
        """Get operator user credit usage content detail.

        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
            - name: usage_bid
              in: path
              type: string
              required: true
              description: Usage business identifier
        responses:
            200:
                description: Operator user credit usage content detail
        """
        _require_operator()
        return make_common_response(
            ops_route.get_operator_user_credit_usage_detail(
                app,
                user_bid=user_bid,
                usage_bid=usage_bid,
            )
        )


def register_admin_operations_user_grant_routes(app: Flask, path_prefix: str) -> None:
    """Register operator credit and package grant routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/credit-grant/bootstrap",
        methods=["GET"],
    )
    def admin_operation_user_credit_grant_bootstrap(user_bid: str) -> str:
        """Get operator user grant bootstrap.

        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
        responses:
            200:
                description: Operator user grant bootstrap payload
        """
        _require_operator()
        return make_common_response(
            ops_route.get_operator_user_grant_bootstrap(
                app,
                user_bid=user_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/credits/grant",
        methods=["POST"],
    )
    def admin_operation_user_credit_grant(user_bid: str) -> str:
        """Grant operator user credits.

        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        $ref: "#/components/schemas/AdminOperationUserCreditGrantRequestDTO"
        responses:
            200:
                description: Operator user credits grant result
        """
        _require_operator()
        payload_data = request.get_json(silent=True) or {}
        try:
            payload = AdminOperationUserCreditGrantRequestDTO.model_validate(
                payload_data
            )
        except ValidationError:
            raise_param_error("credits_grant_payload")
        return make_common_response(
            ops_route.grant_operator_user_credits(
                app,
                user_bid=user_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/credits/deduct",
        methods=["POST"],
    )
    def admin_operation_user_credit_deduct(user_bid: str) -> str:
        """Deduct operator user credits with paid credits first."""
        _require_operator()
        payload_data = request.get_json(silent=True) or {}
        try:
            payload = AdminOperationUserCreditDeductionRequestDTO.model_validate(
                payload_data
            )
        except ValidationError:
            raise_param_error("credits_deduction_payload")
        return make_common_response(
            ops_route.deduct_operator_user_credits(
                app,
                user_bid=user_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/users/<user_bid>/packages/grant",
        methods=["POST"],
    )
    def admin_operation_user_package_grant(user_bid: str) -> str:
        """Grant operator user package.

        ---
        tags:
            - User
        parameters:
            - name: user_bid
              in: path
              type: string
              required: true
              description: User business identifier
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        $ref: "#/components/schemas/AdminOperationUserPackageGrantRequestDTO"
        responses:
            200:
                description: Operator user package grant result
        """
        _require_operator()
        payload_data = request.get_json(silent=True) or {}
        try:
            payload = AdminOperationUserPackageGrantRequestDTO.model_validate(
                payload_data
            )
        except ValidationError:
            raise_param_error("package_grant_payload")
        return make_common_response(
            ops_route.grant_operator_user_package(
                app,
                user_bid=user_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

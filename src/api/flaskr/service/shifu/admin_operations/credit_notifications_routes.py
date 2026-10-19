"""Register operator credit-notification and rate-config routes.

Service calls resolve through the route module so its patch targets stay effective.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.admin_operations.route_helpers import (
    CREDIT_NOTIFICATION_DELIVERY_STATUS_VALUES,
    CREDIT_NOTIFICATION_SKIP_REASON_VALUES,
    CREDIT_NOTIFICATION_STATUS_VALUES,
    _normalize_query_text,
    _parse_choice_query_param,
    _parse_datetime_filter,
    _parse_positive_query_int,
    _require_operator,
    _validate_datetime_range,
)

if TYPE_CHECKING:
    from flask import Flask


def register_admin_operations_credit_notification_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register credit-notification list, detail, and config routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/overview",
        methods=["GET"],
    )
    def admin_operation_credit_notifications_overview() -> str:
        """Return global operator credit notification overview."""
        _require_operator()
        return make_common_response(
            ops_route.get_operator_credit_notification_overview(app)
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications",
        methods=["GET"],
    )
    def admin_operation_credit_notifications() -> str:
        """List operator credit notification records."""
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
            "creator_bid": _normalize_query_text(request.args.get("creator_bid")),
            "creator_keyword": _normalize_query_text(
                request.args.get("creator_keyword")
            ),
            "target_user_bid": _normalize_query_text(
                request.args.get("target_user_bid")
            ),
            "mobile": _normalize_query_text(request.args.get("mobile")),
            "notification_type": _normalize_query_text(
                request.args.get("notification_type")
            ),
            "channel": _normalize_query_text(request.args.get("channel")),
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=CREDIT_NOTIFICATION_STATUS_VALUES,
            ),
            "delivery_status": _parse_choice_query_param(
                request.args.get("delivery_status"),
                field_name="delivery_status",
                allowed_values=CREDIT_NOTIFICATION_DELIVERY_STATUS_VALUES,
            ),
            "skip_reason": _parse_choice_query_param(
                request.args.get("skip_reason"),
                field_name="skip_reason",
                allowed_values=CREDIT_NOTIFICATION_SKIP_REASON_VALUES,
            ),
            "source_type": _normalize_query_text(request.args.get("source_type")),
            "source_bid": _normalize_query_text(request.args.get("source_bid")),
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
            ops_route.list_operator_credit_notifications(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/<notification_bid>",
        methods=["GET"],
    )
    def admin_operation_credit_notification_detail(notification_bid: str) -> str:
        """Return one operator credit notification record detail."""
        _require_operator()
        return make_common_response(
            ops_route.get_operator_credit_notification_detail(
                app,
                notification_bid=notification_bid,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/config",
        methods=["GET"],
    )
    def admin_operation_credit_notification_config() -> str:
        """Get operator credit notification config."""
        _require_operator()
        return make_common_response(
            ops_route.get_operator_credit_notification_config(app)
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/config",
        methods=["POST"],
    )
    def admin_operation_update_credit_notification_config() -> str:
        """Update operator credit notification config."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_config")
        return make_common_response(
            ops_route.update_operator_credit_notification_config(
                app,
                payload=payload,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )


def register_admin_operations_rate_config_routes(app: Flask, path_prefix: str) -> None:
    """Register operator rate-config routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/config/rates",
        methods=["GET"],
    )
    def admin_operation_rate_config() -> str:
        """Get operator-managed model and TTS credit rate config."""
        _require_operator()
        return make_common_response(ops_route.get_operator_rate_config(app))

    @app.route(
        path_prefix + "/admin/operations/config/rates",
        methods=["POST"],
    )
    def admin_operation_update_rate_config() -> str:
        """Update one operator-managed model or TTS credit rate config."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("rate_config")
        return make_common_response(
            ops_route.update_operator_rate_config(
                app,
                payload=payload,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )


def register_admin_operations_credit_notification_template_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register credit-notification template, dry-run, and requeue routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/templates/sync",
        methods=["POST"],
    )
    def admin_operation_credit_notification_template_sync() -> str:
        """Sync one SMS template for operator credit notification config."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_template_sync")
        return make_common_response(
            ops_route.sync_operator_credit_notification_template(
                app,
                notification_type=str(payload.get("notification_type") or ""),
                template_code=str(payload.get("template_code") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/templates",
        methods=["GET"],
    )
    def admin_operation_credit_notification_templates() -> str:
        """List SMS templates for operator credit notification config."""
        _require_operator()
        return make_common_response(
            ops_route.list_operator_credit_notification_templates(app)
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/email-templates",
        methods=["GET"],
    )
    def admin_operation_credit_notification_email_templates() -> str:
        """List operator-managed notification email templates."""
        _require_operator()
        return make_common_response(
            ops_route.list_operator_credit_notification_email_templates(app)
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/email-templates",
        methods=["POST"],
    )
    def admin_operation_create_credit_notification_email_template() -> str:
        """Create an operator-managed notification email template."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_email_template")
        return make_common_response(
            ops_route.save_operator_credit_notification_email_template(
                app,
                payload=payload,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/credit-notifications/email-templates/<notification_template_bid>",
        methods=["PUT"],
    )
    def admin_operation_update_credit_notification_email_template(
        notification_template_bid: str,
    ) -> str:
        """Update an operator-managed notification email template."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_email_template")
        return make_common_response(
            ops_route.save_operator_credit_notification_email_template(
                app,
                payload=payload,
                notification_template_bid=notification_template_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/credit-notifications/email-templates/<notification_template_bid>/status",
        methods=["PUT"],
    )
    def admin_operation_update_credit_notification_email_template_status(
        notification_template_bid: str,
    ) -> str:
        """Update one operator-managed notification email template's availability."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_email_template_status")
        return make_common_response(
            ops_route.update_operator_credit_notification_email_template_status(
                app,
                notification_template_bid=notification_template_bid,
                template_status=str(payload.get("template_status") or ""),
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/credit-notifications/dry-run",
        methods=["POST"],
    )
    def admin_operation_credit_notification_dry_run() -> str:
        """Dry-run operator credit notification scans."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("credit_notification_dry_run")
        return make_common_response(
            ops_route.dry_run_operator_credit_notifications(
                app,
                notification_type=str(payload.get("notification_type") or ""),
                creator_bid=str(payload.get("creator_bid") or ""),
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/credit-notifications/<notification_bid>/requeue",
        methods=["POST"],
    )
    def admin_operation_credit_notification_requeue(notification_bid: str) -> str:
        """Requeue one failed provider credit notification."""
        _require_operator()
        return make_common_response(
            ops_route.requeue_operator_credit_notification(
                app,
                notification_bid=notification_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

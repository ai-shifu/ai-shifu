"""Register operator referral routes.

Service calls resolve through the route module so its patch targets stay effective.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.admin_operations.route_helpers import (
    REFERRAL_CAMPAIGN_STATUS_VALUES,
    _normalize_query_text,
    _parse_choice_query_param,
    _parse_datetime_filter,
    _parse_digit_query_param,
    _parse_positive_query_int,
    _require_operator,
    _validate_datetime_range,
)

if TYPE_CHECKING:
    from flask import Flask


def register_admin_operations_referral_routes(app: Flask, path_prefix: str) -> None:
    """Register operator referral relation routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/referrals", methods=["GET"])
    def admin_operations_referrals() -> str:
        """List operator-visible referral invite relations."""
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
            "campaign_bid": _normalize_query_text(request.args.get("campaign_bid")),
            "inviter_user_bid": _normalize_query_text(
                request.args.get("inviter_user_bid")
            ),
            "invitee_user_bid": _normalize_query_text(
                request.args.get("invitee_user_bid")
            ),
            "invite_code": _normalize_query_text(request.args.get("invite_code")),
            "relation_status": _parse_digit_query_param(
                request.args.get("relation_status"),
                field_name="relation_status",
            ),
            "abnormal_status": _parse_digit_query_param(
                request.args.get("abnormal_status"),
                field_name="abnormal_status",
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
            ops_route.list_operator_referrals(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(path_prefix + "/admin/operations/referrals/overview", methods=["GET"])
    def admin_operations_referrals_overview() -> str:
        """Return operator referral overview metrics."""
        _require_operator()
        return make_common_response(ops_route.get_operator_referral_overview(app))

    @app.route(
        path_prefix + "/admin/operations/referrals/<relation_bid>",
        methods=["GET"],
    )
    def admin_operations_referral_detail(relation_bid: str) -> str:
        """Return one operator referral relation detail."""
        _require_operator()
        return make_common_response(
            ops_route.get_operator_referral_detail(app, relation_bid=relation_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/referrals/<relation_bid>/status",
        methods=["POST"],
    )
    def admin_operations_referral_status(relation_bid: str) -> str:
        """Update one referral relation or reward operator status."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_status")
        return make_common_response(
            ops_route.update_operator_referral_status(
                app,
                relation_bid=relation_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/referrals/<relation_bid>/adjustment",
        methods=["POST"],
    )
    def admin_operations_referral_adjustment(relation_bid: str) -> str:
        """Apply an audited operator adjustment to one referral relation."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_adjustment")
        return make_common_response(
            ops_route.update_operator_referral_status(
                app,
                relation_bid=relation_bid,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )


def register_admin_operations_referral_campaign_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register referral campaign list, create, and detail routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/promotions/referral-campaigns",
        methods=["GET"],
    )
    def admin_operations_promotion_referral_campaigns() -> str:
        """Operator referral campaign configuration list."""
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
                allowed_values=REFERRAL_CAMPAIGN_STATUS_VALUES,
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
            ops_route.list_operator_referral_campaigns(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/referral-campaigns",
        methods=["POST"],
    )
    def admin_create_operations_promotion_referral_campaign() -> str:
        """Create operator referral campaign configuration."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_campaign")
        return make_common_response(
            ops_route.create_operator_referral_campaign(
                app,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                payload=payload,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/promotions/referral-campaigns/<campaign_bid>",
        methods=["GET"],
    )
    def admin_operations_promotion_referral_campaign_detail(
        campaign_bid: str,
    ) -> str:
        """Get operator referral campaign configuration detail."""
        _require_operator()
        return make_common_response(
            ops_route.get_operator_referral_campaign_detail(
                app, campaign_bid=campaign_bid
            )
        )


def register_admin_operations_referral_campaign_member_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register referral campaign relation and invitation routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix
        + "/admin/operations/promotions/referral-campaigns/<campaign_bid>/relations",
        methods=["GET"],
    )
    def admin_operations_promotion_referral_campaign_relations(
        campaign_bid: str,
    ) -> str:
        """List invite relations for one referral campaign."""
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
            "campaign_bid": _normalize_query_text(campaign_bid),
            "inviter_user_bid": _normalize_query_text(
                request.args.get("inviter_user_bid")
            ),
            "invitee_user_bid": _normalize_query_text(
                request.args.get("invitee_user_bid")
            ),
            "invite_code": _normalize_query_text(request.args.get("invite_code")),
            "relation_status": _parse_digit_query_param(
                request.args.get("relation_status"),
                field_name="relation_status",
            ),
            "abnormal_status": _parse_digit_query_param(
                request.args.get("abnormal_status"),
                field_name="abnormal_status",
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
            ops_route.list_operator_referrals(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/promotions/referral-campaigns/<campaign_bid>/invitations",
        methods=["GET"],
    )
    def admin_operations_promotion_referral_campaign_invitations(
        campaign_bid: str,
    ) -> str:
        """List invite-code funnel data for one referral campaign."""
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
            "inviter_user_bid": _normalize_query_text(
                request.args.get("inviter_user_bid")
            ),
            "invite_code": _normalize_query_text(request.args.get("invite_code")),
            "status": _parse_digit_query_param(
                request.args.get("status"),
                field_name="status",
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
            ops_route.list_operator_referral_campaign_invitations(
                app,
                campaign_bid=campaign_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )


def register_admin_operations_referral_campaign_update_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register referral campaign update and status routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/promotions/referral-campaigns/<campaign_bid>",
        methods=["POST"],
    )
    def admin_update_operations_promotion_referral_campaign(
        campaign_bid: str,
    ) -> str:
        """Update operator referral campaign configuration."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_campaign")
        return make_common_response(
            ops_route.update_operator_referral_campaign(
                app,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                campaign_bid=campaign_bid,
                payload=payload,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/promotions/referral-campaigns/<campaign_bid>/status",
        methods=["POST"],
    )
    def admin_operations_promotion_referral_campaign_status(
        campaign_bid: str,
    ) -> str:
        """Update operator referral campaign configuration status."""
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("referral_campaign_status")
        return make_common_response(
            ops_route.update_operator_referral_campaign_status(
                app,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                campaign_bid=campaign_bid,
                enabled=payload.get("enabled"),
            )
        )

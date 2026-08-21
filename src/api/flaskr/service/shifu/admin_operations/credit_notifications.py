"""Handle credit notifications for course-administration operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.service.billing.api import (
    dry_run_credit_notifications,
    get_credit_notification_detail,
    list_credit_notification_templates,
    list_credit_notifications,
    load_credit_notification_policy_for_operator,
    requeue_credit_notification,
    save_credit_notification_policy,
    sync_credit_notification_template,
)
from flaskr.service.billing.api import (
    get_operator_credit_notification_overview as build_credit_notification_overview,
)

if TYPE_CHECKING:
    from flask import Flask


def get_operator_credit_notification_overview(app: Flask) -> dict[str, Any]:
    """Return operator credit notification overview."""
    return build_credit_notification_overview(app)


def list_operator_credit_notifications(
    app: Flask,
    *,
    page_index: int = 1,
    page_size: int = 20,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return operator credit notifications."""
    return list_credit_notifications(
        app,
        page_index=page_index,
        page_size=page_size,
        filters=filters,
    )


def get_operator_credit_notification_detail(
    app: Flask,
    *,
    notification_bid: str,
) -> dict[str, Any]:
    """Return operator credit notification detail."""
    return get_credit_notification_detail(app, notification_bid=notification_bid)


def get_operator_credit_notification_config(app: Flask) -> dict[str, Any]:
    """Return operator credit notification config."""
    with app.app_context():
        return load_credit_notification_policy_for_operator()


def update_operator_credit_notification_config(
    app: Flask,
    *,
    payload: dict[str, Any],
    operator_user_bid: str = "",
) -> dict[str, Any]:
    """Update operator credit notification config."""
    with app.app_context():
        save_credit_notification_policy(
            app,
            payload,
            preserve_opt_out=True,
            updated_by=operator_user_bid,
        )
        return load_credit_notification_policy_for_operator()


def sync_operator_credit_notification_template(
    app: Flask,
    *,
    notification_type: str,
    template_code: str,
) -> dict[str, Any]:
    """Synchronize operator credit notification template."""
    return sync_credit_notification_template(
        app,
        notification_type=notification_type,
        template_code=template_code,
    )


def list_operator_credit_notification_templates(app: Flask) -> dict[str, Any]:
    """Return operator credit notification templates."""
    return list_credit_notification_templates(app)


def dry_run_operator_credit_notifications(
    app: Flask,
    *,
    notification_type: str = "",
    creator_bid: str = "",
) -> dict[str, Any]:
    """Preview operator credit notifications."""
    return dry_run_credit_notifications(
        app,
        notification_type=notification_type,
        creator_bid=creator_bid,
    )


def requeue_operator_credit_notification(
    app: Flask,
    *,
    notification_bid: str,
    operator_user_bid: str = "",
) -> dict[str, Any]:
    """Requeue operator credit notification."""
    return requeue_credit_notification(
        app,
        notification_bid=notification_bid,
        operator_user_bid=operator_user_bid,
    )

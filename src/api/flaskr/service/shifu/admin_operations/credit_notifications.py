"""Handle credit notifications for course-administration operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.billing.api import (
    dry_run_credit_notifications,
    get_credit_notification_detail,
    list_credit_notification_email_templates,
    list_credit_notification_templates,
    list_credit_notifications,
    load_credit_notification_policy_for_operator,
    requeue_credit_notification,
    save_credit_notification_email_template,
    save_credit_notification_policy,
    sync_credit_notification_template,
    update_credit_notification_email_template_status,
)
from flaskr.service.billing.api import (
    get_operator_credit_notification_overview as build_credit_notification_overview,
)

if TYPE_CHECKING:
    from flask import Flask


def get_operator_credit_notification_overview(app: Flask) -> dict[str, object]:
    """Return operator credit notification overview."""
    return build_credit_notification_overview(app)


def list_operator_credit_notifications(
    app: Flask,
    *,
    page_index: int = 1,
    page_size: int = 20,
    filters: dict[str, object] | None = None,
) -> dict[str, object]:
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
) -> dict[str, object]:
    """Return operator credit notification detail."""
    return get_credit_notification_detail(app, notification_bid=notification_bid)


def get_operator_credit_notification_config(app: Flask) -> dict[str, object]:
    """Return operator credit notification config."""
    with app.app_context():
        return load_credit_notification_policy_for_operator()


def update_operator_credit_notification_config(
    app: Flask,
    *,
    payload: dict[str, object],
    operator_user_bid: str = "",
) -> dict[str, object]:
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
) -> dict[str, object]:
    """Synchronize operator credit notification template."""
    return sync_credit_notification_template(
        app,
        notification_type=notification_type,
        template_code=template_code,
    )


def list_operator_credit_notification_templates(app: Flask) -> dict[str, object]:
    """Return operator credit notification templates."""
    return list_credit_notification_templates(app)


def list_operator_credit_notification_email_templates(app: Flask) -> dict[str, object]:
    """Return operator-managed notification email templates."""
    return list_credit_notification_email_templates(app)


def save_operator_credit_notification_email_template(
    app: Flask,
    *,
    payload: dict[str, object],
    notification_template_bid: str = "",
    operator_user_bid: str = "",
) -> dict[str, object]:
    """Create or update an operator-managed notification email template."""
    return save_credit_notification_email_template(
        app,
        payload=payload,
        notification_template_bid=notification_template_bid,
        updated_by=operator_user_bid,
    )


def update_operator_credit_notification_email_template_status(
    app: Flask,
    *,
    notification_template_bid: str,
    template_status: str,
    operator_user_bid: str = "",
) -> dict[str, object]:
    """Update the availability of one operator-managed email template."""
    return update_credit_notification_email_template_status(
        app,
        notification_template_bid=notification_template_bid,
        template_status=template_status,
        updated_by=operator_user_bid,
    )


def dry_run_operator_credit_notifications(
    app: Flask,
    *,
    notification_type: str = "",
    creator_bid: str = "",
) -> dict[str, object]:
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
) -> dict[str, object]:
    """Requeue operator credit notification."""
    return requeue_credit_notification(
        app,
        notification_bid=notification_bid,
        operator_user_bid=operator_user_bid,
    )

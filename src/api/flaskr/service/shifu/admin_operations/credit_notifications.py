from __future__ import annotations

from typing import Any

from flask import Flask

from flaskr.service.billing.api import (
    dry_run_credit_notifications,
    get_credit_notification_detail,
    get_operator_credit_notification_overview as build_credit_notification_overview,
    list_credit_notification_templates,
    list_credit_notifications,
    load_credit_notification_policy_for_operator,
    requeue_credit_notification,
    save_credit_notification_policy,
    sync_credit_notification_template,
)


def get_operator_credit_notification_overview(app: Flask) -> dict[str, Any]:
    return build_credit_notification_overview(app)


def list_operator_credit_notifications(
    app: Flask,
    *,
    page_index: int = 1,
    page_size: int = 20,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    return get_credit_notification_detail(app, notification_bid=notification_bid)


def get_operator_credit_notification_config(app: Flask) -> dict[str, Any]:
    with app.app_context():
        return load_credit_notification_policy_for_operator()


def update_operator_credit_notification_config(
    app: Flask,
    *,
    payload: dict[str, Any],
    operator_user_bid: str = "",
) -> dict[str, Any]:
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
    return sync_credit_notification_template(
        app,
        notification_type=notification_type,
        template_code=template_code,
    )


def list_operator_credit_notification_templates(app: Flask) -> dict[str, Any]:
    return list_credit_notification_templates(app)


def dry_run_operator_credit_notifications(
    app: Flask,
    *,
    notification_type: str = "",
    creator_bid: str = "",
) -> dict[str, Any]:
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
    return requeue_credit_notification(
        app,
        notification_bid=notification_bid,
        operator_user_bid=operator_user_bid,
    )

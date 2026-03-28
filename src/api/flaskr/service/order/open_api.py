"""Open API service functions for external partner course authorization."""

from __future__ import annotations

from typing import Any, Dict

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.service.order.admin import (
    import_activation_order,
    normalize_contact_identifier,
)
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.utils import get_shifu_creator_bid
from flaskr.service.user.repository import load_user_aggregate_by_identifier


def verify_course_ownership(app: Flask, owner_bid: str, course_id: str) -> None:
    """Verify that the API key owner is the creator of the specified course."""
    creator_bid = get_shifu_creator_bid(app, course_id)
    if not creator_bid:
        raise_error("server.shifu.courseNotFound")
    if creator_bid != owner_bid:
        raise_error("server.openapi.courseOwnershipRequired")


def open_api_query_authorization(
    app: Flask,
    owner_bid: str,
    phone: str,
    course_id: str,
    contact_type: str = "phone",
) -> Dict[str, Any]:
    """Check if a user (by phone/email) has active authorization for a course."""
    with app.app_context():
        verify_course_ownership(app, owner_bid, course_id)
        normalized = normalize_contact_identifier(phone, contact_type)

        aggregate = load_user_aggregate_by_identifier(
            normalized, providers=[contact_type]
        )
        if not aggregate:
            return {"authorized": False, "order_bid": None}

        order = (
            Order.query.filter(
                Order.user_bid == aggregate.user_bid,
                Order.shifu_bid == course_id,
                Order.status == ORDER_STATUS_SUCCESS,
                Order.deleted == 0,
            )
            .order_by(Order.id.desc())
            .first()
        )

        if order:
            return {"authorized": True, "order_bid": order.order_bid}
        return {"authorized": False, "order_bid": None}


def open_api_grant_authorization(
    app: Flask,
    owner_bid: str,
    phone: str,
    course_id: str,
    contact_type: str = "phone",
) -> Dict[str, Any]:
    """Grant course authorization (create manual order).

    If the user already has an active authorization the existing order is
    returned without creating a duplicate.  If the user does not yet exist,
    a new account is created via import_activation_order.
    """
    with app.app_context():
        verify_course_ownership(app, owner_bid, course_id)

        normalized = normalize_contact_identifier(phone, contact_type)
        aggregate = load_user_aggregate_by_identifier(
            normalized, providers=[contact_type]
        )
        if aggregate:
            existing_order = (
                Order.query.filter(
                    Order.user_bid == aggregate.user_bid,
                    Order.shifu_bid == course_id,
                    Order.status == ORDER_STATUS_SUCCESS,
                    Order.deleted == 0,
                )
                .order_by(Order.id.desc())
                .first()
            )
            if existing_order:
                return {"order_bid": existing_order.order_bid}

        result = import_activation_order(
            app, phone, course_id, contact_type=contact_type
        )
        return result


def open_api_revoke_authorization(
    app: Flask,
    owner_bid: str,
    phone: str,
    course_id: str,
    contact_type: str = "phone",
) -> Dict[str, Any]:
    """Revoke course authorization by setting order status to REFUND (503)."""
    with app.app_context():
        verify_course_ownership(app, owner_bid, course_id)
        normalized = normalize_contact_identifier(phone, contact_type)

        aggregate = load_user_aggregate_by_identifier(
            normalized, providers=[contact_type]
        )
        if not aggregate:
            raise_error("server.openapi.noActiveAuthorization")

        order = (
            Order.query.filter(
                Order.user_bid == aggregate.user_bid,
                Order.shifu_bid == course_id,
                Order.status == ORDER_STATUS_SUCCESS,
                Order.deleted == 0,
            )
            .order_by(Order.id.desc())
            .first()
        )

        if not order:
            raise_error("server.openapi.noActiveAuthorization")

        order.status = ORDER_STATUS_REFUND
        db.session.commit()
        return {"order_bid": order.order_bid, "status": "revoked"}

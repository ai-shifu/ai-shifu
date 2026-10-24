"""Verify partner course authorization, idempotent grant, and lookup boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.order import open_api
from flaskr.service.order.consts import (
    ORDER_STATUS_REFUND,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.models import Order

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize("creator", [None, "another-owner"])
@pytest.mark.parametrize(
    "operation",
    ["open_api_query_order", "open_api_grant_order", "open_api_revoke_order"],
)
def test_foreign_or_missing_course_rejects_before_account_lookup(
    creator: str | None, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(open_api, "get_shifu_creator_bid", Mock(return_value=creator))
    lookup = Mock()
    monkeypatch.setattr(open_api, "load_user_aggregate_by_identifier", lookup)
    with pytest.raises(AppError):
        getattr(open_api, operation)(
            Flask(__name__),
            "owner-test",
            "course-test",
            "learner@example.test",
            "email",
        )
    lookup.assert_not_called()


@pytest.fixture
def authorized_partner(monkeypatch: pytest.MonkeyPatch) -> Callable:
    monkeypatch.setattr(
        open_api, "get_shifu_creator_bid", Mock(return_value="owner-test")
    )

    def configure_user(user_bid: str | None) -> Mock:
        lookup = Mock(
            return_value=SimpleNamespace(user_bid=user_bid) if user_bid else None
        )
        monkeypatch.setattr(open_api, "load_user_aggregate_by_identifier", lookup)
        return lookup

    return configure_user


@pytest.mark.parametrize(
    "status", [ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_REFUND]
)
def test_partner_query_requires_active_order_for_exact_user_and_course(
    status: int, app: Flask, authorized_partner: Callable
) -> None:
    user_bid, course_bid = uuid4().hex, uuid4().hex
    lookup = authorized_partner(user_bid)
    with app.app_context():
        order = Order(
            order_bid=uuid4().hex,
            user_bid=user_bid,
            shifu_bid=course_bid,
            status=status,
        )
        db.session.add_all(
            [
                order,
                Order(
                    order_bid=uuid4().hex,
                    user_bid=user_bid,
                    shifu_bid=uuid4().hex,
                    status=ORDER_STATUS_SUCCESS,
                ),
                Order(
                    order_bid=uuid4().hex,
                    user_bid=uuid4().hex,
                    shifu_bid=course_bid,
                    status=ORDER_STATUS_SUCCESS,
                ),
                Order(
                    order_bid=uuid4().hex,
                    user_bid=user_bid,
                    shifu_bid=course_bid,
                    status=ORDER_STATUS_SUCCESS,
                    deleted=1,
                ),
            ]
        )
        db.session.commit()
        order_bid = order.order_bid
    result = open_api.open_api_query_order(
        app, "owner-test", course_bid, " LEARNER@EXAMPLE.TEST ", "email"
    )
    assert result == {
        "authorized": status == ORDER_STATUS_SUCCESS,
        "order_bid": order_bid if status == ORDER_STATUS_SUCCESS else None,
    }
    lookup.assert_called_once_with("learner@example.test", providers=["email"])


def test_partner_query_unknown_account_is_not_authorized(
    authorized_partner: Callable,
) -> None:
    authorized_partner(None)
    assert open_api.open_api_query_order(
        Flask(__name__), "owner-test", "course-test", "learner@example.test", "email"
    ) == {"authorized": False, "order_bid": None}


@pytest.mark.parametrize("existing_user", [False, True])
def test_partner_grant_creates_activation_when_no_active_order_exists(
    existing_user: bool,
    app: Flask,
    authorized_partner: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorized_partner(uuid4().hex if existing_user else None)
    importer = Mock(return_value={"order_bid": "new-order"})
    monkeypatch.setattr(open_api, "import_activation_order", importer)
    with app.app_context():
        result = open_api.open_api_grant_order(
            app, "owner-test", "course-test", "learner@example.test", "email"
        )
    assert result == {"order_bid": "new-order"}
    importer.assert_called_once_with(
        app,
        "learner@example.test",
        "course-test",
        contact_type="email",
        payment_channel="open_api",
    )


def test_partner_grant_returns_existing_active_order_without_duplicate(
    app: Flask, authorized_partner: Callable, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid, course_bid = uuid4().hex, uuid4().hex
    authorized_partner(user_bid)
    importer = Mock()
    monkeypatch.setattr(open_api, "import_activation_order", importer)
    with app.app_context():
        order = Order(
            order_bid=uuid4().hex,
            user_bid=user_bid,
            shifu_bid=course_bid,
            status=ORDER_STATUS_SUCCESS,
        )
        db.session.add(order)
        db.session.commit()
        result = open_api.open_api_grant_order(
            app, "owner-test", course_bid, "learner@example.test", "email"
        )
        assert result == {"order_bid": order.order_bid}
    importer.assert_not_called()


@pytest.mark.parametrize("existing_user", [False, True])
def test_partner_revocation_without_active_access_does_not_notify(
    existing_user: bool,
    app: Flask,
    authorized_partner: Callable,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorized_partner(uuid4().hex if existing_user else None)
    notify = Mock()
    monkeypatch.setattr(open_api, "send_revoke_feishu", notify)
    with app.app_context(), pytest.raises(AppError):
        open_api.open_api_revoke_order(
            app, "owner-test", uuid4().hex, "learner@example.test", "email"
        )
    notify.assert_not_called()

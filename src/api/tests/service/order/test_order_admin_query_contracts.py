"""Verify administrative order filters against persisted orders and coupon usage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.order import admin
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order
from flaskr.service.promo.models import CouponUsage
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import UserInfo

if TYPE_CHECKING:
    from flask import Flask


@pytest.fixture
def order_query_data(app: Flask, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    course_bid, other_course_bid, user_bid = uuid4().hex, uuid4().hex, uuid4().hex
    name = f"Course {uuid4().hex}"
    specs = [
        ("manual", 0),
        ("open_api", 0),
        ("stripe", 0),
        ("stripe", 50),
        ("pingxx", 0),
        ("pingxx", 50),
        ("alipay", 25),
    ]
    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(shifu_bid=course_bid, title=f"Draft {name}"),
                PublishedShifu(shifu_bid=course_bid, title=name),
                DraftShifu(shifu_bid=other_course_bid, title=f"Unpublished {name}"),
                UserInfo(
                    user_bid=user_bid,
                    user_identify=f"{user_bid}@example.test",
                    nickname="Test learner",
                ),
            ]
        )
        orders = [
            Order(
                order_bid=uuid4().hex,
                shifu_bid=course_bid,
                user_bid=user_bid,
                payment_channel=provider,
                payable_price=100,
                paid_price=amount,
                status=ORDER_STATUS_SUCCESS,
                created_at=datetime(2026, 1, index + 1),
            )
            for index, (provider, amount) in enumerate(specs)
        ]
        foreign_order = Order(
            order_bid=uuid4().hex,
            shifu_bid=other_course_bid,
            user_bid=user_bid,
            payment_channel="stripe",
            paid_price=25,
            status=ORDER_STATUS_TO_BE_PAID,
        )
        db.session.add_all([*orders, foreign_order])
        db.session.add_all(
            [
                CouponUsage(
                    order_bid=orders[2].order_bid,
                    code="FIRST",
                    coupon_usage_bid=uuid4().hex,
                ),
                CouponUsage(
                    order_bid=orders[2].order_bid,
                    code="SECOND",
                    coupon_usage_bid=uuid4().hex,
                ),
                CouponUsage(
                    order_bid=orders[2].order_bid,
                    code="FIRST",
                    coupon_usage_bid=uuid4().hex,
                ),
                CouponUsage(
                    order_bid=orders[2].order_bid,
                    code="DELETED",
                    coupon_usage_bid=uuid4().hex,
                    deleted=1,
                ),
                CouponUsage(
                    order_bid=orders[2].order_bid, code="", coupon_usage_bid=uuid4().hex
                ),
            ]
        )
        db.session.commit()
        bids = [order.order_bid for order in orders]
        foreign_bid = foreign_order.order_bid
    monkeypatch.setattr(
        admin, "get_user_created_shifu_bids", lambda *_args: [course_bid]
    )
    monkeypatch.setattr(admin, "resolve_market_payment_provider", lambda: "stripe")
    return SimpleNamespace(
        course_bid=course_bid,
        other_course_bid=other_course_bid,
        user_bid=user_bid,
        name=name,
        bids=bids,
        foreign_bid=foreign_bid,
    )


@pytest.mark.parametrize(
    ("source", "indexes"),
    [
        ("import_activation", [0]),
        ("open_api", [1]),
        ("coupon_redeem", [2]),
        ("user_purchase", [3, 4, 5, 6]),
        ("unknown", []),
    ],
)
def test_operator_order_source_filters_use_persisted_coupon_evidence(
    source: str, indexes: list[int], order_query_data: SimpleNamespace, app: Flask
) -> None:
    data = order_query_data
    result = admin.list_operator_orders(
        app, 1, 20, {"shifu_bid": data.course_bid, "order_source": source}
    )
    assert {item.order_bid for item in result.data} == {
        data.bids[index] for index in indexes
    }
    assert result.total == len(indexes)
    if source == "coupon_redeem":
        assert result.data[0].coupon_codes == ["FIRST", "SECOND"]
        assert Decimal(result.data[0].paid_price) == 0


@pytest.mark.parametrize(
    ("channel", "indexes"),
    [("stripe", [2, 3, 4]), ("pingxx", [5]), ("alipay", [6]), ("manual", [0])],
)
def test_channel_filter_matches_displayed_market_channel_for_free_legacy_orders(
    channel: str, indexes: list[int], order_query_data: SimpleNamespace, app: Flask
) -> None:
    result = admin.list_orders(app, "teacher-test", 1, 20, {"payment_channel": channel})
    assert {item.order_bid for item in result.data} == {
        order_query_data.bids[index] for index in indexes
    }
    assert {item.payment_channel for item in result.data} == {channel}


@pytest.mark.parametrize("course_filter", ["list", "comma-separated", "foreign"])
def test_teacher_course_filter_is_intersected_with_owned_courses(
    course_filter: str, order_query_data: SimpleNamespace, app: Flask
) -> None:
    data = order_query_data
    courses: object = [data.course_bid, data.other_course_bid]
    if course_filter == "comma-separated":
        courses = f" {data.course_bid} , {data.other_course_bid} "
    elif course_filter == "foreign":
        courses = [data.other_course_bid]
    result = admin.list_orders(app, "teacher-test", 1, 20, {"shifu_bid": courses})
    assert {item.order_bid for item in result.data} == (
        set() if course_filter == "foreign" else set(data.bids)
    )
    assert data.foreign_bid not in {item.order_bid for item in result.data}


@pytest.mark.parametrize("identify_kind", ["identifier", "user_bid"])
def test_teacher_filters_account_by_identifier_or_business_id_and_utc_window(
    identify_kind: str, order_query_data: SimpleNamespace, app: Flask
) -> None:
    data = order_query_data
    user_filter = (
        f"{data.user_bid}@example.test"
        if identify_kind == "identifier"
        else data.user_bid
    )
    result = admin.list_orders(
        app,
        "teacher-test",
        0,
        0,
        {
            "user_bid": user_filter,
            "status": str(ORDER_STATUS_SUCCESS),
            "start_time": "2026-01-04T00:00:00Z",
            "end_time": "2026-01-04T23:59:59Z",
        },
    )
    assert result.page == 1
    assert result.page_size == 1
    assert result.total == 1
    assert result.data[0].order_bid == data.bids[3]
    assert result.data[0].shifu_name == data.name
    assert result.data[0].user_email == f"{data.user_bid}@example.test"
    assert Decimal(result.data[0].discount_amount) == 50


@pytest.mark.parametrize("filter_name", ["course_query", "course_name"])
def test_operator_course_search_finds_draft_and_published_titles_without_duplicates(
    filter_name: str, order_query_data: SimpleNamespace, app: Flask
) -> None:
    data = order_query_data
    result = admin.list_operator_orders(app, 1, 20, {filter_name: data.name})
    assert result.total == 8
    assert {item.order_bid for item in result.data} == {*data.bids, data.foreign_bid}
    assert (
        next(
            item for item in result.data if item.order_bid == data.foreign_bid
        ).shifu_name
        == f"Unpublished {data.name}"
    )


def test_operator_course_query_accepts_exact_business_id(
    order_query_data: SimpleNamespace, app: Flask
) -> None:
    result = admin.list_operator_orders(
        app, 1, 20, {"course_query": order_query_data.course_bid}
    )
    assert {item.order_bid for item in result.data} == set(order_query_data.bids)


def test_operator_unknown_course_returns_empty_page(app: Flask) -> None:
    result = admin.list_operator_orders(app, 1, 20, {"course_name": uuid4().hex})
    assert result.total == 0
    assert result.data == []


def test_teacher_without_courses_cannot_read_global_orders(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin, "get_user_created_shifu_bids", lambda *_args: [])
    result = admin.list_orders(app, "teacher-without-courses", 1, 20)
    assert result.total == 0
    assert result.data == []

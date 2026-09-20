"""Verify committed order summaries, notification evidence, and discount limits."""

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.i18n import _
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import (
    COUPON_TYPE_FIXED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
)
from flaskr.service.promo.models import (
    Coupon,
    CouponUsage,
    PromoCampaign,
    PromoRedemption,
)
from flaskr.service.user.consts import USER_STATE_PAID, USER_STATE_REGISTERED
from flaskr.service.user.models import UserConversion, UserInfo
from flaskr.util.datetime import now_utc
from sqlalchemy import text

from tests.service.billing.test_billing_callbacks import billing_callback_app

__all__ = ["billing_callback_app"]


@pytest.fixture
def summary_scope(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SimpleNamespace]:
    with app.app_context():
        order = Order(
            order_bid=uuid4().hex,
            user_bid=uuid4().hex,
            shifu_bid=uuid4().hex,
            status=ORDER_STATUS_SUCCESS,
            payment_channel="stripe",
            payable_price=100,
            paid_price=75,
        )
        db.session.add(order)
        db.session.flush()
        notify = Mock()
        monkeypatch.setattr(funs, "send_notify", notify)
        monkeypatch.setattr(
            funs, "get_shifu_info", Mock(return_value=SimpleNamespace(title="Course"))
        )
        yield SimpleNamespace(order=order, notify=notify)
        db.session.rollback()
        UserInfo.query.filter_by(user_bid=order.user_bid).delete()
        Order.query.filter_by(order_bid=order.order_bid).delete()
        db.session.commit()


@pytest.mark.parametrize("initial_state", [1, USER_STATE_REGISTERED])
def test_payment_success_persists_canonical_user_state_and_repeated_processing_keeps_it(
    app: object,
    summary_scope: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    initial_state: int,
) -> None:
    order = summary_scope.order
    order.status = ORDER_STATUS_TO_BE_PAID
    user = UserInfo(user_bid=order.user_bid, state=initial_state)
    db.session.add(user)
    db.session.commit()
    monkeypatch.setattr(funs, "send_order_feishu", Mock())
    monkeypatch.setattr(funs, "get_shifu_creator_bid", Mock(return_value=""))

    assert funs.query_buy_record(app, order.order_bid).status == ORDER_STATUS_TO_BE_PAID
    db.session.expire_all()
    assert user.state == initial_state

    for _attempt in range(2):
        result = funs.success_buy_record(app, order.order_bid)
        db.session.expire_all()
        assert result.status == ORDER_STATUS_SUCCESS
        assert order.status == ORDER_STATUS_SUCCESS
        assert user.state == USER_STATE_PAID


@pytest.mark.parametrize("channel", ["stripe", "manual", "custom", ""])
def test_notification_uses_real_order_coupon_and_conversion_evidence(
    app: object,
    summary_scope: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    channel: str,
) -> None:
    scope = summary_scope
    scope.order.payment_channel = channel
    coupon = Coupon(
        coupon_bid=uuid4().hex,
        name="Reward",
        code="TEST",
        value=25,
        discount_type=COUPON_TYPE_FIXED,
        filter="{}",
    )
    db.session.add(coupon)
    db.session.add(
        CouponUsage(coupon_bid=coupon.coupon_bid, order_bid=scope.order.order_bid)
    )
    db.session.add(UserInfo(user_bid=scope.order.user_bid, state=USER_STATE_PAID))
    db.session.add(UserConversion(scope.order.user_bid, uuid4().hex, "newsletter", 1))
    db.session.flush()
    db.session.expire_all()
    monkeypatch.setattr(
        funs,
        "load_user_aggregate",
        Mock(return_value=SimpleNamespace(mobile="13000000000", name="Learner")),
    )
    funs.send_order_feishu(app, scope.order.order_bid)

    scope.notify.assert_called_once()
    notified_app, title, messages = scope.notify.call_args.args
    assert notified_app is app
    assert title
    assert any(message.endswith("newsletter") for message in messages)
    assert any(message.endswith("TEST") for message in messages)
    assert any(
        "Reward (TEST)" in message and message.endswith("25.00") for message in messages
    )
    if channel == "custom":
        assert any(message.endswith("custom") for message in messages)
    summary = funs.query_buy_record(app, scope.order.order_bid).__json__()
    assert summary["price"] == "100"
    assert summary["discount"] == "25"
    assert summary["value_to_pay"] == "75"
    assert summary["price_item"] == [
        {
            "name": _("server.order.payItemCoupon"),
            "price_name": "Reward (TEST)",
            "price": "25.00",
            "is_discount": True,
        }
    ]


@pytest.mark.parametrize("missing", ["user", "course"])
def test_notification_skips_unresolvable_order_dependencies(
    app: object,
    summary_scope: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    aggregate = None if missing == "user" else SimpleNamespace(mobile="", name="")
    monkeypatch.setattr(funs, "load_user_aggregate", Mock(return_value=aggregate))
    if missing == "course":
        funs.get_shifu_info.return_value = None
    funs.send_order_feishu(app, summary_scope.order.order_bid)
    summary_scope.notify.assert_not_called()
    if missing == "user":
        funs.get_shifu_info.assert_not_called()


@pytest.mark.parametrize("course_exists", [True, False])
def test_revocation_notification_uses_course_title_or_stable_identifier(
    app: object, summary_scope: SimpleNamespace, course_exists: bool
) -> None:
    scope = summary_scope
    if not course_exists:
        funs.get_shifu_info.return_value = None
    funs.send_revoke_feishu(app, scope.order.order_bid, "learner@example.test")
    messages = scope.notify.call_args.args[2]
    assert messages[1].endswith("Course" if course_exists else scope.order.shifu_bid)
    assert messages[2].endswith(scope.order.order_bid)
    scope.notify.reset_mock()
    funs.send_revoke_feishu(app, uuid4().hex, "learner@example.test")
    scope.notify.assert_not_called()


def test_promotion_supplement_excludes_voided_deleted_and_duplicates_and_caps_total(
    summary_scope: SimpleNamespace,
) -> None:
    scope = summary_scope
    now = now_utc()
    campaign = PromoCampaign(promo_bid=uuid4().hex, name="Current campaign name")
    db.session.add(campaign)
    # The newest eligible evidence is considered first; ignored rows must not
    # consume the remaining discount budget.
    for minutes, name, amount, status, deleted, bid in [
        (0, "Deleted", 100, PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED, 1, ""),
        (1, "Voided", 100, PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED, 0, ""),
        (2, "Existing", 30, PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED, 0, ""),
        (3, "Zero", 0, PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED, 0, ""),
        (
            4,
            "Old campaign name",
            100,
            PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
            0,
            campaign.promo_bid,
        ),
        (5, "Excess", 50, PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED, 0, ""),
    ]:
        db.session.add(
            PromoRedemption(
                order_bid=scope.order.order_bid,
                promo_bid=bid,
                promo_name=name,
                discount_amount=amount,
                status=status,
                deleted=deleted,
                updated_at=now - timedelta(minutes=minutes),
            )
        )
    db.session.flush()
    items = [
        funs.PayItemDto(
            "Promotion", "Existing", Decimal(5), is_discount=True, discount_code=None
        )
    ]

    result = funs._supplement_promo_discount_items(
        scope.order.order_bid, items, Decimal(25)
    )

    assert result is items
    assert [(item.price_name, item.price) for item in result] == [
        ("Existing", Decimal(5)),
        ("Current campaign name", Decimal(20)),
    ]
    assert funs._sum_discount_items(result) == Decimal(25)
    assert (
        funs._supplement_promo_discount_items(
            scope.order.order_bid, result, Decimal(25)
        )
        is result
    )
    assert len(result) == 2


@pytest.mark.parametrize(
    ("states", "expected_counts"),
    [
        ([0, 1, 2, 3], ["1", "3", "4"]),
        ([1101, 1102, 1103, 1104], ["1", "3", "4"]),
        ([0, 1, 2, 3, 1101, 1102, 1103, 1104], ["2", "6", "8"]),
    ],
    ids=["legacy", "canonical", "mixed"],
)
def test_notification_counts_historical_states_without_changing_persisted_accounts(
    billing_callback_app: object,
    monkeypatch: pytest.MonkeyPatch,
    states: list[int],
    expected_counts: list[str],
) -> None:
    app = billing_callback_app
    active_users = [UserInfo(user_bid=uuid4().hex, state=state) for state in states]
    deleted_users = [
        UserInfo(user_bid=uuid4().hex, state=state, deleted=1) for state in states
    ]
    order = Order(
        order_bid=uuid4().hex,
        user_bid=active_users[3].user_bid,
        shifu_bid=uuid4().hex,
        payment_channel="stripe",
        status=ORDER_STATUS_SUCCESS,
        payable_price=10,
        paid_price=10,
    )
    db.session.add_all([*active_users, *deleted_users, order])
    db.session.commit()
    # Raw SQL proves the database retains both representations without binding hooks.
    stored_before = db.session.execute(
        text("SELECT user_bid, state, deleted FROM user_users ORDER BY id")
    ).all()
    assert [row.state for row in stored_before] == states + states
    assert [row.deleted for row in stored_before] == [0] * len(states) + [1] * len(
        states
    )
    monkeypatch.setattr(
        funs, "get_shifu_info", Mock(return_value=SimpleNamespace(title="Course"))
    )
    notify = Mock()
    monkeypatch.setattr(funs, "send_notify", notify)

    funs.send_order_feishu(app, order.order_bid)

    notify.assert_called_once()
    notified_app, _title, messages = notify.call_args.args
    assert notified_app is app
    assert [message.rsplit("：", 1)[-1] for message in messages[-3:]] == expected_counts
    db.session.expire_all()
    assert (
        db.session.execute(
            text("SELECT user_bid, state, deleted FROM user_users ORDER BY id")
        ).all()
        == stored_before
    )
    assert order.status == ORDER_STATUS_SUCCESS

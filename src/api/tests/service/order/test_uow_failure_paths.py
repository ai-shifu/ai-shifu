"""Mid-flow-failure tests for the order unit-of-work migration (B4a).

Before the migration, ``order/funs.py`` committed 13 times mid-flow, so a
failure late in a flow left earlier writes permanently committed. These tests
pin the new semantics: an entry point owns one ``unit_of_work()`` and a late
failure rolls back everything written inside it.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.dao import uow
from flaskr.service.order import funs as order_funs
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TIMEOUT,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.funs import init_buy_record, success_buy_record
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import (
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
)
from flaskr.service.promo.models import Coupon, CouponUsage, PromoRedemption

USER_ID = "uow-user-1"
COURSE_ID = "uow-course-1"


@pytest.fixture
def order_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REDIS_KEY_PREFIX="uow-order-test",
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


@pytest.fixture
def stub_shifu(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "c1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_a, **_k: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(
            price=Decimal("100.00"),
            title="UOW course",
            description="UOW failure-path course",
        ),
    )


@pytest.fixture
def stub_promo_side_sessions(monkeypatch: pytest.MonkeyPatch):
    """Neutralize the promo helpers that push their own app context.

    ``timeout_coupon_code_rollback`` / ``void_promo_campaign_applications``
    open a nested app context and commit a *separate* session (documented
    cross-module boundary leak, out of scope for this batch). Stub them so
    these tests observe only the order module's own unit of work.
    """
    calls = {"rollback": 0, "void": 0}
    monkeypatch.setattr(
        order_funs,
        "timeout_coupon_code_rollback",
        lambda *_a, **_k: calls.__setitem__("rollback", calls["rollback"] + 1),
    )
    monkeypatch.setattr(
        order_funs,
        "void_promo_campaign_applications",
        lambda *_a, **_k: calls.__setitem__("void", calls["void"] + 1),
    )
    return calls


def _fail_after_pricing_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the real pricing sync, then fail — simulating any late step error."""
    real_sync = order_funs._sync_order_campaign_pricing

    def failing_sync(*args, **kwargs):
        real_sync(*args, **kwargs)
        raise RuntimeError("boom after pricing sync")

    monkeypatch.setattr(order_funs, "_sync_order_campaign_pricing", failing_sync)


def _seed_order(**overrides) -> str:
    order = Order(
        order_bid=overrides.pop("order_bid", "uow-origin-order"),
        user_bid=USER_ID,
        shifu_bid=COURSE_ID,
        payable_price=Decimal("100.00"),
        paid_price=Decimal("100.00"),
        status=overrides.pop("status", ORDER_STATUS_INIT),
        **overrides,
    )
    dao.db.session.add(order)
    dao.db.session.commit()
    return order.order_bid


def test_init_buy_record_late_failure_persists_nothing(
    order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    stub_shifu,
):
    """(a) A late failure in init_buy_record must not leave partial rows.

    Pre-migration, ``_sync_order_campaign_pricing`` committed the new Order
    row and the promo applications before the failure point.
    """

    def fake_apply_promo(_app, **kwargs):
        application = PromoRedemption(
            redemption_bid="uow-redemption-1",
            promo_bid="uow-promo-1",
            order_bid=kwargs["order_bid"],
            user_bid=kwargs["user_bid"],
            shifu_bid=kwargs["shifu_bid"],
            promo_name="UOW promo",
            discount_amount=Decimal("10.00"),
            status=PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
        )
        dao.db.session.add(application)
        return [application]

    monkeypatch.setattr(order_funs, "apply_promo_campaigns", fake_apply_promo)
    _fail_after_pricing_sync(monkeypatch)

    with pytest.raises(RuntimeError, match="boom after pricing sync"):
        init_buy_record(order_app, USER_ID, COURSE_ID)

    dao.db.session.rollback()
    assert Order.query.count() == 0
    assert PromoRedemption.query.count() == 0


def test_init_buy_record_timeout_flip_persists_with_replacement_order(
    order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    stub_shifu,
    stub_promo_side_sessions,
):
    """(b) Clean run: the timeout flip and the new order commit together."""
    monkeypatch.setattr(order_funs, "apply_promo_campaigns", lambda *_a, **_k: [])
    stale_created_at = datetime.datetime.now(datetime.timezone.utc).replace(
        tzinfo=None
    ) - datetime.timedelta(hours=2)
    origin_bid = _seed_order(created_at=stale_created_at)

    result = init_buy_record(order_app, USER_ID, COURSE_ID)

    dao.db.session.expire_all()
    origin = Order.query.filter(Order.order_bid == origin_bid).first()
    assert origin.status == ORDER_STATUS_TIMEOUT
    assert result.order_id != origin_bid
    assert Order.query.count() == 2
    assert stub_promo_side_sessions == {"rollback": 1, "void": 1}


def test_init_buy_record_timeout_flip_rolls_back_on_late_failure(
    order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    stub_shifu,
    stub_promo_side_sessions,
):
    """(b) Failure run: the timeout flip joins the caller's transaction.

    Decision: the flip is derived state (recomputed from ``created_at`` on
    every attempt), so it must NOT survive a failed order-creation attempt.
    A retry re-detects the timeout and re-flips atomically with the
    replacement order.
    """
    monkeypatch.setattr(order_funs, "apply_promo_campaigns", lambda *_a, **_k: [])
    stale_created_at = datetime.datetime.now(datetime.timezone.utc).replace(
        tzinfo=None
    ) - datetime.timedelta(hours=2)
    origin_bid = _seed_order(created_at=stale_created_at)
    _fail_after_pricing_sync(monkeypatch)

    with pytest.raises(RuntimeError, match="boom after pricing sync"):
        init_buy_record(order_app, USER_ID, COURSE_ID)

    dao.db.session.rollback()
    dao.db.session.expire_all()
    origin = Order.query.filter(Order.order_bid == origin_bid).first()
    assert origin.status == ORDER_STATUS_INIT  # flip rolled back
    assert Order.query.count() == 1  # no replacement order persisted


def test_discount_refresh_failure_keeps_coupon_pricing_untouched(
    order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    stub_shifu,
):
    """(c) A failure after the discount recalculation leaves pricing intact.

    Pre-migration, ``_sync_order_campaign_pricing`` committed the recomputed
    ``paid_price`` (coupon applied) before order validation could fail.
    """
    monkeypatch.setattr(order_funs, "apply_promo_campaigns", lambda *_a, **_k: [])
    origin_bid = _seed_order()
    coupon = Coupon(
        coupon_bid="uow-coupon-1",
        code="UOWTEST",
        name="UOW coupon",
        discount_type=COUPON_TYPE_FIXED,
        value=Decimal("20.00"),
        filter="",
    )
    usage = CouponUsage(
        coupon_usage_bid="uow-coupon-usage-1",
        coupon_bid=coupon.coupon_bid,
        user_bid=USER_ID,
        order_bid=origin_bid,
        code=coupon.code,
        discount_type=COUPON_TYPE_FIXED,
        value=Decimal("20.00"),
        status=COUPON_STATUS_USED,
    )
    dao.db.session.add_all([coupon, usage])
    dao.db.session.commit()
    _fail_after_pricing_sync(monkeypatch)

    with pytest.raises(RuntimeError, match="boom after pricing sync"):
        init_buy_record(order_app, USER_ID, COURSE_ID)

    dao.db.session.rollback()
    dao.db.session.expire_all()
    origin = Order.query.filter(Order.order_bid == origin_bid).first()
    # The recomputed coupon discount (100 -> 80) must not persist.
    assert origin.paid_price == Decimal("100.00")
    refreshed_usage = CouponUsage.query.filter(
        CouponUsage.coupon_usage_bid == "uow-coupon-usage-1"
    ).first()
    assert refreshed_usage.status == COUPON_STATUS_USED


def test_success_buy_record_commits_alone_but_joins_outer_unit_of_work(
    order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    stub_shifu,
):
    """The key migration property: self-committing at top level, joining when
    nested — legacy callers (coupon_funcs, admin) and migrated owners both
    stay correct."""
    monkeypatch.setattr(order_funs, "set_user_state", lambda *_a, **_k: None)
    feishu_calls = []
    monkeypatch.setattr(
        order_funs,
        "send_order_feishu",
        lambda *_a, **_k: feishu_calls.append("sent"),
    )
    order_bid = _seed_order(status=ORDER_STATUS_TO_BE_PAID)

    # Nested: an outer failure must roll the success flip back too, and the
    # Feishu notification scheduled via uow.on_commit must be dropped — the
    # old code notified for a flip that could later be rolled back.
    with pytest.raises(RuntimeError, match="outer boom"):
        with uow.unit_of_work():
            success_buy_record(order_app, order_bid)
            assert feishu_calls == []  # not yet durable, must not notify
            raise RuntimeError("outer boom")
    dao.db.session.expire_all()
    order = Order.query.filter(Order.order_bid == order_bid).first()
    assert order.status == ORDER_STATUS_TO_BE_PAID
    assert feishu_calls == []

    # Top level: legacy self-committing behavior is preserved and the
    # notification fires exactly once, after the commit.
    success_buy_record(order_app, order_bid)
    dao.db.session.expire_all()
    order = Order.query.filter(Order.order_bid == order_bid).first()
    assert order.status == ORDER_STATUS_SUCCESS
    assert feishu_calls == ["sent"]

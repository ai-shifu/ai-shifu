"""Keep rejected coupons from changing pending payment and committed discounts."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.order import coupon_funcs as coupons
from flaskr.service.order import funs
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import (
    COUPON_APPLY_TYPE_ALL,
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_STATUS_ACTIVE,
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
)
from flaskr.service.promo.models import Coupon, CouponUsage
from flaskr.service.user.models import UserConversion
from flaskr.util.datetime import now_utc


@pytest.fixture
def coupon_scope(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SimpleNamespace]:
    user, bid, code = (uuid.uuid4().hex for _ in range(3))
    cancel = Mock()
    notify = Mock()
    notify_function = coupons.send_feishu_coupon_code
    monkeypatch.setattr(coupons, "cancel_pending_payment_for_repricing", cancel)
    monkeypatch.setattr(coupons, "send_feishu_coupon_code", notify)
    monkeypatch.setattr(funs, "send_order_feishu", Mock())
    monkeypatch.setattr(funs, "set_user_state", Mock())
    monkeypatch.setattr(funs, "get_shifu_creator_bid", lambda *_args: "")
    with app.app_context():
        row = Order(
            order_bid=bid,
            user_bid=user,
            shifu_bid=uuid.uuid4().hex,
            paid_price=100,
            payable_price=100,
            status=ORDER_STATUS_TO_BE_PAID,
        )
        db.session.add(row)
        db.session.commit()
        yield SimpleNamespace(
            order=row,
            user=user,
            code=code,
            cancel=cancel,
            notify=notify,
            notify_function=notify_function,
        )
        db.session.rollback()
        CouponUsage.query.filter_by(code=code).delete()
        Coupon.query.filter_by(code=code).delete()
        Order.query.filter_by(order_bid=bid).delete()
        UserConversion.query.filter_by(user_id=user).delete()
        db.session.commit()


def _coupon(scope: SimpleNamespace, **overrides: object) -> Coupon:
    row = Coupon(
        **{
            "coupon_bid": uuid.uuid4().hex,
            "code": scope.code,
            "value": 10,
            "filter": "{}",
            "status": 1,
            "usage_type": COUPON_APPLY_TYPE_ALL,
            "start": now_utc() - timedelta(days=1),
            "end": now_utc() + timedelta(days=1),
            "total_count": 10,
            "used_count": 0,
            **overrides,
        }
    )
    db.session.add(row)
    db.session.commit()
    return row


@pytest.mark.parametrize(
    ("overrides", "error_key"),
    [
        (
            {"filter": '{"course_id":"another-course"}'},
            "server.common.unknownError",
        ),
        ({"start": now_utc() + timedelta(days=1)}, "server.discount.discountNotStart"),
        (
            {"end": now_utc() - timedelta(days=1)},
            "server.discount.discountAlreadyExpired",
        ),
        ({"used_count": 10}, "server.discount.discountLimitExceeded"),
        ({"deleted": 1}, "server.discount.discountNotFound"),
        (
            {"status": 0, "created_user_bid": "operator"},
            "server.discount.discountNotFound",
        ),
    ],
)
def test_prevalidation_rejects_unusable_coupon_without_closing_payment(
    app: object, coupon_scope: SimpleNamespace, overrides: dict, error_key: str
) -> None:
    coupon = _coupon(coupon_scope, **overrides)
    with pytest.raises(AppError) as caught:
        coupons.use_coupon_code(
            app, coupon_scope.user, coupon_scope.code, coupon_scope.order.order_bid
        )
    assert caught.value.code == ERROR_CODE[error_key]
    coupon_scope.cancel.assert_not_called()
    coupon_scope.notify.assert_not_called()
    db.session.expire_all()
    assert coupon_scope.order.status == ORDER_STATUS_TO_BE_PAID
    assert coupon_scope.order.paid_price == Decimal(100)
    assert coupon.used_count == overrides.get("used_count", 0)
    assert CouponUsage.query.filter_by(code=coupon_scope.code).count() == 0


@pytest.mark.parametrize(
    "failure", ["missing", "foreign-user", "completed", "already-used"]
)
def test_prevalidation_checks_order_ownership_status_and_existing_coupon(
    app: object, coupon_scope: SimpleNamespace, failure: str
) -> None:
    order = coupon_scope.order
    requested_bid, requested_user = order.order_bid, coupon_scope.user
    if failure == "missing":
        requested_bid = uuid.uuid4().hex
    elif failure == "foreign-user":
        requested_user = uuid.uuid4().hex
    elif failure == "completed":
        order.status = ORDER_STATUS_SUCCESS
    else:
        db.session.add(
            CouponUsage(
                code=coupon_scope.code,
                order_bid=order.order_bid,
                status=COUPON_STATUS_USED,
            )
        )
    db.session.commit()
    key = {
        "missing": "server.order.orderNotFound",
        "foreign-user": "server.order.orderNotFound",
        "completed": "server.order.orderStatusError",
        "already-used": "server.discount.orderDiscountAlreadyUsed",
    }[failure]
    with pytest.raises(AppError) as caught:
        coupons._validate_coupon_before_closing_payment(
            app, requested_user, coupon_scope.code, requested_bid
        )
    assert caught.value.code == ERROR_CODE[key]


@pytest.mark.parametrize(
    ("discount_type", "value", "expected_price"),
    [
        (COUPON_TYPE_FIXED, 25, "75"),
        (COUPON_TYPE_PERCENT, 25, "75"),
        (COUPON_TYPE_FIXED, 150, "0"),
    ],
)
def test_coupon_redemption_commits_usage_and_discount_without_negative_price(
    app: object,
    coupon_scope: SimpleNamespace,
    discount_type: int,
    value: int,
    expected_price: str,
) -> None:
    coupon = _coupon(
        coupon_scope,
        discount_type=discount_type,
        value=value,
        filter="{invalid legacy filter",
    )
    coupon_scope.order.status = ORDER_STATUS_INIT
    db.session.commit()
    result = coupons._use_coupon_code_locked(
        app, coupon_scope.user, coupon_scope.code, coupon_scope.order.order_bid
    )
    db.session.expire_all()
    usage = CouponUsage.query.filter_by(code=coupon_scope.code).one()
    assert coupon_scope.order.paid_price == Decimal(expected_price)
    assert result.value_to_pay == str(Decimal(expected_price).quantize(Decimal("0.01")))
    assert usage.user_bid == coupon_scope.user
    assert usage.shifu_bid == coupon_scope.order.shifu_bid
    assert usage.status == COUPON_STATUS_USED
    assert coupon.used_count == 1
    coupon_scope.cancel.assert_called_once()
    if expected_price == "0":
        assert coupon_scope.order.status == ORDER_STATUS_SUCCESS
    else:
        assert coupon_scope.order.status == ORDER_STATUS_INIT
        coupon_scope.notify.assert_called_once()


@pytest.mark.parametrize(
    ("overrides", "error_key"),
    [
        ({"start": now_utc() + timedelta(days=1)}, "server.discount.discountNotStart"),
        (
            {"end": now_utc() - timedelta(days=1)},
            "server.discount.discountAlreadyExpired",
        ),
        ({"used_count": 10}, "server.discount.discountLimitExceeded"),
    ],
)
def test_locked_redemption_revalidates_coupon_and_rolls_back_new_usage(
    app: object, coupon_scope: SimpleNamespace, overrides: dict, error_key: str
) -> None:
    coupon = _coupon(coupon_scope, **overrides)
    coupon_scope.order.status = ORDER_STATUS_INIT
    db.session.commit()
    with pytest.raises(AppError) as caught:
        coupons._use_coupon_code_locked(
            app,
            coupon_scope.user,
            coupon_scope.code,
            coupon_scope.order.order_bid,
            prevalidated=True,
        )
    assert caught.value.code == ERROR_CODE[error_key]
    assert CouponUsage.query.filter_by(code=coupon_scope.code).count() == 0
    assert coupon_scope.order.paid_price == Decimal(100)
    assert coupon.used_count == overrides.get("used_count", 0)
    coupon_scope.notify.assert_not_called()


def test_specific_coupon_without_active_usage_is_not_redeemable(
    coupon_scope: SimpleNamespace,
) -> None:
    coupon = _coupon(coupon_scope, usage_type=COUPON_APPLY_TYPE_SPECIFIC)
    assert coupons._pick_coupon_candidate(
        [], {}, [coupon], coupon_scope.order.shifu_bid, coupon_scope.user
    ) == (None, None, True)


@pytest.mark.parametrize(
    ("failure", "error_key"),
    [
        ("missing-order", "server.order.orderNotFound"),
        ("foreign-user", "server.order.orderNotFound"),
        ("paid-order", "server.order.orderStatusError"),
        ("used-coupon", "server.discount.orderDiscountAlreadyUsed"),
        ("missing-coupon", "server.discount.discountNotFound"),
        ("wrong-course", "server.common.unknownError"),
    ],
)
def test_locked_redemption_rechecks_changes_after_payment_cancellation(
    app: object, coupon_scope: SimpleNamespace, failure: str, error_key: str
) -> None:
    scope = coupon_scope
    order = scope.order
    order.status = ORDER_STATUS_INIT
    requested_bid, requested_user = order.order_bid, scope.user
    if failure == "missing-order":
        requested_bid = uuid.uuid4().hex
    elif failure == "foreign-user":
        requested_user = uuid.uuid4().hex
    elif failure == "paid-order":
        order.status = ORDER_STATUS_SUCCESS
    elif failure == "used-coupon":
        db.session.add(
            CouponUsage(
                code=scope.code, order_bid=order.order_bid, status=COUPON_STATUS_USED
            )
        )
    elif failure == "wrong-course":
        _coupon(scope, filter='{"course_id":"another-course"}')
    db.session.commit()
    original_status = order.status
    original_usages = CouponUsage.query.filter_by(code=scope.code).count()

    with pytest.raises(AppError) as caught:
        coupons._use_coupon_code_locked(
            app, requested_user, scope.code, requested_bid, prevalidated=True
        )

    assert caught.value.code == ERROR_CODE[error_key]
    db.session.expire_all()
    assert order.status == original_status
    assert order.paid_price == Decimal(100)
    assert CouponUsage.query.filter_by(code=scope.code).count() == original_usages
    scope.notify.assert_not_called()


@pytest.mark.parametrize("coupon_filter", ["[]", '{"course_id":""}'])
def test_legacy_empty_course_filter_redeems_as_unrestricted_coupon(
    app: object, coupon_scope: SimpleNamespace, coupon_filter: str
) -> None:
    scope = coupon_scope
    _coupon(scope, filter=coupon_filter, discount_type=COUPON_TYPE_FIXED)
    scope.order.status = ORDER_STATUS_INIT
    db.session.commit()
    result = coupons._use_coupon_code_locked(
        app, scope.user, scope.code, scope.order.order_bid
    )
    assert Decimal(result.value_to_pay) == Decimal(90)
    usage = CouponUsage.query.filter_by(code=scope.code).one()
    assert usage.shifu_bid == scope.order.shifu_bid
    assert usage.status == COUPON_STATUS_USED


def test_usage_already_assigned_to_user_is_preferred_without_double_counting(
    app: object, coupon_scope: SimpleNamespace
) -> None:
    coupon = _coupon(coupon_scope, used_count=1)
    owned = CouponUsage(
        coupon_usage_bid=uuid.uuid4().hex,
        coupon_bid=coupon.coupon_bid,
        code=coupon_scope.code,
        user_bid=coupon_scope.user,
        value=10,
        status=COUPON_STATUS_ACTIVE,
    )
    other = CouponUsage(
        coupon_usage_bid=uuid.uuid4().hex,
        coupon_bid=coupon.coupon_bid,
        code=coupon_scope.code,
        user_bid="other",
        value=10,
        status=COUPON_STATUS_ACTIVE,
    )
    db.session.add_all([owned, other])
    coupon_scope.order.status = ORDER_STATUS_INIT
    db.session.commit()
    coupons._use_coupon_code_locked(
        app, coupon_scope.user, coupon_scope.code, coupon_scope.order.order_bid
    )
    db.session.expire_all()
    assert owned.status == COUPON_STATUS_USED
    assert other.status == COUPON_STATUS_ACTIVE
    assert coupon.used_count == 1


@pytest.mark.parametrize("with_user", [False, True])
def test_coupon_notification_uses_committed_user_context_without_external_message(
    app: object,
    coupon_scope: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    with_user: bool,
) -> None:
    sender = Mock()
    monkeypatch.setattr(coupons, "send_notify", sender)
    monkeypatch.setattr(
        coupons,
        "load_user_aggregate",
        lambda _bid: (
            SimpleNamespace(mobile="13800000001", name="Learner") if with_user else None
        ),
    )
    db.session.add(
        UserConversion(
            user_id=coupon_scope.user,
            conversion_id=uuid.uuid4().hex,
            conversion_source="test-channel",
            conversion_status=1,
        )
    )
    db.session.commit()
    # The fixture stubs the post-commit hook, so call the original exported function.
    coupon_scope.notify_function(app, coupon_scope.user, "TEST", "Discount", "10")
    coupon_scope.notify.assert_not_called()
    if with_user:
        sender.assert_called_once()
        assert any("test-channel" in part for part in sender.call_args.args[2])
    else:
        sender.assert_not_called()

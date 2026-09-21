"""Ensure operator details use order-domain evidence and safe batch-import errors."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.i18n import _
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.order import admin
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import (
    AlipayOrder,
    Order,
    PingxxOrder,
    StripeOrder,
    WechatPayOrder,
)
from flaskr.service.promo.models import CouponUsage, PromoRedemption
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity


@pytest.fixture
def detail_scope(app: object) -> Iterator[SimpleNamespace]:
    bid, user, course = (uuid.uuid4().hex for _ in range(3))
    with app.app_context():
        order = Order(
            order_bid=bid,
            shifu_bid=course,
            user_bid=user,
            payable_price=100,
            paid_price=50,
            status=ORDER_STATUS_SUCCESS,
        )
        db.session.add(order)
        db.session.commit()
        yield SimpleNamespace(order=order, user=user, course=course)
        db.session.rollback()
        for model in (
            AlipayOrder,
            WechatPayOrder,
            StripeOrder,
            PingxxOrder,
            CouponUsage,
            PromoRedemption,
            Order,
        ):
            model.query.filter_by(order_bid=bid).delete()
        for model in (DraftShifu, PublishedShifu):
            model.query.filter_by(shifu_bid=course).delete()
        AuthCredential.query.filter_by(user_bid=user).delete()
        UserEntity.query.filter_by(user_bid=user).delete()
        db.session.commit()


def _snapshot(
    scope: SimpleNamespace, provider: str, domain: str, amount: int
) -> object:
    model = {
        "stripe": StripeOrder,
        "pingxx": PingxxOrder,
        "alipay": AlipayOrder,
        "wechatpay": WechatPayOrder,
    }[provider]
    row = model(
        order_bid=scope.order.order_bid,
        biz_domain=domain,
        amount=amount,
        status=999,
        currency="cny",
    )
    if provider == "pingxx":
        row.extra = "{}"
        row.charge_object = "{}"
    elif provider in {"alipay", "wechatpay"}:
        row.provider_attempt_id = uuid.uuid4().hex
        setattr(row, f"{provider}_order_bid", uuid.uuid4().hex)
    db.session.add(row)
    db.session.flush()
    return row


@pytest.mark.parametrize("provider", ["stripe", "pingxx", "alipay", "wechatpay"])
def test_payment_detail_uses_latest_order_snapshot_and_excludes_billing_snapshot(
    detail_scope: SimpleNamespace, provider: str
) -> None:
    detail_scope.order.payment_channel = provider
    _snapshot(detail_scope, provider, "order", 1000)
    _snapshot(detail_scope, provider, "order", 1234)
    _snapshot(detail_scope, provider, "billing", 99999)
    result = admin._load_payment_detail(detail_scope.order)
    assert result.payment_channel == provider
    assert result.amount == "12.34"
    assert result.status == 999
    assert result.status_key == "module.order.paymentStatus.unknown"
    assert result.currency == "cny"


@pytest.mark.parametrize(
    "provider", ["stripe", "pingxx", "alipay", "wechatpay", "manual"]
)
def test_payment_detail_has_no_evidence_when_only_billing_snapshot_exists(
    detail_scope: SimpleNamespace, provider: str
) -> None:
    detail_scope.order.payment_channel = provider
    if provider != "manual":
        _snapshot(detail_scope, provider, "billing", 99999)
    assert admin._load_payment_detail(detail_scope.order) is None


def test_order_detail_contains_only_live_promotions_and_coupon_usages(
    app: object, detail_scope: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = detail_scope
    monkeypatch.setattr(admin, "get_shifu_creator_bid", lambda *_args: "owner")
    scope.order.payment_channel = "manual"
    db.session.add(
        PromoRedemption(
            order_bid=scope.order.order_bid,
            promo_bid=uuid.uuid4().hex,
            promo_name="Promotion",
            discount_amount=5,
            status=999,
        )
    )
    db.session.add(
        PromoRedemption(
            order_bid=scope.order.order_bid, promo_name="Deleted", deleted=1
        )
    )
    db.session.add(
        CouponUsage(
            order_bid=scope.order.order_bid,
            coupon_bid=uuid.uuid4().hex,
            code="TEST",
            name="Coupon",
            value=10,
            status=999,
            discount_type=999,
        )
    )
    db.session.add(
        CouponUsage(order_bid=scope.order.order_bid, code="REMOVED", deleted=1)
    )
    db.session.commit()
    result = admin.get_order_detail(app, "owner", scope.order.order_bid)
    assert [item.active_name for item in result.activities] == ["Promotion"]
    assert result.activities[0].price == "5"
    assert [item.code for item in result.coupons] == ["TEST"]
    assert result.coupons[0].discount_type_key == "module.order.couponType.unknown"
    assert result.payment.status == 0
    assert result.payment.amount == "0"
    assert result.payment.payment_channel == "manual"
    operator = admin.get_operator_order_detail(app, scope.order.order_bid)
    assert operator.order.order_bid == scope.order.order_bid


@pytest.mark.parametrize("failure", ["foreign-owner", "missing", "deleted"])
def test_teacher_order_detail_requires_existing_order_and_current_course_ownership(
    app: object,
    detail_scope: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    monkeypatch.setattr(admin, "get_shifu_creator_bid", lambda *_args: "owner")
    if failure == "deleted":
        detail_scope.order.deleted = 1
        db.session.commit()
    bid = uuid.uuid4().hex if failure == "missing" else detail_scope.order.order_bid
    with pytest.raises(AppError) as caught:
        admin.get_order_detail(app, "another-owner", bid)
    key = (
        "server.shifu.noPermission"
        if failure == "foreign-owner"
        else "server.order.orderNotFound"
    )
    assert caught.value.code == ERROR_CODE[key]


def test_admin_lookup_keeps_latest_published_course_and_credential_contact_priority(
    detail_scope: SimpleNamespace,
) -> None:
    scope = detail_scope
    db.session.add(PublishedShifu(shifu_bid=scope.course, title="Old"))
    db.session.flush()
    latest = PublishedShifu(shifu_bid=scope.course, title="Latest")
    db.session.add(latest)
    db.session.add(DraftShifu(shifu_bid=scope.course, title="Unpublished changes"))
    db.session.add(
        UserEntity(user_bid=scope.user, user_identify="13800000000", nickname="Learner")
    )
    db.session.add(
        AuthCredential(
            user_bid=scope.user, provider_name="phone", identifier="13800000001"
        )
    )
    db.session.flush()
    db.session.add(
        AuthCredential(
            user_bid=scope.user, provider_name="phone", identifier="13800000002"
        )
    )
    db.session.add(
        AuthCredential(
            user_bid=scope.user,
            provider_name="email",
            identifier="learner@example.test",
        )
    )
    db.session.flush()
    assert admin._load_shifu_map([scope.course]) == {scope.course: latest}
    assert admin._load_user_map([scope.user])[scope.user] == {
        "mobile": "13800000002",
        "email": "learner@example.test",
        "nickname": "Learner",
        "identify": "13800000000",
    }
    assert admin._load_matching_user_bids_for_keyword("LEARNER@EXAMPLE.TEST") == [
        scope.user
    ]
    assert admin._load_matching_user_bids_for_keyword(" ") == []
    assert admin._load_matching_shifu_bids_for_course_name(" ") == []


@pytest.mark.parametrize(
    "filter_kind",
    [
        "order",
        "credential",
        "user-bid",
        "missing-user",
        "status",
        "course",
        "missing-course",
    ],
)
def test_operator_filters_query_real_order_course_and_contact_records(
    app: object, detail_scope: SimpleNamespace, filter_kind: str
) -> None:
    scope = detail_scope
    title = f"Published-{scope.course}"
    email = f"{scope.user}@example.test"
    db.session.add(PublishedShifu(shifu_bid=scope.course, title=title))
    db.session.add(
        AuthCredential(user_bid=scope.user, provider_name="email", identifier=email)
    )
    db.session.commit()
    filters = {"order_bid": scope.order.order_bid}
    filters.update(
        {
            "order": {},
            "credential": {"user_keyword": email.upper()},
            "user-bid": {"user_keyword": scope.user},
            "missing-user": {"user_keyword": uuid.uuid4().hex},
            "status": {"status": ORDER_STATUS_SUCCESS},
            "course": {"course_name": title},
            "missing-course": {"course_name": uuid.uuid4().hex},
        }[filter_kind]
    )
    result = admin.list_operator_orders(app, 1, 10, filters)
    expected = [] if filter_kind.startswith("missing") else [scope.order.order_bid]
    assert result.total == len(expected)
    assert [item.order_bid for item in result.data] == expected


def test_teacher_order_identifier_filter_keeps_course_ownership_scope(
    app: object, detail_scope: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = detail_scope
    owned_courses = Mock(return_value=[scope.course])
    monkeypatch.setattr(admin, "get_user_created_shifu_bids", owned_courses)
    result = admin.list_orders(
        app, "teacher", 1, 10, {"order_bid": scope.order.order_bid}
    )
    assert [item.order_bid for item in result.data] == [scope.order.order_bid]
    owned_courses.return_value = [uuid.uuid4().hex]
    hidden = admin.list_orders(
        app, "teacher", 1, 10, {"order_bid": scope.order.order_bid}
    )
    assert hidden.total == 0
    assert hidden.data == []


@pytest.mark.parametrize("from_entries", [False, True])
def test_batch_import_isolates_per_account_errors_and_logs_only_masked_identifier(
    app: object, monkeypatch: pytest.MonkeyPatch, from_entries: bool
) -> None:
    identifiers = ["first@example.test", "second@example.test", "third@example.test"]
    importer = Mock(
        side_effect=[
            {"order_bid": "created"},
            AppError("Rejected account", 123),
            RuntimeError("private failure"),
        ]
    )
    monkeypatch.setattr(admin, "import_activation_order", importer)
    warning, exception = Mock(), Mock()
    monkeypatch.setattr(app.logger, "warning", warning)
    monkeypatch.setattr(app.logger, "exception", exception)
    with app.app_context():
        if from_entries:
            result = admin.import_activation_orders_from_entries(
                app,
                [
                    {"mobile": ""},
                    *[{"mobile": item, "nickname": ""} for item in identifiers],
                ],
                "course",
                contact_type="email",
            )
        else:
            result = admin.import_activation_orders(
                app, identifiers, "course", contact_type="email"
            )
        assert result == {
            "success": [{"mobile": identifiers[0], "order_bid": "created"}],
            "failed": [
                {"mobile": identifiers[1], "message": "Rejected account"},
                {
                    "mobile": identifiers[2],
                    "message": _("server.order.importActivationFailed"),
                },
            ],
        }
    assert importer.call_count == 3
    assert warning.call_args.args[1].startswith("hash:")
    assert warning.call_args.args[2] == "123"
    assert exception.call_args.args[1].startswith("hash:")
    assert not any(
        item in str(warning.call_args) + str(exception.call_args)
        for item in identifiers
    )


@pytest.mark.parametrize(
    ("identifier", "contact_type"),
    [
        ("", "phone"),
        ("123", "phone"),
        ("", "email"),
        ("not-an-email", "email"),
        ("abc", "unsupported"),
    ],
)
def test_import_rejects_invalid_identity_before_creating_accounts(
    app: object, monkeypatch: pytest.MonkeyPatch, identifier: str, contact_type: str
) -> None:
    ensure = Mock()
    monkeypatch.setattr(admin, "ensure_user_for_identifier", ensure)
    with app.app_context(), pytest.raises(AppError) as caught:
        admin.import_activation_order(
            app, identifier, "course", contact_type=contact_type
        )
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]
    ensure.assert_not_called()


def test_order_filters_handle_empty_criteria_and_exact_supported_market_channel(
    detail_scope: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = Order.query.filter_by(order_bid=detail_scope.order.order_bid)
    assert admin._apply_order_source_filter(query, " ") is query
    assert admin._apply_payment_channel_filter(query, " ") is query
    monkeypatch.setattr(admin, "resolve_market_payment_provider", lambda: "pingxx")
    detail_scope.order.payment_channel = "pingxx"
    db.session.flush()
    assert admin._apply_payment_channel_filter(query, "pingxx").all() == [
        detail_scope.order
    ]
    assert admin._apply_payment_channel_filter(query, "stripe").all() == []
    assert admin._format_cents(None) == "0"
    assert admin._format_cents("invalid") == "0"
    assert admin._format_cents(1234) == "12.34"
    assert Decimal(admin._format_decimal(Decimal("1.25"))) == Decimal("1.25")

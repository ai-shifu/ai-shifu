from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from flask import Flask
import pytest

import flaskr.common.config as common_config
import flaskr.dao as dao
from flaskr.service.billing.models import BillingOrder
from flaskr.service.order.consts import ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.funs import (
    BuyRecordDTO,
    generate_charge,
    init_buy_record,
    query_buy_record,
)
from flaskr.service.order.models import Order, StripeOrder
from flaskr.service.order.payment_providers import PaymentCreationResult


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)  # noqa: SLF001


@pytest.fixture(autouse=True)
def clear_legacy_order_url_config_cache():
    _reset_config_cache("HOST_URL", "PATH_PREFIX")
    yield
    _reset_config_cache("HOST_URL", "PATH_PREFIX")


@pytest.fixture
def legacy_order_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REDIS_KEY_PREFIX="legacy-order-test",
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_legacy_order_purchase_flow_stays_on_order_tables(
    legacy_order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.order import funs as order_funs

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(
            price=Decimal("99.00"),
            title="Legacy course",
            description="Legacy checkout flow",
        ),
    )
    monkeypatch.setattr(
        order_funs, "apply_promo_campaigns", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        order_funs,
        "_generate_pingxx_charge",
        lambda **kwargs: _fake_pingxx_charge(**kwargs),
    )

    def _fake_pingxx_charge(**kwargs):
        buy_record = kwargs["buy_record"]
        buy_record.status = ORDER_STATUS_TO_BE_PAID
        dao.db.session.add(buy_record)
        dao.db.session.commit()
        return BuyRecordDTO(
            buy_record.order_bid,
            buy_record.user_bid,
            buy_record.paid_price,
            kwargs["channel"],
            "legacy-qr-url",
            payment_channel="pingxx",
        )

    init_result = init_buy_record(
        legacy_order_app,
        "legacy-user-1",
        "legacy-course-1",
    )
    charge_result = generate_charge(
        legacy_order_app,
        init_result.order_id,
        "wx_wap",
        "127.0.0.1",
    )
    query_result = query_buy_record(legacy_order_app, init_result.order_id)

    assert charge_result.payment_channel == "pingxx"
    assert charge_result.channel == "wx_wap"
    assert charge_result.qr_url == "legacy-qr-url"
    assert query_result.order_id == init_result.order_id
    assert query_result.user_id == "legacy-user-1"
    assert query_result.course_id == "legacy-course-1"

    with legacy_order_app.app_context():
        order = Order.query.filter(Order.order_bid == init_result.order_id).first()

        assert order is not None
        assert order.status == ORDER_STATUS_TO_BE_PAID
        assert order.payment_channel == "pingxx"
        assert BillingOrder.query.count() == 0


def test_legacy_stripe_checkout_urls_are_derived_from_host_url(
    legacy_order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.order import funs as order_funs

    monkeypatch.setenv("HOST_URL", "https://learn.example.com")
    monkeypatch.setenv("PATH_PREFIX", "/api")
    _reset_config_cache("HOST_URL", "PATH_PREFIX")

    stripe_requests: list[dict] = []

    class FakeStripeProvider:
        def create_payment(self, *, request, app):
            stripe_requests.append(
                {
                    "order_bid": request.order_bid,
                    "channel": request.channel,
                    "extra": request.extra,
                }
            )
            return PaymentCreationResult(
                provider_reference="cs_legacy_test",
                raw_response={
                    "id": "cs_legacy_test",
                    "url": "https://stripe.test/checkout",
                },
                checkout_session_id="cs_legacy_test",
                extra={
                    "url": "https://stripe.test/checkout",
                    "payment_intent_id": "pi_legacy_test",
                    "latest_charge_id": "ch_legacy_test",
                    "payment_intent_object": {"id": "pi_legacy_test"},
                },
            )

    monkeypatch.setattr(
        order_funs,
        "get_payment_provider",
        lambda provider_name: FakeStripeProvider(),
    )

    with legacy_order_app.app_context():
        order = Order(
            order_bid="order-stripe-url-1",
            user_bid="legacy-user-1",
            shifu_bid="legacy-course-1",
            payable_price=Decimal("99.00"),
            paid_price=Decimal("99.00"),
            status=ORDER_STATUS_TO_BE_PAID,
        )
        dao.db.session.add(order)
        dao.db.session.commit()

        result = order_funs._generate_stripe_charge(
            app=legacy_order_app,
            buy_record=order,
            course=SimpleNamespace(
                bid="legacy-course-1",
                title="Legacy course",
                description="Legacy checkout flow",
            ),
            channel="checkout_session",
            client_ip="127.0.0.1",
            amount=9900,
            subject="Legacy course",
            body="Legacy checkout flow",
            order_no="stripe-attempt-1",
        )

        raw_order = StripeOrder.query.filter_by(
            order_bid="order-stripe-url-1",
            biz_domain="order",
        ).one()

    assert result.payment_channel == "stripe"
    assert result.payment_payload["checkout_session_id"] == "cs_legacy_test"
    assert stripe_requests[0]["extra"]["success_url"] == (
        "https://learn.example.com/payment/stripe/result?order_id=order-stripe-url-1"
    )
    assert stripe_requests[0]["extra"]["cancel_url"] == (
        "https://learn.example.com/payment/stripe/result"
        "?canceled=1&order_id=order-stripe-url-1"
    )
    assert raw_order.checkout_session_id == "cs_legacy_test"

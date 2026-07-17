from __future__ import annotations

from decimal import Decimal
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from cryptography.fernet import Fernet
from flask import Flask
import pytest

import flaskr.common.config as common_config
import flaskr.dao as dao
from flaskr.service.billing.entitlements import grant_creator_manual_entitlement
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


class _FakeSaasConfigFuncs:
    @dataclass
    class SaasUserConfigCreateDTO:
        user_bid: str
        key: str
        value: str
        is_encrypted: int | bool = 0
        remark: str = ""
        updated_by: str = ""
        config_bid: str = ""

    def __init__(self) -> None:
        self._by_bid: dict[str, dict[str, Any]] = {}
        self._by_user_key: dict[tuple[str, str], str] = {}

    def create_versioned_saas_user_config(
        self,
        app,
        *,
        user_bid: str,
        key: str,
        value: str,
        is_encrypted: bool,
        remark: str,
        updated_by: str,
        config_bid: str,
    ) -> None:
        del app, is_encrypted, remark, updated_by
        self._by_bid[config_bid] = {
            "user_bid": user_bid,
            "key": key,
            "value": value,
        }

    def create_or_update_saas_user_config(self, app, dto) -> None:
        del app
        self._by_user_key[(dto.user_bid, dto.key)] = dto.value
        if dto.config_bid:
            self._by_bid[dto.config_bid] = {
                "user_bid": dto.user_bid,
                "key": dto.key,
                "value": dto.value,
            }

    def get_sass_config(self, user_bid: str, key: str, default: str = "") -> str:
        return self._by_user_key.get((user_bid, key), default)

    def get_saas_user_config_value_by_bid(self, app, config_bid: str):
        del app
        record = self._by_bid.get(config_bid)
        return None if record is None else record["value"]

    def update_saas_user_config_version(
        self,
        app,
        *,
        config_bid: str,
        value: str,
        is_encrypted: bool,
    ) -> None:
        del app, is_encrypted
        self._by_bid[config_bid]["value"] = value

    def soft_delete_saas_user_config(self, app, user_bid: str, key: str) -> None:
        del app
        self._by_user_key.pop((user_bid, key), None)


def test_creator_payment_config_smoke_supports_alipay_and_wechatpay_checkout(
    legacy_order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import customization
    from flaskr.service.config import get_config
    from flaskr.service.order import funs as order_funs

    fake_saas = _FakeSaasConfigFuncs()
    provider_requests: list[dict[str, Any]] = []

    class FakeNativeProvider:
        def __init__(self, provider_name: str) -> None:
            self.provider_name = provider_name

        def create_payment(self, *, request, app):
            del app
            if self.provider_name == "alipay":
                assert request.channel == "alipay_qr"
                provider_requests.append(
                    {
                        "provider": self.provider_name,
                        "channel": request.channel,
                        "app_id": get_config("ALIPAY_APP_ID"),
                        "private_key": get_config("ALIPAY_APP_PRIVATE_KEY"),
                    }
                )
                return PaymentCreationResult(
                    provider_reference="ali_native_attempt_1",
                    raw_response={"qr_code": "https://alipay.test/qr"},
                    extra={"credential": {"alipay_qr": "https://alipay.test/qr"}},
                )

            assert self.provider_name == "wechatpay"
            assert request.channel == "wx_pub_qr"
            provider_requests.append(
                {
                    "provider": self.provider_name,
                    "channel": request.channel,
                    "app_id": get_config("WECHATPAY_APP_ID"),
                    "mch_id": get_config("WECHATPAY_MCH_ID"),
                    "private_key": get_config("WECHATPAY_PRIVATE_KEY"),
                }
            )
            return PaymentCreationResult(
                provider_reference="wx_native_attempt_1",
                raw_response={"code_url": "weixin://wxpay/test"},
                extra={"credential": {"wx_pub_qr": "weixin://wxpay/test"}},
            )

    monkeypatch.setattr(customization, "_saas_funcs", lambda **_kwargs: fake_saas)
    monkeypatch.setattr(
        customization,
        "_config_owner_bid",
        lambda integration_bid: fake_saas._by_bid[integration_bid]["user_bid"],
    )
    monkeypatch.setattr(customization, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(
        customization, "_probe_provider_credentials", lambda *_args, **_kwargs: None
    )
    legacy_order_app.config["CREATOR_INTEGRATION_ENCRYPTION_KEY"] = (
        Fernet.generate_key().decode()
    )
    monkeypatch.setenv("HOST_URL", "https://learn.example.com")
    monkeypatch.setenv("PATH_PREFIX", "/api")
    _reset_config_cache("HOST_URL", "PATH_PREFIX")
    monkeypatch.setattr(
        order_funs,
        "get_payment_provider",
        lambda provider_name: FakeNativeProvider(provider_name),
    )
    monkeypatch.setattr(
        order_funs, "get_shifu_creator_bid", lambda _app, _bid: "teacher-pay-1"
    )
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, bid, _preview: SimpleNamespace(
            bid=bid,
            price=Decimal("99.00"),
            title="Paid course",
            description="Course checkout",
        ),
    )
    monkeypatch.setattr(
        order_funs, "apply_promo_campaigns", lambda *_args, **_kwargs: []
    )

    with legacy_order_app.app_context():
        grant_creator_manual_entitlement(
            legacy_order_app,
            "teacher-pay-1",
            custom_payment_enabled=True,
        )
        alipay = customization.save_creator_integration(
            legacy_order_app,
            "teacher-pay-1",
            "alipay",
            {
                "public_config": {"app_id": "ali-app-id"},
                "secret_config": {
                    "app_private_key": "ali-private-key",
                    "alipay_public_key": "ali-public-key",
                },
            },
        )
        assert (
            customization.verify_creator_integration(
                legacy_order_app,
                "teacher-pay-1",
                "alipay",
                alipay["integration_bid"],
            )["status"]
            == "verified"
        )
        wechatpay = customization.save_creator_integration(
            legacy_order_app,
            "teacher-pay-1",
            "wechatpay",
            {
                "public_config": {
                    "app_id": "wx-app-id",
                    "mch_id": "wx-mch-id",
                    "merchant_serial_no": "wx-serial-no",
                },
                "secret_config": {
                    "api_v3_key": "wx-api-v3-key",
                    "private_key": "wx-private-key",
                    "platform_cert": "wx-platform-cert",
                },
            },
        )
        assert (
            customization.verify_creator_integration(
                legacy_order_app,
                "teacher-pay-1",
                "wechatpay",
                wechatpay["integration_bid"],
            )["status"]
            == "verified"
        )

    alipay_order = init_buy_record(
        legacy_order_app,
        "learner-alipay-1",
        "course-alipay-1",
    )
    alipay_charge = generate_charge(
        legacy_order_app,
        alipay_order.order_id,
        "alipay_qr",
        "127.0.0.1",
        payment_channel="alipay",
    )
    wechat_order = init_buy_record(
        legacy_order_app,
        "learner-wechat-1",
        "course-wechat-1",
    )
    wechat_charge = generate_charge(
        legacy_order_app,
        wechat_order.order_id,
        "wx_pub_qr",
        "127.0.0.1",
        payment_channel="wechatpay",
    )

    assert alipay_charge.payment_channel == "alipay"
    assert alipay_charge.channel == "alipay_qr"
    assert alipay_charge.qr_url == "https://alipay.test/qr"
    assert alipay_charge.payment_payload["credential"]["alipay_qr"] == (
        "https://alipay.test/qr"
    )
    assert wechat_charge.payment_channel == "wechatpay"
    assert wechat_charge.channel == "wx_pub_qr"
    assert wechat_charge.qr_url == "weixin://wxpay/test"
    assert wechat_charge.payment_payload["credential"]["wx_pub_qr"] == (
        "weixin://wxpay/test"
    )
    assert provider_requests == [
        {
            "provider": "alipay",
            "channel": "alipay_qr",
            "app_id": "ali-app-id",
            "private_key": "ali-private-key",
        },
        {
            "provider": "wechatpay",
            "channel": "wx_pub_qr",
            "app_id": "wx-app-id",
            "mch_id": "wx-mch-id",
            "private_key": "wx-private-key",
        },
    ]

    with legacy_order_app.app_context():
        orders = Order.query.order_by(Order.id.asc()).all()
        assert [order.payment_channel for order in orders] == ["alipay", "wechatpay"]
        assert [order.payment_integration_bid for order in orders] == [
            alipay["integration_bid"],
            wechatpay["integration_bid"],
        ]


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

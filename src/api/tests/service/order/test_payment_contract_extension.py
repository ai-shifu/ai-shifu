"""Exercise added integrations through real selection, persistence and business APIs."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar

import pytest
from flask import Flask, Response, jsonify, request
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.route.callback import register_callback_handler
from flaskr.service.billing import customization, subscriptions
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppError
from flaskr.service.config import config_overrides
from flaskr.service.order import funs, payment_providers, raw_snapshots
from flaskr.service.order.consts import ORDER_STATUS_INIT, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import AlipayOrder, Order
from flaskr.service.order.payment_providers.base import (
    PaymentCancellationResult,
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentProvider,
    PaymentRequest,
    SubscriptionUpdateResult,
)
from flaskr.service.order.payment_providers.contracts import (
    PaymentAction,
    PaymentCapabilities,
    PaymentDefinition,
    PaymentFacts,
    PaymentRoute,
    SubscriptionFacts,
)
from flaskr.service.order.payment_providers.options import configured_payment_options
from flaskr.util.datetime import now_utc
from sqlalchemy import MetaData

from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing.billing_write_routes_test_helpers import (
    add_active_subscription,
    seed_creator_user,
)
from tests.service.billing.route_loader import (
    load_billing_routes_module,
    load_register_billing_routes,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask.testing import FlaskClient

_snapshot_table = AlipayOrder.__table__.to_metadata(
    MetaData(), name="test_payment_contract_snapshots"
)
for _index in _snapshot_table.indexes:
    _index.name = "test_contract_" + str(_index.name)


class FixtureSnapshot(dao.db.Model):
    """An isolated fixture schema; no fake integration writes to a real provider table."""

    __table__ = _snapshot_table


_hosted_table = AlipayOrder.__table__.to_metadata(
    MetaData(), name="test_hosted_contract_snapshots"
)
for _index in _hosted_table.indexes:
    _index.name = "test_hosted_" + str(_index.name)


class HostedFixtureSnapshot(dao.db.Model):
    """A separate storage identity for the hosted fixture variant."""

    __table__ = _hosted_table


class FixtureProvider(PaymentProvider):
    """A fifth adapter implementing existing one-time payment capabilities."""

    channel = "fixture-pay"
    definition = PaymentDefinition(
        capabilities=PaymentCapabilities(query=True, close=True, poll_provider=True),
        routes=(PaymentRoute("fixture_qr", "alipay", "qr", "qr"),),
        default_channel="fixture_qr",
        label_key="module.billing.catalog.labels.providerAlipay",
    )
    attempts: ClassVar[dict[str, dict]] = {}
    calls: ClassVar[list[tuple[str, str]]] = []

    def create_payment(
        self, *, request: PaymentRequest, app: object
    ) -> PaymentCreationResult:
        del app
        self.calls.append(("payment", request.order_bid))
        self.attempts[request.order_bid] = {
            "state": "pending",
            "amount": request.amount,
            "currency": request.currency.upper(),
            "reference": request.order_bid,
            "fixture_occurred_at": int(now_utc().replace(tzinfo=UTC).timestamp()),
        }
        action = PaymentAction(
            "redirect" if self.definition.capabilities.subscription_create else "qr",
            url="https://fixture.test/pay",
        )
        return PaymentCreationResult(
            request.order_bid,
            {"link": action.url},
            extra={"credential": {request.channel: action.url}},
            action=action,
        )

    @classmethod
    def read_payment_facts(cls, payload: dict) -> PaymentFacts:
        payload = payload.get("trade", payload)
        return PaymentFacts(
            state=payload.get("state", "unknown"),
            order_amount=payload.get("amount"),
            currency=payload.get("currency"),
            raw_status=payload.get("state", ""),
            provider_reference=payload.get("reference"),
            event_time=payload.get("fixture_occurred_at"),
        )

    def _notification(self, payload: dict) -> PaymentNotificationResult:
        contract = payload.get("contract")
        if contract:
            self.attempts[contract["provider_reference"]] = {
                **payload,
                "reference": contract["provider_reference"],
                "state": "unknown",
                "amount": None,
                "currency": None,
            }
        return PaymentNotificationResult(
            payload["reference"],
            "fixture.event",
            payload,
            charge_id="fixture-transaction",
            facts=self.read_payment_facts(payload),
            subscription=SubscriptionFacts(**contract) if contract else None,
        )

    def sync_reference(
        self, *, provider_reference: str, reference_type: str, app: object
    ) -> PaymentNotificationResult:
        del app
        assert reference_type in {"payment", "subscription"}
        self.calls.append(("query", provider_reference))
        return self._notification(self.attempts[provider_reference])

    def verify_webhook(
        self, *, headers: dict, raw_body: bytes, app: object
    ) -> PaymentNotificationResult:
        del app
        expected = hmac.new(b"fixture-key", raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(headers.get("X-Fixture-Signature", ""), expected):
            message = "Invalid fixture signature"
            raise ValueError(message)
        return self._notification(json.loads(raw_body))

    def cancel_payment(
        self, *, provider_reference: str, reference_type: str, app: object
    ) -> PaymentCancellationResult:
        del app, reference_type
        self.attempts[provider_reference]["state"] = "canceled"
        return PaymentCancellationResult(provider_reference, {}, "cancelled")


class HostedFixtureProvider(FixtureProvider):
    """The same extension path can preserve a provider-managed subscription."""

    channel = "fixture-hosted"
    definition = PaymentDefinition(
        capabilities=PaymentCapabilities(
            billing_mode="provider_managed",
            query=True,
            close=True,
            subscription_create=True,
            subscription_cancel=True,
            subscription_resume=True,
        ),
        routes=(PaymentRoute("fixture_checkout", "hosted", "redirect", "hosted"),),
        default_channel="fixture_checkout",
        label_key="module.billing.catalog.labels.providerStripe",
    )

    def create_subscription(
        self, *, request: PaymentRequest, app: object
    ) -> PaymentCreationResult:
        assert request.payment_mode == "subscription"
        assert request.biz_domain == "billing"
        result = self.create_payment(request=request, app=app)
        self.calls.append(("subscription", request.order_bid))
        return result

    def cancel_subscription(
        self, *, subscription_bid: str, provider_subscription_id: str, app: object
    ) -> SubscriptionUpdateResult:
        del subscription_bid, app
        self.calls.append(("cancel", provider_subscription_id))
        return SubscriptionUpdateResult(provider_subscription_id, {}, "active")

    def resume_subscription(
        self, *, subscription_bid: str, provider_subscription_id: str, app: object
    ) -> SubscriptionUpdateResult:
        del subscription_bid, app
        self.calls.append(("resume", provider_subscription_id))
        return SubscriptionUpdateResult(provider_subscription_id, {}, "active")


@pytest.fixture
def integration_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[Flask]:
    monkeypatch.setattr(
        payment_providers,
        "_PROVIDER_REGISTRY",
        dict(payment_providers._PROVIDER_REGISTRY),
    )
    monkeypatch.setattr(
        raw_snapshots,
        "_NATIVE_PAYMENT_MODELS",
        dict(raw_snapshots._NATIVE_PAYMENT_MODELS),
    )
    monkeypatch.setattr(
        raw_snapshots,
        "_NATIVE_PAYMENT_BID_ATTRS",
        dict(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS),
    )
    for provider in (FixtureProvider, HostedFixtureProvider):
        payment_providers.register_payment_provider(provider)
        raw_snapshots.register_native_snapshot_model(
            provider.channel,
            HostedFixtureSnapshot
            if provider is HostedFixtureProvider
            else FixtureSnapshot,
            "alipay_order_bid",
        )
    FixtureProvider.attempts.clear()
    FixtureProvider.calls.clear()
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)
    monkeypatch.setattr(
        load_billing_routes_module(), "is_billing_enabled", lambda: True
    )
    routes = load_register_billing_routes()
    routes(app=app)
    register_callback_handler(app, "/api/callback")

    @app.before_request
    def user_context() -> None:
        request.user = SimpleNamespace(
            user_id="creator-1", is_creator=True, language="en-US"
        )

    @app.errorhandler(AppError)
    def business_error(error: AppError) -> Response:
        return jsonify({"code": error.code, "message": error.message})

    with (
        app.app_context(),
        config_overrides(
            {
                "PAYMENT_CHANNELS_ENABLED": "fixture-pay,fixture-hosted",
                "BILLING_ENABLED": True,
                "CREATOR_CUSTOMIZATION_ENABLED": False,
            }
        ),
    ):
        dao.db.create_all()
        FixtureSnapshot.__table__.create(dao.db.engine)
        HostedFixtureSnapshot.__table__.create(dao.db.engine)
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        seed_creator_user(app)
        yield app
        dao.db.session.remove()
        HostedFixtureSnapshot.__table__.drop(dao.db.engine)
        FixtureSnapshot.__table__.drop(dao.db.engine)
        dao.db.drop_all()


def _notify(
    client: FlaskClient,
    provider: str,
    reference: str,
    *,
    state: str = "paid",
    contract: dict | None = None,
    amount: int | None = None,
    signed: bool = True,
    occurred_at: int | None = None,
) -> Response:
    payload = {**FixtureProvider.attempts[reference], "state": state}
    if amount is not None:
        payload["amount"] = amount
    if occurred_at is not None:
        payload["fixture_occurred_at"] = occurred_at
    if contract:
        payload["contract"] = contract
    body = json.dumps(payload).encode()
    signature = (
        hmac.new(b"fixture-key", body, hashlib.sha256).hexdigest()
        if signed
        else "wrong"
    )
    return client.post(
        f"/api/callback/payments/{provider}",
        data=body,
        headers={"X-Fixture-Signature": signature},
    )


def test_fifth_adapter_creates_reuses_and_completes_learner_order(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = integration_app
    monkeypatch.setattr(
        funs,
        "get_shifu_info",
        lambda *_args, **_kwargs: SimpleNamespace(
            bid="fixture-course", title="Fixture", description="Fixture"
        ),
    )
    monkeypatch.setattr(funs, "get_shifu_creator_bid", lambda *_args: "teacher-fixture")
    notifications = []
    monkeypatch.setattr(
        funs, "send_order_feishu", lambda *_args: notifications.append("paid")
    )
    order = Order(
        order_bid="fixture-course-order",
        user_bid="creator-1",
        shifu_bid="fixture-course",
        payable_price=Decimal(10),
        paid_price=Decimal(10),
        status=ORDER_STATUS_INIT,
    )
    dao.db.session.add(order)
    dao.db.session.commit()
    result = funs.generate_charge(
        app,
        order.order_bid,
        "fixture_qr",
        "127.0.0.1",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    assert result.__json__()["payment_action"]["type"] == "qr"
    assert result.payment_channel == "fixture-pay"
    snapshot = FixtureSnapshot.query.filter_by(order_bid=order.order_bid).one()
    reference = snapshot.provider_attempt_id
    reused = funs.generate_charge(
        app,
        order.order_bid,
        "fixture_qr",
        "127.0.0.1",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    assert reused.payment_action == result.payment_action
    assert sum(operation == "payment" for operation, _ in FixtureProvider.calls) == 1
    with app.test_client() as client:
        assert (
            _notify(client, "fixture-pay", reference, signed=False).status_code == 400
        )
        assert _notify(client, "fixture-pay", reference, amount=1).status_code == 400
        assert _notify(client, "fixture-pay", reference).status_code == 200
        assert _notify(client, "fixture-pay", reference).status_code == 200
    dao.db.session.expire_all()
    assert (
        Order.query.filter_by(order_bid=order.order_bid).one().status
        == ORDER_STATUS_SUCCESS
    )
    assert FixtureSnapshot.query.filter_by(order_bid=order.order_bid).one().status == 1
    assert notifications == ["paid"]


def test_fifth_adapter_topup_grants_credits_once_through_billing_routes(
    integration_app: Flask,
) -> None:
    app = integration_app
    add_active_subscription(app)
    with app.test_client() as client:
        response = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-pay:fixture_qr",
            },
        )
        assert response.get_json(force=True).get("code") == 0, response.get_json(
            force=True
        )
        result = response.get_json(force=True)["data"]
        assert result["provider"] == "fixture-pay"
        assert result["payment_action"]["type"] == "qr"
        reference = result["bill_order_bid"]
        reopened_response = client.post(
            f"/api/billing/orders/{reference}/checkout", json={}
        ).get_json(force=True)
        assert reopened_response.get("code") == 0, reopened_response
        reopened = reopened_response["data"]
        assert reopened["payment_action"] == result["payment_action"]
        assert (
            sum(operation == "payment" for operation, _ in FixtureProvider.calls) == 1
        )
        assert _notify(client, "fixture-pay", reference).status_code == 200
        grants = CreditLedgerEntry.query.filter_by(source_bid=reference).count()
        assert grants > 0
        assert _notify(client, "fixture-pay", reference).status_code == 200
        assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == grants
        assert (
            client.post(f"/api/billing/orders/{reference}/sync", json={}).get_json(
                force=True
            )["data"]["status"]
            == "paid"
        )
        assert (
            BillingOrder.query.filter_by(bill_order_bid=reference).one().status
            == BILLING_ORDER_STATUS_PAID
        )


def test_hosted_fixture_preserves_contract_management_when_new_payments_are_disabled(
    integration_app: Flask,
) -> None:
    app = integration_app
    with app.test_client() as client:
        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        )
        assert response.get_json(force=True).get("code") == 0, response.get_json(
            force=True
        )
        result = response.get_json(force=True)["data"]
        assert result["payment_action"]["type"] == "redirect"
        reference = result["bill_order_bid"]
        assert ("subscription", reference) in FixtureProvider.calls
        reopened = client.post(
            f"/api/billing/orders/{reference}/checkout", json={}
        ).get_json(force=True)
        assert reopened.get("code") == 0, reopened
        assert reopened["data"]["payment_action"] == result["payment_action"]
        repeated = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
        assert repeated.get("code") == 0, repeated
        assert repeated["data"]["bill_order_bid"] == reference
        assert (
            sum(operation == "subscription" for operation, _ in FixtureProvider.calls)
            == 1
        )

        event_time = int(now_utc().replace(tzinfo=UTC).timestamp())
        now = event_time + 5
        contract = {
            "provider_reference": "fixture-contract",
            "status": "active",
            "customer_reference": "fixture-customer",
            "period_start": now,
            "period_end": now + 30 * 86400,
        }
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                state="pending",
                contract=contract,
                occurred_at=event_time,
            ).status_code
            == 200
        )
        assert (
            BillingOrder.query.filter_by(bill_order_bid=reference).one().status
            != BILLING_ORDER_STATUS_PAID
        )
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                contract=contract,
                occurred_at=event_time,
            ).status_code
            == 200
        )
        order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=order.subscription_bid
        ).one()
        assert subscription.provider_subscription_id == "fixture-contract"
        assert subscription.provider_customer_id == "fixture-customer"
        bucket = CreditWalletBucket.query.filter_by(source_bid=reference).one()
        assert bucket.effective_from.replace(tzinfo=UTC).timestamp() == now
        assert (
            bucket.effective_to.replace(tzinfo=UTC).timestamp()
            == contract["period_end"]
        )
        assert order.paid_at < bucket.effective_from

        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                state="unknown",
                contract={**contract, "status": "canceled", "period_end": now - 1},
                occurred_at=event_time - 100,
            ).status_code
            == 200
        )
        dao.db.session.expire_all()
        assert (
            subscription.current_period_end_at.replace(tzinfo=UTC).timestamp()
            == now + 30 * 86400
        )
        assert subscription.provider_subscription_id == "fixture-contract"
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                state="unknown",
                contract={**contract, "provider_reference": ""},
                occurred_at=event_time,
            ).status_code
            == 200
        )
        assert subscription.provider_subscription_id == "fixture-contract"
        next_contract = {
            **contract,
            "period_start": contract["period_end"],
            "period_end": contract["period_end"] + 30 * 86400,
        }
        shortened_contract = {**contract, "period_end": now + 20 * 86400}
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                state="unknown",
                contract=shortened_contract,
                occurred_at=event_time + 1,
            ).status_code
            == 200
        )
        dao.db.session.expire_all()
        assert (
            subscription.current_period_end_at.replace(tzinfo=UTC).timestamp()
            == shortened_contract["period_end"]
        )
        for index, (provider_status, local_status) in enumerate(
            [
                ("past_due", BILLING_SUBSCRIPTION_STATUS_PAST_DUE),
                ("paused", BILLING_SUBSCRIPTION_STATUS_PAUSED),
                ("canceled", BILLING_SUBSCRIPTION_STATUS_CANCELED),
            ],
            start=2,
        ):
            assert (
                _notify(
                    client,
                    "fixture-hosted",
                    reference,
                    state="unknown",
                    contract={**shortened_contract, "status": provider_status},
                    occurred_at=event_time + index,
                ).status_code
                == 200
            )
            dao.db.session.expire_all()
            assert subscription.status == local_status
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                contract=contract,
                occurred_at=event_time,
            ).status_code
            == 200
        )
        dao.db.session.expire_all()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                occurred_at=event_time,
            ).status_code
            == 200
        )
        dao.db.session.expire_all()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        FixtureProvider.attempts[reference].update(
            {"state": "paid", "fixture_occurred_at": event_time}
        )
        synced = client.post(f"/api/billing/orders/{reference}/sync", json={})
        assert synced.get_json(force=True).get("code") == 0
        dao.db.session.expire_all()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                state="unknown",
                contract=next_contract,
                occurred_at=event_time + 10,
            ).status_code
            == 200
        )
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                state="unknown",
                contract=contract,
                occurred_at=event_time - 10,
            ).status_code
            == 200
        )
        dao.db.session.expire_all()
        assert (
            subscription.current_period_start_at.replace(tzinfo=UTC).timestamp()
            == next_contract["period_start"]
        )
        assert (
            subscription.current_period_end_at.replace(tzinfo=UTC).timestamp()
            == next_contract["period_end"]
        )

        with config_overrides({"PAYMENT_CHANNELS_ENABLED": "alipay"}):
            assert not any(
                option.provider == "fixture-hosted"
                for option in configured_payment_options(biz_domain="billing")
            )
            payload = {"subscription_bid": subscription.subscription_bid}
            assert client.post(
                "/api/billing/subscriptions/cancel", json=payload
            ).get_json(force=True)["data"]["cancel_at_period_end"]
            assert not client.post(
                "/api/billing/subscriptions/resume", json=payload
            ).get_json(force=True)["data"]["cancel_at_period_end"]
        assert ("cancel", "fixture-contract") in FixtureProvider.calls
        assert ("resume", "fixture-contract") in FixtureProvider.calls
        with unit_of_work():
            renewal = subscriptions.ensure_subscription_renewal_order(app, subscription)
            assert renewal.provider_reference_id == "fixture-contract"
            assert renewal.payment_provider == "fixture-hosted"
            renewal_bid = renewal.bill_order_bid
        synchronized = client.post(
            f"/api/billing/orders/{renewal_bid}/sync", json={}
        ).get_json(force=True)
        assert synchronized.get("code") == 0, synchronized
        assert synchronized["data"]["status"] == "pending"
        assert ("query", "fixture-contract") in FixtureProvider.calls
        assert (
            sum(operation == "subscription" for operation, _ in FixtureProvider.calls)
            == 1
        )


def test_added_merchant_config_supports_required_and_optional_credentials(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "_PROVIDER_CONFIG_KEYS",
        "_PROVIDER_FIELDS",
        "_OPTIONAL_PUBLIC_FIELDS",
        "_OPTIONAL_SECRET_FIELDS",
        "_INTEGRATION_PROBES",
    ):
        monkeypatch.setattr(customization, name, dict(getattr(customization, name)))
    monkeypatch.setattr(
        customization, "PAYMENT_PROVIDERS", set(customization.PAYMENT_PROVIDERS)
    )
    monkeypatch.setattr(
        customization,
        "INTEGRATION_PROVIDERS",
        customization._PROVIDER_CONFIG_KEYS.keys(),
    )
    probed = []
    customization.register_payment_integration_config(
        "fixture-pay",
        public_keys={"merchant_id": "FIXTURE_MERCHANT"},
        secret_keys={"api_key": "FIXTURE_KEY", "webhook_key": "FIXTURE_WEBHOOK_KEY"},
        required_public={"merchant_id"},
        required_secret={"api_key"},
        probe=lambda *_values: probed.append(True),
    )
    public = customization._normalize_config(
        "fixture-pay", {"merchant_id": "merchant"}, secret=False
    )
    secret = customization._normalize_config(
        "fixture-pay", {"api_key": "required", "webhook_key": "optional"}, secret=True
    )
    customization._validate_required_config("fixture-pay", public, secret)
    customization._probe_provider_credentials(
        integration_app, "fixture-pay", public, secret
    )
    assert probed == [True]
    assert customization.build_provider_config_overrides(
        SimpleNamespace(
            provider="fixture-pay",
            public_config=public,
            secret_config=secret,
        )
    ) == {
        "FIXTURE_MERCHANT": "merchant",
        "FIXTURE_KEY": "required",
        "FIXTURE_WEBHOOK_KEY": "optional",
    }
    with pytest.raises(AppError):
        customization._normalize_config(
            "fixture-pay", {"unexpected_secret": "secret"}, secret=False
        )
    with pytest.raises(ValueError, match="Missing required configuration"):
        customization._validate_required_config("fixture-pay", public, {})

"""Exercise added integrations through real selection, persistence and business APIs."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, Response, jsonify
from flask import request as flask_request
from flaskr import dao
from flaskr.common.request_context import thread_local
from flaskr.dao import uow
from flaskr.dao.uow import unit_of_work
from flaskr.route.callback import register_callback_handler
from flaskr.route.order import register_order_handler
from flaskr.service.billing import (
    checkout,
    customization,
    provider_recovery,
    provider_snapshots,
    subscriptions,
    webhooks,
)
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppError
from flaskr.service.config import config_overrides
from flaskr.service.order import (
    coupon_funcs,
    funs,
    learner_payments,
    payment_providers,
    raw_snapshots,
)
from flaskr.service.order.consts import ORDER_STATUS_INIT, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import AlipayOrder, Order
from flaskr.service.order.payment_providers.base import (
    PaymentCancellationResult,
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentProvider,
    PaymentRefundResult,
    PaymentRequest,
    SubscriptionUpdateResult,
)
from flaskr.service.order.payment_providers.contracts import (
    PaymentAction,
    PaymentCapabilities,
    PaymentDefinition,
    PaymentFacts,
    PaymentQueryTerms,
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
    from pathlib import Path

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
        return SubscriptionUpdateResult(
            provider_subscription_id, {}, "active", {"cancel_at_period_end": True}
        )

    def resume_subscription(
        self, *, subscription_bid: str, provider_subscription_id: str, app: object
    ) -> SubscriptionUpdateResult:
        del subscription_bid, app
        self.calls.append(("resume", provider_subscription_id))
        return SubscriptionUpdateResult(
            provider_subscription_id, {}, "active", {"cancel_at_period_end": False}
        )


@contextmanager
def _preserve_request_context() -> Iterator[None]:
    before = vars(thread_local).copy()
    try:
        yield
    finally:
        vars(thread_local).clear()
        vars(thread_local).update(before)


@pytest.fixture
def integration_app(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest, tmp_path: Path
) -> Iterator[Flask]:
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
        SQLALCHEMY_DATABASE_URI=(
            f"sqlite:///{tmp_path / 'payments.sqlite'}"
            if getattr(request, "param", "") == "file"
            else "sqlite:///:memory:"
        ),
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
        flask_request.user = SimpleNamespace(
            user_id="creator-1", is_creator=True, language="en-US"
        )

    @app.errorhandler(AppError)
    def business_error(error: AppError) -> Response:
        return jsonify({"code": error.code, "message": error.message})

    with (
        _preserve_request_context(),
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


def _learner_sync_case(app: Flask, monkeypatch: pytest.MonkeyPatch) -> tuple:
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
    with unit_of_work():
        dao.db.session.add(
            Order(
                order_bid="sync-binding-order",
                user_bid="creator-1",
                shifu_bid="fixture-course",
                payable_price=Decimal(10),
                paid_price=Decimal(10),
                status=ORDER_STATUS_INIT,
            )
        )
    funs.generate_charge(
        app,
        "sync-binding-order",
        "fixture_qr",
        "127.0.0.1",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    order = Order.query.filter_by(order_bid="sync-binding-order").one()
    snapshot = FixtureSnapshot.query.filter_by(order_bid=order.order_bid).one()
    FixtureProvider.attempts[snapshot.provider_attempt_id]["state"] = "paid"
    return order, snapshot, notifications


def _creation_case(monkeypatch: pytest.MonkeyPatch) -> list:
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
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(
                FixtureProvider.definition.capabilities, poll_provider=False
            ),
        ),
    )
    with unit_of_work():
        dao.db.session.add(
            Order(
                order_bid="creation-order",
                user_bid="creator-1",
                shifu_bid="fixture-course",
                payable_price=Decimal(10),
                paid_price=Decimal(10),
                status=ORDER_STATUS_INIT,
            )
        )
    return notifications


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("failure", ["none", "response", "finalization"])
@pytest.mark.parametrize("different_reference", [False, True])
def test_early_signed_callback_fulfills_a_durable_attempt_without_polling(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    different_reference: bool,
) -> None:
    app = integration_app
    notifications = _creation_case(monkeypatch)
    original = FixtureProvider.create_payment
    observed = {}
    worker_errors = []
    references = []

    def create(
        self: FixtureProvider, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        observed["provider_uow"] = uow.in_unit_of_work()
        result = original(self, request=request, app=app)
        reference = request.order_bid
        references.append(reference)
        FixtureProvider.attempts[reference]["state"] = "paid"
        if different_reference:
            # The callback carries the merchant lookup but omits the gateway
            # identity until the distinct creation response becomes available.
            FixtureProvider.attempts[reference]["trade"] = {
                **FixtureProvider.attempts[reference],
                "reference": None,
            }

        def callback() -> None:
            try:
                with app.app_context():
                    observed["durable_attempt"] = (
                        FixtureSnapshot.query.filter_by(
                            order_bid="creation-order", provider_attempt_id=reference
                        ).count()
                        == 1
                    )
                    with app.test_client() as client:
                        observed["ack"] = _notify(
                            client, "fixture-pay", reference
                        ).status_code
                    dao.db.session.expire_all()
                    observed["paid_before_return"] = (
                        Order.query.filter_by(order_bid="creation-order").one().status
                        == ORDER_STATUS_SUCCESS
                    )
            except Exception as error:
                worker_errors.append(error)

        worker = threading.Thread(target=callback, daemon=True)
        worker.start()
        worker.join(timeout=5)
        assert not worker.is_alive()
        if failure == "response":
            message = "Provider response was lost after payment"
            raise RuntimeError(message)
        return (
            replace(result, provider_reference=f"external-{reference}")
            if different_reference
            else result
        )

    monkeypatch.setattr(FixtureProvider, "create_payment", create)
    if failure == "finalization":

        def fail_finalize(*_args: object) -> None:
            message = "Injected response persistence failure"
            raise RuntimeError(message)

        monkeypatch.setattr(learner_payments, "persist_direct_creation", fail_finalize)
        with pytest.raises(RuntimeError, match="response persistence failure"):
            funs.generate_charge(
                app,
                "creation-order",
                "fixture_qr",
                "127.0.0.1",
                payment_channel="fixture-pay",
                expected_user="creator-1",
            )
    result = funs.generate_charge(
        app,
        "creation-order",
        "fixture_qr",
        "127.0.0.1",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    assert worker_errors == []
    assert observed == {
        "provider_uow": False,
        "durable_attempt": True,
        "ack": 200,
        "paid_before_return": True,
    }
    if failure != "finalization":
        assert result.__json__()["status"] == ORDER_STATUS_SUCCESS
    assert result.__json__()["payment_action"]["type"] == "none"
    assert result.poll_provider is False
    dao.db.session.expire_all()
    snapshot = FixtureSnapshot.query.filter_by(order_bid="creation-order").one()
    expected_reference = (
        f"external-{references[0]}"
        if different_reference and failure == "none"
        else references[0]
    )
    assert snapshot.provider_attempt_id == expected_reference
    with app.test_client() as client:
        assert _notify(client, "fixture-pay", references[0]).status_code == 200
    assert snapshot.provider_attempt_id == expected_reference
    assert (
        funs.get_payment_details(app, "creation-order", expected_user="creator-1")[
            "status"
        ]
        == 1
    )
    assert notifications == ["paid"]
    assert not any(
        operation == "query" for operation, _reference in FixtureProvider.calls
    )
    assert sum(operation == "payment" for operation, _ in FixtureProvider.calls) == 1


def test_failed_creation_retries_the_durable_request_with_the_same_merchant_id(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = integration_app
    _creation_case(monkeypatch)
    original = FixtureProvider.create_payment
    requests = []

    def create(
        self: FixtureProvider, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        assert not uow.in_unit_of_work()
        requests.append(request)
        result = original(self, request=request, app=app)
        if len(requests) == 1:
            message = "Lost provider response"
            raise RuntimeError(message)
        return result

    monkeypatch.setattr(FixtureProvider, "create_payment", create)
    with pytest.raises(RuntimeError, match="Lost provider response"):
        funs.generate_charge(
            app,
            "creation-order",
            "fixture_qr",
            "127.0.0.1",
            payment_channel="fixture-pay",
            expected_user="creator-1",
        )
    snapshot = FixtureSnapshot.query.one()
    identity = snapshot.id
    assert (
        json.loads(snapshot.metadata_json)["prepared_payment_request"]["order_bid"]
        == requests[0].order_bid
    )
    funs.generate_charge(
        app,
        "creation-order",
        "fixture_qr",
        "192.0.2.10",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    assert requests[0] == requests[1]
    assert FixtureSnapshot.query.one().id == identity
    assert "prepared_payment_request" not in json.loads(snapshot.metadata_json)


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("competing_operation", ["create", "coupon"])
def test_creation_serializes_duplicate_requests_and_coupon_repricing(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    competing_operation: str,
) -> None:
    app = integration_app
    _creation_case(monkeypatch)
    locks = {}
    provider_entered = threading.Event()
    release_provider = threading.Event()
    competitor_entered = threading.Event()
    competitor_started = threading.Event()
    errors = []
    original = FixtureProvider.create_payment

    class BlockingLock:
        def __init__(self, key: str) -> None:
            self.lock = locks.setdefault(key, threading.Lock())

        def acquire(self, **_kwargs: object) -> bool:
            return self.lock.acquire(timeout=5)

        def release(self) -> None:
            self.lock.release()

        def extend(self, *_args: object, **_kwargs: object) -> bool:
            return self.lock.locked()

    monkeypatch.setattr(
        funs.cache_provider, "lock", lambda key, **_kw: BlockingLock(key)
    )

    def create(
        self: FixtureProvider, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        provider_entered.set()
        assert release_provider.wait(timeout=5)
        return original(self, request=request, app=app)

    monkeypatch.setattr(FixtureProvider, "create_payment", create)
    monkeypatch.setattr(
        coupon_funcs,
        "_validate_coupon_before_closing_payment",
        lambda *_args: competitor_entered.set(),
    )
    monkeypatch.setattr(coupon_funcs, "_use_coupon_code_locked", lambda *_a, **_k: None)

    def run(*, competitor: bool) -> None:
        try:
            with (
                app.app_context(),
                config_overrides({"PAYMENT_CHANNELS_ENABLED": "fixture-pay"}),
            ):
                if competitor:
                    competitor_started.set()
                if competitor and competing_operation == "coupon":
                    coupon_funcs.use_coupon_code(
                        app, "creator-1", "FIXTURE", "creation-order"
                    )
                else:
                    funs.generate_charge(
                        app,
                        "creation-order",
                        "fixture_qr",
                        "127.0.0.1",
                        payment_channel="fixture-pay",
                        expected_user="creator-1",
                    )
                    if competitor:
                        competitor_entered.set()
        except Exception as error:
            errors.append(error)

    first = threading.Thread(target=run, kwargs={"competitor": False}, daemon=True)
    second = threading.Thread(target=run, kwargs={"competitor": True}, daemon=True)
    first.start()
    try:
        assert provider_entered.wait(timeout=5)
        second.start()
        assert competitor_started.wait(timeout=5)
        assert not competitor_entered.wait(timeout=0.1)
    finally:
        release_provider.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert competitor_entered.is_set()
    assert FixtureSnapshot.query.count() == 1
    assert sum(operation == "payment" for operation, _ in FixtureProvider.calls) == 1


def test_unknown_signed_payment_notification_is_not_acknowledged_as_success(
    integration_app: Flask,
) -> None:
    FixtureProvider.attempts["unknown-attempt"] = {
        "reference": "unknown-attempt",
        "state": "paid",
        "amount": 1000,
        "currency": "CNY",
    }
    with integration_app.test_client() as client:
        response = _notify(client, "fixture-pay", "unknown-attempt")
    assert response.status_code == 400
    assert response.get_json(force=True)["code"] == "FAIL"
    assert FixtureSnapshot.query.count() == 0


@pytest.mark.parametrize("state", ["pending", "paid", "refunded", "canceled", "failed"])
def test_nonqueryable_learner_redirect_returns_local_status_and_webhooks_still_settle(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    app = integration_app
    notifications = _creation_case(monkeypatch)
    register_order_handler(app, "/api/order")
    monkeypatch.setattr(
        HostedFixtureProvider,
        "definition",
        replace(
            HostedFixtureProvider.definition,
            capabilities=replace(
                HostedFixtureProvider.definition.capabilities,
                query=False,
                poll_provider=False,
            ),
        ),
    )
    query = Mock(side_effect=NotImplementedError("Query is unsupported"))
    monkeypatch.setattr(HostedFixtureProvider, "sync_reference", query)
    with config_overrides({"HOST_URL": "https://fixture.test"}):
        created = funs.generate_charge(
            app,
            "creation-order",
            "fixture_checkout",
            "127.0.0.1",
            payment_channel="fixture-hosted",
            expected_user="creator-1",
        )
    assert created.payment_action.type == "redirect"
    snapshot = HostedFixtureSnapshot.query.one()
    reference = snapshot.provider_attempt_id
    with app.test_client() as client:
        if state == "refunded":
            assert _notify(client, "fixture-hosted", reference).status_code == 200
        if state != "pending":
            assert (
                _notify(client, "fixture-hosted", reference, state=state).status_code
                == 200
            )
        expected = funs.get_payment_details(
            app, "creation-order", expected_user="creator-1"
        )
        before = (
            snapshot.raw_response,
            snapshot.raw_notification,
            snapshot.metadata_json,
            list(notifications),
        )
        for _ in range(2):
            result = client.post(
                "/api/order/payment/sync", json={"order_id": "creation-order"}
            ).get_json(force=True)
            assert result["code"] == 0, result
            assert result["data"] == expected
        assert (
            snapshot.raw_response,
            snapshot.raw_notification,
            snapshot.metadata_json,
            notifications,
        ) == before
    with pytest.raises(AppError):
        funs.sync_native_payment_order(
            app, "creation-order", expected_user="another-user"
        )
    query.assert_not_called()
    if state in {"paid", "refunded"}:
        assert notifications == ["paid"]


@pytest.mark.parametrize("state", ["pending", "paid", "refunded", "canceled", "failed"])
def test_nonqueryable_billing_redirect_returns_local_status_without_replaying_effects(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    app = integration_app
    add_active_subscription(app)
    monkeypatch.setattr(
        HostedFixtureProvider,
        "definition",
        replace(
            HostedFixtureProvider.definition,
            capabilities=replace(
                HostedFixtureProvider.definition.capabilities,
                query=False,
                poll_provider=False,
            ),
        ),
    )
    query = Mock(side_effect=NotImplementedError("Query is unsupported"))
    monkeypatch.setattr(HostedFixtureProvider, "sync_reference", query)
    with app.test_client() as client:
        created = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
        assert created["code"] == 0, created
        assert created["data"]["payment_action"]["type"] == "redirect"
        reference = created["data"]["bill_order_bid"]
        if state == "refunded":
            assert _notify(client, "fixture-hosted", reference).status_code == 200
        if state != "pending":
            assert (
                _notify(client, "fixture-hosted", reference, state=state).status_code
                == 200
            )
        order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
        before = (
            order.status,
            dict(order.metadata_json),
            CreditLedgerEntry.query.count(),
            CreditWalletBucket.query.count(),
        )
        for _ in range(2):
            result = client.post(
                f"/api/billing/orders/{reference}/sync", json={}
            ).get_json(force=True)
            assert result["code"] == 0, result
            assert result["data"]["status"] == state
        assert (
            order.status,
            order.metadata_json,
            CreditLedgerEntry.query.count(),
            CreditWalletBucket.query.count(),
        ) == before
        from flaskr.service.billing.checkout import sync_billing_order

        with pytest.raises(AppError):
            sync_billing_order(app, "another-user", reference, {})
    query.assert_not_called()


@pytest.mark.parametrize("reported_reference", [True, False])
@pytest.mark.parametrize("operation", ["close", "refund"])
def test_billing_callback_preserves_gateway_reference_across_recovery_and_operations(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    reported_reference: bool,
    operation: str,
) -> None:
    app = integration_app
    add_active_subscription(app)
    original = FixtureProvider.create_payment
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(FixtureProvider.definition.capabilities, refund=True),
        ),
    )

    def create(
        self: FixtureProvider, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        result = original(self, request=request, app=app)
        external = f"external-{request.order_bid}"
        payload = FixtureProvider.attempts[request.order_bid]
        payload["trade"] = {
            **payload,
            "reference": external if reported_reference else None,
        }
        FixtureProvider.attempts[external] = payload
        return replace(result, provider_reference=external)

    closed, refunded = [], []

    def close(
        self: FixtureProvider, *, provider_reference: str, **_kwargs: object
    ) -> PaymentCancellationResult:
        closed.append(provider_reference)
        self.attempts[provider_reference]["state"] = "canceled"
        self.attempts[provider_reference]["trade"]["state"] = "canceled"
        return PaymentCancellationResult(provider_reference, {}, "cancelled")

    def refund(
        self: FixtureProvider, *, request: object, app: object
    ) -> PaymentRefundResult:
        del self, app
        refunded.append(request.metadata["provider_reference"])
        return PaymentRefundResult("fixture-refund", {}, "succeeded")

    monkeypatch.setattr(FixtureProvider, "create_payment", create)
    monkeypatch.setattr(FixtureProvider, "cancel_payment", close)
    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    with app.test_client() as client:
        created = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-pay:fixture_qr",
            },
        ).get_json(force=True)
        assert created["code"] == 0, created
        merchant = created["data"]["bill_order_bid"]
        external = f"external-{merchant}"
        state = "pending" if operation == "close" else "paid"
        FixtureProvider.attempts[merchant]["trade"]["state"] = state
        for _ in range(2):
            assert (
                _notify(client, "fixture-pay", merchant, state=state).status_code == 200
            )
            order = BillingOrder.query.filter_by(bill_order_bid=merchant).one()
            snapshot = FixtureSnapshot.query.filter_by(bill_order_bid=merchant).one()
            assert order.provider_reference_id == external
            assert snapshot.provider_attempt_id == external
        grants = CreditLedgerEntry.query.filter_by(source_bid=merchant).count()
        if not reported_reference:
            # Optional callback references retain the bound identity, but a
            # subsequent query must independently identify its payment.
            with pytest.raises(RuntimeError, match="reference mismatch"):
                checkout.sync_billing_order(app, "creator-1", merchant, {})
            assert order.provider_reference_id == external
            assert snapshot.provider_attempt_id == external
            assert (
                CreditLedgerEntry.query.filter_by(source_bid=merchant).count() == grants
            )
        FixtureProvider.attempts[external]["trade"]["reference"] = external
        synced = client.post(f"/api/billing/orders/{merchant}/sync", json={}).get_json(
            force=True
        )
        assert synced["code"] == 0, synced
        assert synced["data"]["status"] == state
        assert ("query", external) in FixtureProvider.calls
        assert CreditLedgerEntry.query.filter_by(source_bid=merchant).count() == grants
        if operation == "close":
            checkout._close_manual_payment_before_replacement(
                app, "creator-1", merchant
            )
            assert closed == [external]
            assert order.status == BILLING_ORDER_STATUS_CANCELED
        else:
            assert (
                checkout.refund_billing_order(app, "creator-1", merchant, {}).status
                == "refunded"
            )
            assert refunded == [external]
        assert order.provider_reference_id == external
        assert snapshot.provider_attempt_id == external


@pytest.mark.parametrize("selection", ["option", "legacy"])
@pytest.mark.parametrize("plan", ["initial", "free", "upgrade"])
def test_provider_managed_plan_without_subscription_creation_is_unavailable_and_rejected(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    selection: str,
    plan: str,
) -> None:
    app = integration_app
    monkeypatch.setattr(
        HostedFixtureProvider,
        "definition",
        replace(
            HostedFixtureProvider.definition,
            capabilities=replace(
                HostedFixtureProvider.definition.capabilities, subscription_create=False
            ),
        ),
    )
    if plan == "upgrade":
        add_active_subscription(app)
        with unit_of_work():
            BillingSubscription.query.one().billing_provider = "fixture-hosted"
    if plan == "free":
        with unit_of_work():
            BillingProduct.query.filter_by(
                product_bid="bill-product-plan-monthly"
            ).one().price_amount = 0
    with (
        config_overrides({"PAYMENT_CHANNELS_ENABLED": "fixture-hosted"}),
        app.test_client() as client,
    ):
        catalog = client.get("/api/billing/catalog").get_json(force=True)
        assert catalog["code"] == 0, catalog
        for operation in catalog["data"]["checkout_operations"].values():
            assert "fixture-hosted:fixture_checkout" not in operation["option_ids"]
            assert not operation["available"]
        before = (
            BillingOrder.query.count(),
            BillingSubscription.query.count(),
            CreditLedgerEntry.query.count(),
            list(FixtureProvider.calls),
        )
        payload = {"product_bid": "bill-product-plan-monthly"}
        if plan == "upgrade":
            payload["product_bid"] = "bill-product-plan-monthly-pro"
            payload["action"] = "upgrade_immediate"
        payload.update(
            {"payment_option": "fixture-hosted:fixture_checkout"}
            if selection == "option"
            else {"payment_provider": "fixture-hosted", "channel": "fixture_checkout"}
        )
        rejected = client.post(
            "/api/billing/subscriptions/checkout", json=payload
        ).get_json(force=True)
        assert rejected["code"] != 0, rejected
        assert (
            BillingOrder.query.count(),
            BillingSubscription.query.count(),
            CreditLedgerEntry.query.count(),
            FixtureProvider.calls,
        ) == before
        if plan != "upgrade":
            add_active_subscription(app)
        topup = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
        assert topup["code"] == 0, topup
        assert any(operation == "payment" for operation, _ in FixtureProvider.calls)


def test_creation_rejects_an_outer_unit_of_work_before_any_provider_call(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    _creation_case(monkeypatch)
    with unit_of_work(), pytest.raises(RuntimeError, match="owns its own transaction"):
        funs.generate_charge(
            integration_app,
            "creation-order",
            "fixture_qr",
            "127.0.0.1",
            payment_channel="fixture-pay",
            expected_user="creator-1",
        )
    assert FixtureProvider.calls == []
    assert FixtureSnapshot.query.count() == 0


@pytest.mark.parametrize("field", ["reference", "order", "customer", "product"])
def test_learner_sync_uses_registered_identity_validator_before_fulfillment(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    order, snapshot, notifications = _learner_sync_case(integration_app, monkeypatch)
    reference = snapshot.provider_attempt_id
    expected = {
        "reference": reference,
        "order": order.order_bid,
        "customer": order.user_bid,
        "product": order.shifu_bid,
    }
    FixtureProvider.attempts[reference].update(expected)
    FixtureProvider.attempts[reference][field] = "another-payment-identity"
    seen = []
    original = FixtureProvider.describe_query.__func__

    def describe(
        cls: type, notification: PaymentNotificationResult, terms: PaymentQueryTerms
    ) -> object:
        assert (
            terms.reference,
            terms.reference_type,
            terms.order_reference,
            terms.customer_reference,
            terms.product_reference,
        ) == (reference, "payment", order.order_bid, "creator-1", "fixture-course")
        seen.append(terms)
        if any(
            notification.provider_payload[key] != value
            for key, value in expected.items()
        ):
            message = "Fixture query identity mismatch"
            raise RuntimeError(message)
        return original(cls, notification, terms)

    monkeypatch.setattr(FixtureProvider, "describe_query", classmethod(describe))
    with pytest.raises(RuntimeError, match="identity mismatch"):
        funs.sync_native_payment_order(
            integration_app, order.order_bid, expected_user="creator-1"
        )
    dao.db.session.expire_all()
    assert seen
    assert order.status != ORDER_STATUS_SUCCESS
    assert snapshot.status == 0
    assert notifications == []
    FixtureProvider.attempts[reference][field] = expected[field]
    for _ in range(2):
        funs.sync_native_payment_order(
            integration_app, order.order_bid, expected_user="creator-1"
        )
    assert order.status == ORDER_STATUS_SUCCESS
    assert notifications == ["paid"]


def test_default_query_validator_rejects_another_payment_reference(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    order, snapshot, notifications = _learner_sync_case(integration_app, monkeypatch)
    FixtureProvider.attempts[snapshot.provider_attempt_id]["reference"] = (
        "another-paid-order"
    )
    with pytest.raises(RuntimeError, match="reference mismatch"):
        funs.sync_native_payment_order(
            integration_app, order.order_bid, expected_user="creator-1"
        )
    dao.db.session.expire_all()
    assert order.status != ORDER_STATUS_SUCCESS
    assert snapshot.status == 0
    assert notifications == []


@pytest.mark.parametrize("reference", ["original-contract", "another-contract"])
def test_default_query_validator_keeps_payment_and_contract_identity_separate(
    reference: str,
) -> None:
    result = PaymentNotificationResult(
        "legacy-order-alias",
        "paid",
        {},
        facts=PaymentFacts(state="paid", provider_reference="invoice-reference"),
        subscription=SubscriptionFacts(provider_reference=reference, status="active"),
    )
    terms = PaymentQueryTerms(
        "original-contract", "subscription", "order", "customer", "product"
    )
    if reference == "another-contract":
        with pytest.raises(RuntimeError, match="reference mismatch"):
            FixtureProvider.describe_query(result, terms)
    else:
        event = FixtureProvider.describe_query(result, terms)
        assert event.contract.provider_reference == reference
        assert event.payment.provider_reference == "invoice-reference"


def test_learner_sync_persists_validated_query_facts_and_original_attempt_identity(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    order, snapshot, notifications = _learner_sync_case(integration_app, monkeypatch)
    reference = snapshot.provider_attempt_id
    FixtureProvider.attempts[reference]["state"] = "pending"
    original_query = FixtureProvider.sync_reference
    original_describe = FixtureProvider.describe_query.__func__

    def query(self: FixtureProvider, **kwargs: object) -> PaymentNotificationResult:
        return replace(original_query(self, **kwargs), order_bid="legacy-query-alias")

    def describe(
        cls: type, notification: PaymentNotificationResult, terms: PaymentQueryTerms
    ) -> object:
        event = original_describe(cls, notification, terms)
        return replace(
            event, payment=replace(event.payment, state="paid", raw_status="accepted")
        )

    monkeypatch.setattr(FixtureProvider, "sync_reference", query)
    monkeypatch.setattr(FixtureProvider, "describe_query", classmethod(describe))
    for _ in range(2):
        funs.sync_native_payment_order(
            integration_app, order.order_bid, expected_user="creator-1"
        )
    dao.db.session.expire_all()
    assert order.status == ORDER_STATUS_SUCCESS
    assert notifications == ["paid"]
    assert snapshot.status == 1
    assert snapshot.raw_status == "accepted"
    assert snapshot.provider_attempt_id == reference
    assert json.loads(snapshot.raw_response)["state"] == "pending"


@pytest.mark.parametrize(
    ("state", "expected_status"),
    [("paid", 1), ("refunded", 2), ("canceled", 3), ("failed", 4)],
)
def test_signed_learner_callbacks_persist_supplied_facts_without_reparsing(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    expected_status: int,
) -> None:
    app = integration_app
    order, snapshot, notifications = _learner_sync_case(app, monkeypatch)
    reference = snapshot.provider_attempt_id
    parser_calls = []

    def read(_cls: type, payload: dict) -> PaymentFacts:
        parser_calls.append(payload)
        return PaymentProvider.read_payment_facts(payload)

    def notification(
        _self: FixtureProvider, payload: dict
    ) -> PaymentNotificationResult:
        return PaymentNotificationResult(
            payload["reference"],
            "fixture.verified",
            {"opaque_receipt": "original-provider-payload"},
            charge_id="verified-transaction",
            facts=PaymentFacts(
                state=payload["state"],
                order_amount=payload["amount"],
                currency=payload["currency"],
                provider_reference=payload["reference"],
                raw_status="provider-verified",
            ),
        )

    monkeypatch.setattr(FixtureProvider, "read_payment_facts", classmethod(read))
    monkeypatch.setattr(FixtureProvider, "_notification", notification)
    with app.test_client() as client:
        assert (
            _notify(
                client, "fixture-pay", reference, state=state, signed=False
            ).status_code
            == 400
        )
        assert snapshot.status == 0
        for _ in range(2):
            assert (
                _notify(client, "fixture-pay", reference, state=state).status_code
                == 200
            )
    dao.db.session.expire_all()
    assert snapshot.status == expected_status
    assert snapshot.raw_status == "provider-verified"
    assert snapshot.provider_attempt_id == reference
    assert snapshot.transaction_id == "verified-transaction"
    assert json.loads(snapshot.raw_notification) == {
        "opaque_receipt": "original-provider-payload"
    }
    assert (
        funs.get_payment_details(app, order.order_bid, expected_user="creator-1")[
            "status"
        ]
        == expected_status
    )
    assert (order.status == ORDER_STATUS_SUCCESS) == (state == "paid")
    assert notifications == (["paid"] if state == "paid" else [])
    assert parser_calls == []


@pytest.mark.parametrize("timing", ["before", "during"])
def test_learner_sync_rejects_a_superseded_provider_override(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, timing: str
) -> None:
    order, snapshot, notifications = _learner_sync_case(integration_app, monkeypatch)
    calls = []
    original = FixtureProvider.sync_reference

    def switch() -> None:
        with unit_of_work():
            current = Order.query.filter_by(order_bid=order.order_bid).one()
            current.payment_channel = "fixture-hosted"
            snapshot.status = 3

    def query(self: FixtureProvider, **kwargs: object) -> PaymentNotificationResult:
        calls.append("query")
        result = original(self, **kwargs)
        switch()
        return result

    if timing == "before":
        switch()
        monkeypatch.setattr(
            FixtureProvider,
            "sync_reference",
            lambda *_args, **kwargs: (
                calls.append("query") or original(FixtureProvider(), **kwargs)
            ),
        )
    else:
        monkeypatch.setattr(FixtureProvider, "sync_reference", query)
    with pytest.raises(AppError):
        funs.sync_native_payment_order(
            integration_app,
            order.order_bid,
            expected_user="creator-1",
            payment_channel="fixture-pay",
        )
    dao.db.session.expire_all()
    assert order.status != ORDER_STATUS_SUCCESS
    assert snapshot.status == 3
    assert notifications == []
    assert calls == ([] if timing == "before" else ["query"])


@pytest.mark.parametrize(
    "change", ["closed", "refunded", "failed", "repriced", "reused_reference"]
)
def test_learner_sync_does_not_fulfill_an_ineligible_or_replaced_attempt(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    order, snapshot, notifications = _learner_sync_case(integration_app, monkeypatch)
    original = FixtureProvider.sync_reference

    def invalidate() -> None:
        with unit_of_work():
            if change == "repriced":
                order.paid_price = Decimal(20)
            elif change == "reused_reference":
                dao.db.session.add(
                    FixtureSnapshot(
                        alipay_order_bid="replacement-snapshot",
                        biz_domain="order",
                        order_bid=order.order_bid,
                        user_bid=order.user_bid,
                        shifu_bid=order.shifu_bid,
                        provider_attempt_id=snapshot.provider_attempt_id,
                        amount=1000,
                        currency="CNY",
                        status=0,
                    )
                )
            else:
                snapshot.status = {"closed": 3, "refunded": 2, "failed": 4}[change]

    if change == "reused_reference":

        def query(self: FixtureProvider, **kwargs: object) -> PaymentNotificationResult:
            result = original(self, **kwargs)
            invalidate()
            return result

        monkeypatch.setattr(FixtureProvider, "sync_reference", query)
    else:
        invalidate()
    if change == "reused_reference":
        with pytest.raises(AppError):
            funs.sync_native_payment_order(
                integration_app, order.order_bid, expected_user="creator-1"
            )
    else:
        funs.sync_native_payment_order(
            integration_app, order.order_bid, expected_user="creator-1"
        )
    dao.db.session.expire_all()
    assert order.status != ORDER_STATUS_SUCCESS
    assert notifications == []
    if change in {"closed", "refunded", "failed"}:
        assert snapshot.status == {"closed": 3, "refunded": 2, "failed": 4}[change]


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


@pytest.mark.parametrize("source", ["notification", "query"])
@pytest.mark.parametrize("kind", ["preorder", "renewal"])
@pytest.mark.parametrize("cancel_scheduled", [False, True])
def test_manual_payment_preserves_the_current_cycle_until_future_activation(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    kind: str,
    cancel_scheduled: bool,
) -> None:
    app = integration_app
    add_active_subscription(app)
    with unit_of_work():
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-1"
        ).one()
        subscription.billing_provider = (
            "pingxx" if kind == "preorder" else "fixture-pay"
        )
        subscription.provider_subscription_id = ""
        subscription.provider_customer_id = ""
        subscription.last_renewed_at = subscription.current_period_start_at
        subscription.metadata_json = {"active_cycle_order_bid": "original-cycle"}
    with app.test_client() as client:
        if kind == "preorder":
            result = client.post(
                "/api/billing/subscriptions/checkout",
                json={
                    "product_bid": "bill-product-plan-monthly",
                    "payment_option": "fixture-pay:fixture_qr",
                    "action": "preorder",
                },
            ).get_json(force=True)
            assert result["code"] == 0, result
            reference = result["data"]["bill_order_bid"]
        else:
            with unit_of_work():
                order = subscriptions.ensure_subscription_renewal_order(
                    app, subscription
                )
                reference = order.bill_order_bid
            result = client.post(
                f"/api/billing/orders/{reference}/checkout", json={}
            ).get_json(force=True)
            assert result["code"] == 0, result
        with unit_of_work():
            subscription.cancel_at_period_end = int(cancel_scheduled)
            subscription.status = (
                BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
                if cancel_scheduled
                else BILLING_SUBSCRIPTION_STATUS_ACTIVE
            )
        before = (
            subscription.billing_provider,
            subscription.status,
            subscription.cancel_at_period_end,
            subscription.current_period_start_at,
            subscription.current_period_end_at,
            subscription.last_renewed_at,
            subscription.metadata_json["active_cycle_order_bid"],
        )
        boundary = subscription.current_period_end_at
        order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
        assert (
            order.metadata_json["provider_reference_type"]
            == FixtureProvider.definition.reference_type
        )
        FixtureProvider.attempts[reference]["state"] = "paid"
        if source == "notification":
            assert _notify(client, "fixture-pay", reference).status_code == 200
        else:
            synced = client.post(
                f"/api/billing/orders/{reference}/sync", json={}
            ).get_json(force=True)
            assert synced["code"] == 0, synced
        dao.db.session.expire_all()
        order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert (
            subscription.billing_provider,
            subscription.status,
            subscription.cancel_at_period_end,
            subscription.current_period_start_at,
            subscription.current_period_end_at,
            subscription.last_renewed_at,
            subscription.metadata_json.get("active_cycle_order_bid"),
        ) == before
        assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == 1
        bucket = CreditWalletBucket.query.filter_by(source_bid=reference).one()
        assert bucket.effective_from == boundary
        assert _notify(client, "fixture-pay", reference).status_code == 200
        # The paid-order lifecycle remains responsible for actual cycle activation.
        monkeypatch.setattr(
            subscriptions, "now_utc", lambda: boundary + timedelta(seconds=1)
        )
        with unit_of_work():
            assert subscriptions.activate_subscription_for_paid_order(app, order)
        assert subscription.current_period_start_at == boundary
        assert subscription.billing_provider == "fixture-pay"
        assert subscription.last_renewed_at == boundary
        assert bool(subscription.cancel_at_period_end) == cancel_scheduled
        assert subscription.metadata_json["active_cycle_order_bid"] == reference
        assert _notify(client, "fixture-pay", reference).status_code == 200
        assert subscription.metadata_json["active_cycle_order_bid"] == reference
        assert subscription.current_period_start_at == boundary
        assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == 1


@pytest.mark.parametrize("source", ["notification", "query"])
def test_manual_initial_payment_retains_its_active_cycle_order_marker(
    integration_app: Flask, source: str
) -> None:
    with integration_app.test_client() as client:
        result = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-pay:fixture_qr",
            },
        ).get_json(force=True)
        assert result["code"] == 0, result
        reference = result["data"]["bill_order_bid"]
        FixtureProvider.attempts[reference]["state"] = "paid"
        if source == "notification":
            assert _notify(client, "fixture-pay", reference).status_code == 200
        else:
            assert (
                client.post(f"/api/billing/orders/{reference}/sync", json={}).get_json(
                    force=True
                )["code"]
                == 0
            )
        order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=order.subscription_bid
        ).one()
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert subscription.metadata_json.get("active_cycle_order_bid") == reference
        assert subscription.last_renewed_at == order.paid_at
        assert _notify(client, "fixture-pay", reference).status_code == 200
        assert subscription.metadata_json.get("active_cycle_order_bid") == reference
        assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == 1


@pytest.mark.parametrize("source", ["notification", "query"])
@pytest.mark.parametrize("currency", ["USD", " usd ", " cNy ", None])
@pytest.mark.parametrize("provider", ["fixture-pay", "fixture-hosted"])
def test_reported_currency_guards_billing_settlement_and_credit_grants(
    integration_app: Flask, source: str, currency: str | None, provider: str
) -> None:
    app = integration_app
    hosted = provider == "fixture-hosted"
    if not hosted:
        add_active_subscription(app)
    with app.test_client() as client:
        result = client.post(
            "/api/billing/subscriptions/checkout"
            if hosted
            else "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-plan-monthly"
                if hosted
                else "bill-product-topup-small",
                "payment_option": f"{provider}:fixture_checkout"
                if hosted
                else f"{provider}:fixture_qr",
            },
        ).get_json(force=True)["data"]
        reference = result["bill_order_bid"]
        order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
        subscription = (
            BillingSubscription.query.filter_by(
                subscription_bid=order.subscription_bid
            ).first()
            if hosted
            else None
        )
        before = (
            (
                subscription.status,
                subscription.current_period_start_at,
                subscription.current_period_end_at,
            )
            if subscription
            else None
        )
        FixtureProvider.attempts[reference].update(state="paid", currency=currency)
        mismatch = bool(currency and currency.strip().upper() != "CNY")
        if source == "notification":
            response = _notify(client, provider, reference)
            assert response.status_code == (400 if mismatch else 200)
        elif mismatch:
            with pytest.raises(RuntimeError, match="currency mismatch"):
                client.post(f"/api/billing/orders/{reference}/sync", json={})
        else:
            response = client.post(f"/api/billing/orders/{reference}/sync", json={})
            assert response.get_json(force=True)["code"] == 0
        dao.db.session.expire_all()
        if mismatch:
            assert order.status != BILLING_ORDER_STATUS_PAID
            assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == 0
            assert CreditWalletBucket.query.filter_by(source_bid=reference).count() == 0
            if subscription:
                assert (
                    subscription.status,
                    subscription.current_period_start_at,
                    subscription.current_period_end_at,
                ) == before
        # A corrected event must still settle exactly once after rejection.
        FixtureProvider.attempts[reference]["currency"] = " cny "
        if source == "query":
            recovered = client.post(
                f"/api/billing/orders/{reference}/sync", json={}
            ).get_json(force=True)
            assert recovered["code"] == 0, recovered
            assert recovered["data"]["status"] == "paid"
        assert _notify(client, provider, reference).status_code == 200
        grants = CreditLedgerEntry.query.filter_by(source_bid=reference).count()
        assert grants > 0
        assert _notify(client, provider, reference).status_code == 200
        assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == grants
        assert order.status == BILLING_ORDER_STATUS_PAID


@pytest.mark.parametrize("source", ["notification", "query"])
@pytest.mark.parametrize("currency", ["USD", " usd ", " cNy ", None])
def test_reported_currency_guards_learner_fulfillment_and_allows_recovery(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    currency: str | None,
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
        order_bid="currency-learner",
        user_bid="creator-1",
        shifu_bid="fixture-course",
        payable_price=Decimal(10),
        paid_price=Decimal(10),
        status=ORDER_STATUS_INIT,
    )
    dao.db.session.add(order)
    dao.db.session.commit()
    funs.generate_charge(
        app,
        order.order_bid,
        "fixture_qr",
        "127.0.0.1",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    snapshot = FixtureSnapshot.query.filter_by(order_bid=order.order_bid).one()
    reference = snapshot.provider_attempt_id
    FixtureProvider.attempts[reference].update(state="paid", currency=currency)
    mismatch = bool(currency and currency.strip().upper() != "CNY")
    with app.test_client() as client:
        if source == "notification":
            assert _notify(client, "fixture-pay", reference).status_code == (
                400 if mismatch else 200
            )
        else:
            funs.sync_native_payment_order(
                app, order.order_bid, expected_user="creator-1"
            )
        dao.db.session.expire_all()
        if mismatch:
            assert order.status != ORDER_STATUS_SUCCESS
            assert snapshot.status == 0
            assert notifications == []
        FixtureProvider.attempts[reference]["currency"] = " cny "
        if source == "query":
            funs.sync_native_payment_order(
                app, order.order_bid, expected_user="creator-1"
            )
            assert order.status == ORDER_STATUS_SUCCESS
        assert _notify(client, "fixture-pay", reference).status_code == 200
        assert _notify(client, "fixture-pay", reference).status_code == 200
    assert order.status == ORDER_STATUS_SUCCESS
    assert notifications == ["paid"]


@pytest.mark.parametrize("native_storage", [False, True])
def test_hosted_fixture_preserves_contract_management_when_new_payments_are_disabled(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    native_storage: bool,
) -> None:
    app = integration_app
    if not native_storage:
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, "fixture-hosted")
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, "fixture-hosted")
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


def test_contract_only_hosted_query_reuses_checkout_without_closing_a_contract(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = integration_app
    with app.test_client() as client:
        result = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)["data"]
        reference = result["bill_order_bid"]
        FixtureProvider.attempts[reference].update(
            state="unknown",
            contract={"provider_reference": "pending-contract", "status": "pending"},
        )
        closed: list[str] = []

        def refuse_contract_closure(self: object, **kwargs: object) -> None:
            del self
            closed.append(str(kwargs["reference_type"]))
            pytest.fail("Reopening a hosted checkout must not close its contract")

        monkeypatch.setattr(
            HostedFixtureProvider, "cancel_payment", refuse_contract_closure
        )
        for endpoint, payload in (
            (f"/api/billing/orders/{reference}/checkout", {}),
            (
                "/api/billing/subscriptions/checkout",
                {
                    "product_bid": "bill-product-plan-monthly",
                    "payment_option": "fixture-hosted:fixture_checkout",
                },
            ),
        ):
            reopened = client.post(endpoint, json=payload).get_json(force=True)
            assert reopened.get("code") == 0, reopened
            assert reopened["data"]["bill_order_bid"] == reference
            assert reopened["data"]["payment_action"] == result["payment_action"]
        assert not closed
        assert sum(op == "subscription" for op, _ in FixtureProvider.calls) == 1
        assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == 0


@pytest.mark.parametrize("days", [20, 40])
@pytest.mark.parametrize("replay_contract", [False, True])
def test_paid_replay_preserves_newer_same_start_contract_end(
    integration_app: Flask, days: int, replay_contract: bool
) -> None:
    with integration_app.test_client() as client:
        result = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)["data"]
        reference = result["bill_order_bid"]
        event_time = int(now_utc().replace(tzinfo=UTC).timestamp())
        contract = {
            "provider_reference": "contract-replay",
            "status": "active",
            "period_start": event_time + 5,
            "period_end": event_time + 5 + 30 * 86400,
        }
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
        entries = CreditLedgerEntry.query.filter_by(source_bid=reference).all()
        ledger_before = [(entry.id, entry.expires_at) for entry in entries]
        updated = {**contract, "period_end": contract["period_start"] + days * 86400}
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                state="unknown",
                contract=updated,
                occurred_at=event_time + 1,
            ).status_code
            == 200
        )
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                contract=contract if replay_contract else None,
                occurred_at=event_time,
            ).status_code
            == 200
        )
        FixtureProvider.attempts[reference].update(
            state="paid", fixture_occurred_at=event_time
        )
        assert (
            client.post(f"/api/billing/orders/{reference}/sync", json={})
            .get_json(force=True)
            .get("code")
            == 0
        )
        dao.db.session.expire_all()
        assert (
            subscription.current_period_end_at.replace(tzinfo=UTC).timestamp()
            == updated["period_end"]
        )
        assert [
            (entry.id, entry.expires_at)
            for entry in CreditLedgerEntry.query.filter_by(source_bid=reference).all()
        ] == ledger_before


@pytest.mark.parametrize("action_type", ["jsapi", "sdk_confirm"])
def test_added_client_action_reuses_the_pending_learner_attempt(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, action_type: str
) -> None:
    """An explicit action needs no QR URL or a built-in route name to recover."""
    channel = "fixture_" + action_type
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            routes=(PaymentRoute(channel, "card", action_type, "embedded"),),
            default_channel=channel,
        ),
    )
    action = (
        PaymentAction(
            "jsapi",
            parameters={
                "appId": "fixture-app",
                "timeStamp": "1770000000",
                "nonceStr": "fixture-nonce",
                "package": "prepay_id=fixture",
                "signType": "RSA",
                "paySign": "fixture-signature",
            },
        )
        if action_type == "jsapi"
        else PaymentAction("sdk_confirm", sdk="stripe", client_secret="fixture_secret")
    )
    original_create = FixtureProvider.create_payment

    def create(self: FixtureProvider, **kwargs: object) -> PaymentCreationResult:
        result = original_create(self, **kwargs)
        result.action = action
        result.raw_response = {}
        result.extra = {}
        return result

    monkeypatch.setattr(FixtureProvider, "create_payment", create)
    monkeypatch.setattr(
        funs,
        "get_shifu_info",
        lambda *_args, **_kwargs: SimpleNamespace(
            bid="fixture-course", title="Fixture", description="Fixture"
        ),
    )
    monkeypatch.setattr(funs, "get_shifu_creator_bid", lambda *_args: "teacher-fixture")
    with unit_of_work():
        dao.db.session.add(
            Order(
                order_bid="fixture-action-order",
                user_bid="creator-1",
                shifu_bid="fixture-course",
                payable_price=Decimal(10),
                paid_price=Decimal(10),
                status=ORDER_STATUS_INIT,
            )
        )
    created = funs.generate_charge(
        integration_app,
        "fixture-action-order",
        channel,
        "127.0.0.1",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    assert created.payment_action == action
    reused = funs.generate_charge(
        integration_app,
        "fixture-action-order",
        channel,
        "127.0.0.1",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    assert reused.payment_action == action
    assert sum(operation == "payment" for operation, _ in FixtureProvider.calls) == 1
    assert (
        FixtureSnapshot.query.filter_by(order_bid="fixture-action-order").count() == 1
    )


def test_hosted_checkout_without_catalog_receives_trusted_return_urls(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hosted redirects need a return path independently of optional catalog support."""
    original_create = HostedFixtureProvider.create_subscription
    requests = []

    def create(self: HostedFixtureProvider, **kwargs: object) -> PaymentCreationResult:
        requests.append(kwargs["request"])
        return original_create(self, **kwargs)

    monkeypatch.setattr(HostedFixtureProvider, "create_subscription", create)
    with integration_app.test_client() as client:
        result = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
        assert result["code"] == 0, result
    extra = requests[0].extra
    for key in ("success_url", "cancel_url"):
        parsed = urlsplit(extra[key])
        assert parsed.scheme in {"http", "https"}
        assert parsed.netloc
        assert parsed.path.endswith("/payment/billing-result")
        assert parse_qs(parsed.query)["bill_order_bid"] == [
            result["data"]["bill_order_bid"]
        ]
    assert parse_qs(urlsplit(extra["cancel_url"]).query)["canceled"] == ["1"]


@pytest.mark.parametrize("separate_operations", [False, True])
def test_added_payment_reference_type_is_used_for_learner_query_and_close(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    separate_operations: bool,
) -> None:
    """A registered protocol must not require business-layer reference aliases."""
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            reference_type="fixture_reference",
            **(
                {
                    "query_reference_type": "checkout",
                    "close_reference_type": "payment",
                    "renewal_reference_type": "agreement",
                }
                if separate_operations
                else {}
            ),
        ),
    )
    monkeypatch.setitem(
        payment_providers.HISTORICAL_DEFINITIONS,
        FixtureProvider.channel,
        FixtureProvider.definition,
    )
    monkeypatch.setattr(
        funs,
        "get_shifu_info",
        lambda *_args, **_kwargs: SimpleNamespace(
            bid="fixture-course", title="Fixture", description="Fixture"
        ),
    )
    monkeypatch.setattr(funs, "get_shifu_creator_bid", lambda *_args: "teacher-fixture")
    with unit_of_work():
        dao.db.session.add(
            Order(
                order_bid="fixture-reference-order",
                user_bid="creator-1",
                shifu_bid="fixture-course",
                payable_price=Decimal(10),
                paid_price=Decimal(10),
                status=ORDER_STATUS_INIT,
            )
        )
    funs.generate_charge(
        integration_app,
        "fixture-reference-order",
        "fixture_qr",
        "127.0.0.1",
        payment_channel="fixture-pay",
        expected_user="creator-1",
    )
    operations = []

    def query(self: FixtureProvider, **kwargs: object) -> PaymentNotificationResult:
        assert kwargs["reference_type"] == (
            "checkout" if separate_operations else "fixture_reference"
        )
        operations.append("query")
        return self._notification(self.attempts[kwargs["provider_reference"]])

    original_close = FixtureProvider.cancel_payment

    def close(self: FixtureProvider, **kwargs: object) -> PaymentCancellationResult:
        assert kwargs["reference_type"] == (
            "payment" if separate_operations else "fixture_reference"
        )
        operations.append("close")
        return original_close(self, **kwargs)

    monkeypatch.setattr(FixtureProvider, "sync_reference", query)
    monkeypatch.setattr(FixtureProvider, "cancel_payment", close)
    assert (
        funs.sync_native_payment_order(
            integration_app, "fixture-reference-order", expected_user="creator-1"
        )["status"]
        == 0
    )
    with funs.payment_lifecycle_lock("fixture-reference-order"):
        assert funs.cancel_pending_payment_for_repricing(
            integration_app, "fixture-reference-order", expected_user="creator-1"
        )
    assert operations == ["query", "close"]
    assert (
        FixtureSnapshot.query.filter_by(order_bid="fixture-reference-order")
        .one()
        .status
        == 3
    )


def test_added_platform_managed_provider_can_pay_a_scheduled_renewal(
    integration_app: Flask,
) -> None:
    """The scheduler and checkout must share the integration's payment reference type."""
    app = integration_app
    add_active_subscription(app)
    with unit_of_work():
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-1"
        ).one()
        subscription.billing_provider = "fixture-pay"
        subscription.provider_subscription_id = ""
        order = subscriptions.ensure_subscription_renewal_order(app, subscription)
        order_bid = order.bill_order_bid
    with app.test_client() as client:
        created = client.post(f"/api/billing/orders/{order_bid}/checkout").get_json(
            force=True
        )
        assert created["code"] == 0, created
        FixtureProvider.attempts[order_bid]["state"] = "paid"
        for _ in range(2):
            synced = client.post(f"/api/billing/orders/{order_bid}/sync").get_json(
                force=True
            )
            assert synced["code"] == 0, synced
            assert synced["data"]["status"] == "paid"
        assert CreditLedgerEntry.query.filter_by(source_bid=order_bid).count() == 1


@pytest.mark.parametrize("custom_writer", [False, True])
def test_non_native_hosted_refund_persists_and_does_not_repeat_external_refunds(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    custom_writer: bool,
) -> None:
    app = integration_app
    add_active_subscription(app)
    monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, "fixture-hosted")
    monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, "fixture-hosted")
    monkeypatch.setattr(
        HostedFixtureProvider,
        "definition",
        replace(
            HostedFixtureProvider.definition,
            capabilities=replace(
                HostedFixtureProvider.definition.capabilities, refund=True
            ),
        ),
    )
    monkeypatch.setattr(
        provider_snapshots,
        "_NOTIFICATION_WRITERS",
        dict(provider_snapshots._NOTIFICATION_WRITERS),
    )
    monkeypatch.setattr(
        provider_snapshots, "_REFUND_WRITERS", dict(provider_snapshots._REFUND_WRITERS)
    )
    provider_snapshots.register_notification_writer(
        "fixture-hosted", lambda *_args: None
    )
    writer = Mock()
    if custom_writer:
        provider_snapshots.register_refund_writer("fixture-hosted", writer)
    refunds = []

    def refund(
        self: HostedFixtureProvider, *, request: object, app: object
    ) -> PaymentRefundResult:
        del self, app
        refunds.append(request.metadata["provider_reference"])
        return PaymentRefundResult(
            "hosted-refund", {"refund": "confirmed"}, "succeeded"
        )

    monkeypatch.setattr(HostedFixtureProvider, "refund_payment", refund)
    with config_overrides({"HOST_URL": "https://fixture.test"}):
        created = checkout.create_billing_topup_checkout(
            app,
            "creator-1",
            {
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        )
    reference = created.bill_order_bid
    payload = {**FixtureProvider.attempts[reference], "state": "paid"}
    body = json.dumps(payload).encode()
    verified = HostedFixtureProvider().verify_webhook(
        headers={
            "X-Fixture-Signature": hmac.new(
                b"fixture-key", body, hashlib.sha256
            ).hexdigest()
        },
        raw_body=body,
        app=app,
    )
    assert (
        webhooks.apply_billing_provider_notification(
            app, "fixture-hosted", verified
        ).status
        == "paid"
    )
    assert HostedFixtureSnapshot.query.count() == 0
    with pytest.raises(AppError):
        checkout.refund_billing_order(app, "another-user", reference, {})
    for _ in range(2):
        assert (
            checkout.refund_billing_order(app, "creator-1", reference, {}).status
            == "refunded"
        )
    assert refunds == [reference]
    order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
    assert order.status == BILLING_ORDER_STATUS_REFUNDED
    if custom_writer:
        writer.assert_called_once()
        assert writer.call_args.args[0] is order
    else:
        assert order.metadata_json["last_refund_id"] == "hosted-refund"
        assert order.metadata_json["refund_status"] == "succeeded"
        assert order.metadata_json["last_refund_response"] == {"refund": "confirmed"}


def test_billing_checkout_query_and_close_use_distinct_declared_reference_types(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = integration_app
    add_active_subscription(app)
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            query_reference_type="checkout",
            close_reference_type="payment",
        ),
    )
    monkeypatch.setitem(
        payment_providers.HISTORICAL_DEFINITIONS,
        "fixture-pay",
        FixtureProvider.definition,
    )
    calls = []

    def query(self: FixtureProvider, **kwargs: object) -> PaymentNotificationResult:
        calls.append(("query", kwargs["reference_type"]))
        assert kwargs["reference_type"] == "checkout"
        return self._notification(self.attempts[kwargs["provider_reference"]])

    original_close = FixtureProvider.cancel_payment

    def close(self: FixtureProvider, **kwargs: object) -> PaymentCancellationResult:
        calls.append(("close", kwargs["reference_type"]))
        assert kwargs["reference_type"] == "payment"
        return original_close(self, **kwargs)

    monkeypatch.setattr(FixtureProvider, "sync_reference", query)
    monkeypatch.setattr(FixtureProvider, "cancel_payment", close)
    created = checkout.create_billing_topup_checkout(
        app,
        "creator-1",
        {
            "product_bid": "bill-product-topup-small",
            "payment_option": "fixture-pay:fixture_qr",
        },
    )
    checkout._close_manual_payment_before_replacement(
        app, "creator-1", created.bill_order_bid
    )
    assert calls == [("query", "checkout"), ("close", "payment"), ("query", "checkout")]
    provider_recovery.reconcile_checkout_before_replacement(
        app,
        provider_name="fixture-pay",
        bill_order_bid=created.bill_order_bid,
        reference=created.bill_order_bid,
        client=FixtureProvider(),
    )
    assert calls[-1] == ("close", "payment")
    FixtureProvider().sync_payment_status(
        app=app,
        order_bid=created.bill_order_bid,
        provider_reference=created.bill_order_bid,
    )
    assert calls[-1] == ("query", "checkout")
    assert (
        BillingOrder.query.filter_by(bill_order_bid=created.bill_order_bid).one().status
        == BILLING_ORDER_STATUS_CANCELED
    )


@pytest.mark.parametrize("wrong_contract", [False, True])
def test_hosted_renewal_uses_declared_agreement_type_and_validates_contract_identity(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    wrong_contract: bool,
) -> None:
    app = integration_app
    add_active_subscription(app)
    definition = replace(
        HostedFixtureProvider.definition,
        query_reference_type="checkout",
        close_reference_type="payment",
        renewal_reference_type="agreement",
    )
    monkeypatch.setattr(HostedFixtureProvider, "definition", definition)
    monkeypatch.setitem(
        payment_providers.HISTORICAL_DEFINITIONS, "fixture-hosted", definition
    )
    with unit_of_work():
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-1"
        ).one()
        subscription.billing_provider = "fixture-hosted"
        subscription.status = BILLING_SUBSCRIPTION_STATUS_PAST_DUE
        order = subscriptions.ensure_subscription_renewal_order(app, subscription)
        reference, order_bid = (
            subscription.provider_subscription_id,
            order.bill_order_bid,
        )
        start, end = (
            subscription.current_period_start_at,
            subscription.current_period_end_at,
        )
    assert order.metadata_json["provider_reference_type"] == "agreement"
    contract = SubscriptionFacts(
        provider_reference="another-contract" if wrong_contract else reference,
        status="active",
        period_start=start,
        period_end=end,
    )
    calls = []

    def query(
        self: HostedFixtureProvider, **kwargs: object
    ) -> PaymentNotificationResult:
        del self
        calls.append((kwargs["provider_reference"], kwargs["reference_type"]))
        return PaymentNotificationResult(
            order_bid,
            "contract.query",
            {},
            facts=PaymentFacts(state="unknown", provider_reference="different-payment"),
            subscription=contract,
        )

    monkeypatch.setattr(HostedFixtureProvider, "sync_reference", query)
    if wrong_contract:
        with pytest.raises(RuntimeError, match="reference mismatch"):
            checkout.sync_billing_order(app, "creator-1", order_bid, {})
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE
    else:
        assert (
            checkout.sync_billing_order(app, "creator-1", order_bid, {}).status
            == "pending"
        )
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert calls == [(reference, "agreement")]
    assert order.status != BILLING_ORDER_STATUS_PAID
    assert CreditLedgerEntry.query.filter_by(source_bid=order_bid).count() == 0


@pytest.mark.parametrize("reopen_expired", [False, True])
@pytest.mark.parametrize("native_storage", [False, True])
def test_expired_hosted_checkout_closes_its_payment_reference_before_replacement(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    reopen_expired: bool,
    native_storage: bool,
) -> None:
    if not native_storage:
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, "fixture-hosted")
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, "fixture-hosted")
    with integration_app.test_client() as client:
        result = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)["data"]
        reference = result["bill_order_bid"]
        with unit_of_work():
            order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
            order.expires_at = now_utc() - timedelta(seconds=1)
        FixtureProvider.attempts[reference]["state"] = "unknown"
        closed: list[tuple[str, str]] = []
        original = HostedFixtureProvider.cancel_payment

        def close_payment(
            self: HostedFixtureProvider,
            *,
            provider_reference: str,
            reference_type: str,
            app: object,
        ) -> PaymentCancellationResult:
            closed.append((provider_reference, reference_type))
            assert reference_type == "payment"
            return original(
                self,
                provider_reference=provider_reference,
                reference_type=reference_type,
                app=app,
            )

        monkeypatch.setattr(HostedFixtureProvider, "cancel_payment", close_payment)
        if reopen_expired:
            expired = client.post(
                f"/api/billing/orders/{reference}/checkout", json={}
            ).get_json(force=True)
            assert expired.get("code") == 3006, expired
            assert not closed
        reopened = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
        assert reopened.get("code") == 0, reopened
        assert reopened["data"]["bill_order_bid"] != reference
        assert closed == [(reference, "payment")]
        assert FixtureProvider.attempts[reference]["state"] == "canceled"
        assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == 0


@pytest.mark.parametrize(
    "status", [BILLING_ORDER_STATUS_CANCELED, BILLING_ORDER_STATUS_REFUNDED]
)
@pytest.mark.parametrize("source", ["query", "notification"])
def test_rejected_paid_update_does_not_activate_a_hosted_subscription(
    integration_app: Flask, status: int, source: str
) -> None:
    with integration_app.test_client() as client:
        result = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)["data"]
        reference = result["bill_order_bid"]
        with unit_of_work():
            order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid=order.subscription_bid
            ).one()
            before = (
                subscription.status,
                subscription.current_period_start_at,
                subscription.current_period_end_at,
            )
            order.status = status
            if status == BILLING_ORDER_STATUS_CANCELED:
                order.metadata_json = {
                    **order.metadata_json,
                    "invalidated_reason": "replaced_by_new_package",
                }
        FixtureProvider.attempts[reference]["state"] = "paid"
        if source == "query":
            synced = client.post(
                f"/api/billing/orders/{reference}/sync", json={}
            ).get_json(force=True)
            assert synced.get("code") == 0, synced
        else:
            assert _notify(client, "fixture-hosted", reference).status_code == 200
        dao.db.session.expire_all()
        assert order.status == status
        assert (
            subscription.status,
            subscription.current_period_start_at,
            subscription.current_period_end_at,
        ) == before
        assert CreditLedgerEntry.query.filter_by(source_bid=reference).count() == 0
        assert CreditWalletBucket.query.filter_by(source_bid=reference).count() == 0


@pytest.mark.parametrize(
    ("provider_status", "expected_status", "cancel_at_period_end"),
    [
        ("active", BILLING_SUBSCRIPTION_STATUS_ACTIVE, False),
        ("active", BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED, True),
        ("past_due", BILLING_SUBSCRIPTION_STATUS_PAST_DUE, False),
        ("paused", BILLING_SUBSCRIPTION_STATUS_PAUSED, False),
        ("canceled", BILLING_SUBSCRIPTION_STATUS_CANCELED, False),
    ],
)
def test_late_contract_facts_remain_authoritative_after_payment_only_settlement(
    integration_app: Flask,
    provider_status: str,
    expected_status: int,
    cancel_at_period_end: bool,
) -> None:
    with integration_app.test_client() as client:
        result = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)["data"]
        reference = result["bill_order_bid"]
        event_time = int(now_utc().replace(tzinfo=UTC).timestamp()) + 10
        assert (
            _notify(
                client, "fixture-hosted", reference, occurred_at=event_time
            ).status_code
            == 200
        )
        order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=order.subscription_bid
        ).one()
        ledger_before = [
            (row.id, row.expires_at)
            for row in CreditLedgerEntry.query.filter_by(source_bid=reference).all()
        ]
        assert ledger_before
        contract = {
            "provider_reference": "late-contract",
            "status": provider_status,
            "cancel_at_period_end": cancel_at_period_end,
            "period_start": event_time + 5,
            "period_end": event_time + 25 * 86400,
        }
        assert (
            _notify(
                client,
                "fixture-hosted",
                reference,
                state="unknown",
                contract=contract,
                occurred_at=event_time + 20,
            ).status_code
            == 200
        )
        dao.db.session.expire_all()
        assert subscription.status == expected_status
        assert bool(subscription.cancel_at_period_end) == cancel_at_period_end
        assert (
            subscription.current_period_start_at.replace(tzinfo=UTC).timestamp()
            == contract["period_start"]
        )
        assert (
            subscription.current_period_end_at.replace(tzinfo=UTC).timestamp()
            == contract["period_end"]
        )
        assert (
            client.post(f"/api/billing/orders/{reference}/sync", json={})
            .get_json(force=True)
            .get("code")
            == 0
        )
        dao.db.session.expire_all()
        assert subscription.status == expected_status
        assert bool(subscription.cancel_at_period_end) == cancel_at_period_end
        assert (
            subscription.current_period_start_at.replace(tzinfo=UTC).timestamp()
            == contract["period_start"]
        )
        assert (
            subscription.current_period_end_at.replace(tzinfo=UTC).timestamp()
            == contract["period_end"]
        )
        assert [
            (row.id, row.expires_at)
            for row in CreditLedgerEntry.query.filter_by(source_bid=reference).all()
        ] == ledger_before

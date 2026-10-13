"""Require management capabilities and release transactions before provider calls."""

import threading
from dataclasses import replace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao import uow
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing.consts import (
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
)
from flaskr.service.order.payment_providers.base import SubscriptionUpdateResult

from tests.service.billing.test_contract_identity import _case
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    HostedFixtureProvider,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("action", ["cancel", "resume"])
@pytest.mark.parametrize("supported", [False, True])
def test_write_api_enforces_management_capability_before_provider_io(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    supported: bool,
) -> None:
    app = integration_app
    _order, sub = _case(app, "fixture-hosted")
    if action == "resume":
        with unit_of_work():
            sub.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            sub.cancel_at_period_end = 1
    before = (sub.status, sub.cancel_at_period_end)
    monkeypatch.setattr(
        HostedFixtureProvider,
        "definition",
        replace(
            HostedFixtureProvider.definition,
            capabilities=replace(
                HostedFixtureProvider.definition.capabilities,
                **{f"subscription_{action}": supported},
            ),
        ),
    )
    calls = []

    def manage(*_args: object, **kwargs: object) -> SubscriptionUpdateResult:
        assert not uow.in_unit_of_work()
        assert not dao.db.session().in_transaction()
        calls.append(kwargs["provider_subscription_id"])
        return SubscriptionUpdateResult(
            "sub_current", {}, "active", {"cancel_at_period_end": action == "cancel"}
        )

    monkeypatch.setattr(HostedFixtureProvider, f"{action}_subscription", manage)
    with app.test_client() as client:
        response = client.post(
            f"/api/billing/subscriptions/{action}",
            json={"subscription_bid": sub.subscription_bid},
        ).get_json(force=True)
    if supported:
        assert response["code"] == 0, response
        assert calls == ["sub_current"]
        assert response["data"]["status"] == (
            "cancel_scheduled" if action == "cancel" else "active"
        )
    else:
        assert response["code"] != 0
        assert calls == []
        dao.db.session.expire_all()
        assert (sub.status, sub.cancel_at_period_end) == before


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("action", ["cancel", "resume"])
@pytest.mark.parametrize("callback_status", ["canceled", "past_due"])
def test_management_cannot_overwrite_a_contract_webhook_committed_during_io(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    callback_status: str,
) -> None:
    app = integration_app
    order, sub = _case(app, "fixture-hosted")
    if action == "resume":
        with unit_of_work():
            sub.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            sub.cancel_at_period_end = 1
    FixtureProvider.attempts[order.bill_order_bid] = {
        "reference": order.bill_order_bid,
        "state": "unknown",
        "amount": 9900,
        "currency": "CNY",
    }
    order_bid = order.bill_order_bid
    errors = []

    def manage(*_args: object, **_kwargs: object) -> SubscriptionUpdateResult:
        assert not uow.in_unit_of_work()
        assert not dao.db.session().in_transaction()

        def callback() -> None:
            try:
                with app.test_client() as client:
                    assert (
                        _notify(
                            client,
                            "fixture-hosted",
                            order_bid,
                            state="unknown",
                            contract={
                                "provider_reference": "sub_current",
                                "status": callback_status,
                            },
                        ).status_code
                        == 200
                    )
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=callback, daemon=True)
        worker.start()
        worker.join(5)
        assert not worker.is_alive()
        assert errors == []
        return SubscriptionUpdateResult(
            "sub_current", {}, "active", {"cancel_at_period_end": action == "cancel"}
        )

    monkeypatch.setattr(HostedFixtureProvider, f"{action}_subscription", manage)
    with app.test_client() as client:
        client.post(
            f"/api/billing/subscriptions/{action}",
            json={"subscription_bid": sub.subscription_bid},
        )
    dao.db.session.expire_all()
    assert sub.status == (
        BILLING_SUBSCRIPTION_STATUS_CANCELED
        if callback_status == "canceled"
        else BILLING_SUBSCRIPTION_STATUS_PAST_DUE
    )
    assert sub.provider_subscription_id == "sub_current"


@pytest.mark.parametrize("action", ["cancel", "resume"])
def test_platform_managed_subscription_uses_local_policy_without_remote_capability(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    app = integration_app
    _order, sub = _case(app, "fixture-pay")
    if action == "resume":
        with unit_of_work():
            sub.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            sub.cancel_at_period_end = 1

    def refuse(*_args: object, **_kwargs: object) -> None:
        message = "A local subscription must not call a provider contract API"
        raise AssertionError(message)

    monkeypatch.setattr(FixtureProvider, f"{action}_subscription", refuse)
    with app.test_client() as client:
        result = client.post(
            f"/api/billing/subscriptions/{action}",
            json={"subscription_bid": sub.subscription_bid},
        ).get_json(force=True)
    assert result["code"] == 0, result
    assert result["data"]["status"] == (
        "cancel_scheduled" if action == "cancel" else "active"
    )


@pytest.mark.parametrize("action", ["cancel", "resume"])
def test_management_provider_failure_does_not_commit_local_subscription_changes(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    from flaskr.service.billing import subscriptions

    app = integration_app
    _order, sub = _case(app, "fixture-hosted")
    if action == "resume":
        with unit_of_work():
            sub.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            sub.cancel_at_period_end = 1
    before = (sub.status, sub.cancel_at_period_end, sub.metadata_json)
    bid = sub.subscription_bid

    def fail(*_args: object, **_kwargs: object) -> None:
        assert not uow.in_unit_of_work()
        assert not dao.db.session().in_transaction()
        message = "Injected provider command failure"
        raise RuntimeError(message)

    monkeypatch.setattr(HostedFixtureProvider, f"{action}_subscription", fail)
    with pytest.raises(RuntimeError, match="Injected provider command failure"):
        getattr(subscriptions, f"{action}_billing_subscription")(
            app, "creator-1", {"subscription_bid": bid}
        )
    dao.db.session.expire_all()
    assert (sub.status, sub.cancel_at_period_end, sub.metadata_json) == before
    with pytest.raises(RuntimeError, match="owns its own transaction"), unit_of_work():
        getattr(subscriptions, f"{action}_billing_subscription")(
            app, "creator-1", {"subscription_bid": bid}
        )


@pytest.mark.parametrize("action", ["cancel", "resume"])
@pytest.mark.parametrize("state", [None, "canceled", "past_due"])
def test_stripe_management_preserves_current_contract_during_provider_io(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    state: str | None,
) -> None:
    from flaskr.service.billing import subscriptions, webhooks
    from flaskr.service.common.models import AppError
    from flaskr.service.order.payment_providers.stripe import StripeProvider

    from tests.service.billing.test_contract_identity import _notification

    app = integration_app
    _order, sub = _case(app, "stripe")
    if action == "resume":
        with unit_of_work():
            sub.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            sub.cancel_at_period_end = 1
    bid = sub.subscription_bid

    calls = []

    def manage(*_args: object, **kwargs: object) -> SubscriptionUpdateResult:
        assert not uow.in_unit_of_work()
        assert not dao.db.session().in_transaction()
        assert kwargs["provider_subscription_id"] == "sub_current"
        calls.append(True)
        if state:
            assert (
                webhooks.apply_billing_stripe_notification(
                    app, _notification("stripe", "sub_current", state)
                ).status_code
                == 200
            )
        if state:
            assert sub.status == (
                BILLING_SUBSCRIPTION_STATUS_CANCELED
                if state == "canceled"
                else BILLING_SUBSCRIPTION_STATUS_PAST_DUE
            )
        return SubscriptionUpdateResult(
            "sub_current", {}, "active", {"cancel_at_period_end": action == "cancel"}
        )

    monkeypatch.setattr(StripeProvider, f"{action}_subscription", manage)
    call = getattr(subscriptions, f"{action}_billing_subscription")
    if state:
        with pytest.raises(AppError):
            call(app, "creator-1", {"subscription_bid": bid})
    else:
        assert call(app, "creator-1", {"subscription_bid": bid}).status == (
            "cancel_scheduled" if action == "cancel" else "active"
        )
    assert calls == [True]
    dao.db.session.expire_all()
    if state:
        assert sub.status == (
            BILLING_SUBSCRIPTION_STATUS_CANCELED
            if state == "canceled"
            else BILLING_SUBSCRIPTION_STATUS_PAST_DUE
        )
        assert sub.metadata_json["last_subscription_command"]["superseded"] is True


@pytest.mark.parametrize("provider_name", ["stripe", "fixture-hosted"])
@pytest.mark.parametrize("action", ["cancel", "resume"])
@pytest.mark.parametrize("reported", ["sub_current", "sub_foreign", ""])
def test_management_response_must_identify_the_requested_contract(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    action: str,
    reported: str,
) -> None:
    from copy import deepcopy

    from flaskr.service.billing import subscriptions
    from flaskr.service.common.models import AppError
    from flaskr.service.order.payment_providers.stripe import StripeProvider

    app = integration_app
    _order, sub = _case(app, provider_name)
    if action == "resume":
        with unit_of_work():
            sub.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            sub.cancel_at_period_end = 1
    before = (sub.status, sub.cancel_at_period_end, deepcopy(sub.metadata_json))
    bid = sub.subscription_bid
    calls = []

    def manage(*_args: object, **_kwargs: object) -> SubscriptionUpdateResult:
        assert not uow.in_unit_of_work()
        assert not dao.db.session().in_transaction()
        calls.append(True)
        return SubscriptionUpdateResult(
            reported,
            {"id": reported},
            "active",
            {"cancel_at_period_end": action == "cancel"},
        )

    monkeypatch.setattr(
        StripeProvider if provider_name == "stripe" else HostedFixtureProvider,
        f"{action}_subscription",
        manage,
    )
    call = getattr(subscriptions, f"{action}_billing_subscription")
    if reported == "sub_current":
        assert call(app, "creator-1", {"subscription_bid": bid}).status == (
            "cancel_scheduled" if action == "cancel" else "active"
        )
    else:
        with pytest.raises(AppError):
            call(app, "creator-1", {"subscription_bid": bid})
        dao.db.session.expire_all()
        assert (sub.status, sub.cancel_at_period_end, sub.metadata_json) == before
    assert calls == [True]

"""Management commands require confirmed state without inventing paid access."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import subscriptions
from flaskr.service.billing.consts import (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
)
from flaskr.service.billing.models import CreditLedgerEntry
from flaskr.service.common.models import AppError
from flaskr.service.order.payment_providers.base import SubscriptionUpdateResult
from flaskr.service.order.payment_providers.stripe import StripeProvider

from tests.service.billing.test_contract_identity import _case
from tests.service.order.test_payment_contract_extension import (
    HostedFixtureProvider,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("provider", ["stripe", "fixture-hosted"])
@pytest.mark.parametrize("action", ["cancel", "resume"])
@pytest.mark.parametrize(
    ("state", "flag"),
    [
        ("pending", "correct"),
        ("failed", "correct"),
        ("canceled", "correct"),
        ("unknown", "correct"),
        ("", "correct"),
        ("active", "opposite"),
        ("active", "missing"),
        ("active", "string"),
    ],
)
def test_unconfirmed_command_cannot_change_subscription_or_credits(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    action: str,
    state: str,
    flag: str,
) -> None:
    _run_command(
        integration_app, monkeypatch, provider, action, state, flag, reject=True
    )


@pytest.mark.parametrize("provider", ["stripe", "fixture-hosted"])
@pytest.mark.parametrize("action", ["cancel", "resume"])
@pytest.mark.parametrize("state", ["active", "trialing", "past_due", "paused"])
def test_confirmed_command_preserves_the_actual_contract_state(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    action: str,
    state: str,
) -> None:
    _run_command(integration_app, monkeypatch, provider, action, state, "correct")


@pytest.mark.parametrize("action", ["cancel", "resume"])
def test_stripe_unpaid_remains_delinquent_after_management(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    _run_command(integration_app, monkeypatch, "stripe", action, "unpaid", "correct")


@pytest.mark.parametrize("provider", ["stripe", "fixture-hosted"])
@pytest.mark.parametrize("state", ["trialing", "past_due", "paused"])
def test_confirmed_cancellation_can_be_reversed_without_restoring_blocked_access(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, provider: str, state: str
) -> None:
    app = integration_app
    _order, sub = _case(app, provider)
    bid = sub.subscription_bid
    ledger_before = CreditLedgerEntry.query.count()

    def result(*, cancel: bool) -> SubscriptionUpdateResult:
        payload = {"id": "sub_current", "status": state, "cancel_at_period_end": cancel}
        return SubscriptionUpdateResult(
            "sub_current",
            payload,
            state,
            {
                "cancel_at_period_end": cancel,
            },
        )

    if provider == "stripe":
        modify = Mock(
            side_effect=lambda *_a, **kw: SimpleNamespace(
                to_dict=lambda: result(cancel=kw["cancel_at_period_end"]).raw_response,
            )
        )
        sdk = SimpleNamespace(Subscription=SimpleNamespace(modify=modify))
        monkeypatch.setattr(StripeProvider, "_client_options", lambda *_a: (sdk, {}))
    else:
        monkeypatch.setattr(
            HostedFixtureProvider,
            "cancel_subscription",
            lambda *_a, **_kw: result(cancel=True),
        )
        monkeypatch.setattr(
            HostedFixtureProvider,
            "resume_subscription",
            lambda *_a, **_kw: result(cancel=False),
        )
    with app.test_client() as client:
        canceled = client.post(
            "/api/billing/subscriptions/cancel", json={"subscription_bid": bid}
        ).get_json(force=True)
        assert canceled["code"] == 0, canceled
        assert canceled["data"]["management_operations"]["resume"] is True
        resumed = client.post(
            "/api/billing/subscriptions/resume", json={"subscription_bid": bid}
        ).get_json(force=True)
        assert resumed["code"] == 0, resumed
        assert resumed["data"]["status"] == ("active" if state == "trialing" else state)
        assert resumed["data"]["cancel_at_period_end"] is False
    assert CreditLedgerEntry.query.count() == ledger_before


def _run_command(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    action: str,
    state: str,
    flag: str,
    *,
    reject: bool = False,
) -> None:
    _order, sub = _case(app, provider)
    if action == "resume":
        with unit_of_work():
            sub.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            sub.cancel_at_period_end = 1
    bid = sub.subscription_bid
    before = (
        sub.status,
        sub.cancel_at_period_end,
        deepcopy(sub.metadata_json),
        sub.last_renewed_at,
        sub.current_period_end_at,
    )
    ledger_before = CreditLedgerEntry.query.count()
    cancel = action == "cancel"
    flags = {"correct": cancel, "opposite": not cancel, "string": str(cancel)}
    extra = {} if flag == "missing" else {"cancel_at_period_end": flags[flag]}
    payload = {"id": "sub_current", "status": state, **extra}
    calls = Mock(return_value=SimpleNamespace(to_dict=lambda: payload))
    if provider == "stripe":
        sdk = SimpleNamespace(Subscription=SimpleNamespace(modify=calls))
        monkeypatch.setattr(StripeProvider, "_client_options", lambda *_a: (sdk, {}))
    else:
        calls.return_value = SubscriptionUpdateResult(
            "sub_current", payload, state, extra
        )
        monkeypatch.setattr(HostedFixtureProvider, f"{action}_subscription", calls)
    execute = getattr(subscriptions, f"{action}_billing_subscription")
    if reject:
        with pytest.raises(AppError):
            execute(app, "creator-1", {"subscription_bid": bid})
    else:
        result = execute(app, "creator-1", {"subscription_bid": bid})
        expected = (
            ("cancel_scheduled" if cancel else "active")
            if state in {"active", "trialing"}
            else ("past_due" if state == "unpaid" else state)
        )
        assert result.status == expected
    calls.assert_called_once()
    if provider == "stripe":
        calls.assert_called_once_with(
            "sub_current",
            cancel_at_period_end=cancel,
            metadata={"subscription_bid": bid},
        )
    dao.db.session.expire_all()
    if reject:
        assert (
            sub.status,
            sub.cancel_at_period_end,
            sub.metadata_json,
            sub.last_renewed_at,
            sub.current_period_end_at,
        ) == before
    else:
        expected_status = {
            "active": BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            "cancel_scheduled": BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
            "past_due": BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
            "paused": BILLING_SUBSCRIPTION_STATUS_PAUSED,
        }[expected]
        assert sub.status == expected_status
        assert sub.cancel_at_period_end == int(cancel)
        assert sub.last_renewed_at == before[3]
        assert sub.current_period_end_at == before[4]
        assert sub.metadata_json["provider_contract_confirmed"] is True
    assert CreditLedgerEntry.query.count() == ledger_before

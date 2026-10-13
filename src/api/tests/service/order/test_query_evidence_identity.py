"""A successful query must identify the payment or contract it describes."""

from dataclasses import replace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing import checkout
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
)
from flaskr.service.billing.models import BillingOrder, CreditLedgerEntry
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.payment_providers.alipay import AlipayProvider
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.order.payment_providers.contracts import (
    PaymentFacts,
    PaymentQueryTerms,
    SubscriptionFacts,
)
from flaskr.service.order.payment_providers.wechatpay import WechatPayProvider

from tests.service.billing.test_billing_query_races import _create_topup
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    _learner_sync_case,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize(
    "adapter", [FixtureProvider, AlipayProvider, WechatPayProvider]
)
@pytest.mark.parametrize("kind", ["payment", "contract"])
@pytest.mark.parametrize("reported", [None, "", " ", "foreign", "query-reference"])
def test_default_query_requires_the_requested_evidence_identity(
    adapter: type, kind: str, reported: str | None
) -> None:
    contract = kind == "contract"
    result = PaymentNotificationResult(
        "merchant-order",
        "manual_sync",
        {},
        facts=PaymentFacts(
            state="paid",
            order_amount=1000,
            currency="CNY",
            provider_reference="other-payment" if contract else reported,
        ),
        subscription=SubscriptionFacts(reported or "", "active") if contract else None,
    )
    terms = PaymentQueryTerms(
        "query-reference",
        "subscription" if contract else "payment",
        "merchant-order",
        "customer",
        "product",
    )
    if reported == "query-reference":
        assert (
            adapter.describe_query(result, terms).updated_payment_reference == reported
        )
    else:
        with pytest.raises(RuntimeError, match="reference mismatch"):
            adapter.describe_query(result, terms)


@pytest.mark.parametrize("domain", ["learner", "billing"])
@pytest.mark.parametrize("reported", [None, "", "foreign", "match"])
def test_unidentified_paid_query_cannot_grant_business_access(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
    reported: str | None,
) -> None:
    app = integration_app
    if domain == "learner":
        order, snapshot, notifications = _learner_sync_case(app, monkeypatch)
        bid, reference = order.order_bid, snapshot.provider_attempt_id
    else:
        bid = _create_topup(app)
        order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
        reference = order.provider_reference_id
        FixtureProvider.attempts[reference]["state"] = "paid"
    original = FixtureProvider.sync_reference

    def query(self: FixtureProvider, **kwargs: object) -> PaymentNotificationResult:
        result = original(self, **kwargs)
        result.facts = replace(
            result.facts,
            provider_reference=reference if reported == "match" else reported,
        )
        return result

    monkeypatch.setattr(FixtureProvider, "sync_reference", query)

    def execute() -> None:
        if domain == "learner":
            funs.sync_native_payment_order(app, bid, expected_user="creator-1")
        else:
            checkout.sync_billing_order(app, "creator-1", bid, {})

    if reported == "match":
        execute()
        execute()
    else:
        with pytest.raises(RuntimeError, match="reference mismatch"):
            execute()
    dao.db.session.expire_all()
    if domain == "learner":
        assert (order.status == ORDER_STATUS_SUCCESS) == (reported == "match")
        assert snapshot.status == (1 if reported == "match" else 0)
        assert notifications == (["paid"] if reported == "match" else [])
    else:
        assert order.status == (
            BILLING_ORDER_STATUS_PAID
            if reported == "match"
            else BILLING_ORDER_STATUS_PENDING
        )
        assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == (
            1 if reported == "match" else 0
        )

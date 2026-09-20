"""Verify trial recovery against persisted eligibility and transactional failures."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.billing import trials
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_TRIAL_PRODUCT_BID,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing.test_billing_tasks import (
    billing_task_integration_app as trial_app,
)
from tests.service.billing.test_billing_trial_credits import _seed_creator

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["trial_app"]


@pytest.fixture
def catalog(trial_app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    assert trial_app.testing
    monkeypatch.setattr(trials, "_is_billing_enabled", lambda: True)
    db.session.add_all(build_bill_products())
    db.session.commit()


def _order(creator: str, metadata: object) -> BillingOrder:
    return BillingOrder(
        bill_order_bid=trials._build_trial_order_bid(creator),
        creator_bid=creator,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        product_bid=BILLING_TRIAL_PRODUCT_BID,
        subscription_bid="",
        currency="CNY",
        payable_amount=0,
        paid_amount=0,
        payment_provider="manual",
        channel="manual",
        provider_reference_id="",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=datetime(2026, 4, 1),
        metadata_json=metadata,
    )


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize(
    ("eligibility", "reason"),
    [
        ("missing_creator", "creator_not_found"),
        ("learner", "not_creator"),
        ("missing_product", "trial_product_missing"),
        ("private_product", "trial_product_not_public"),
        ("active_subscription", "active_subscription_exists"),
        ("draft_trial", "trial_subscription_exists"),
        ("paid_trial_order", "trial_order_exists"),
    ],
)
def test_ineligible_teacher_cannot_receive_another_trial(
    trial_app: Flask, eligibility: str, reason: str
) -> None:
    creator = "trial-boundary-teacher"
    if eligibility != "missing_creator":
        _seed_creator(user_bid=creator, is_creator=eligibility != "learner")
    product = BillingProduct.query.filter_by(
        product_bid=BILLING_TRIAL_PRODUCT_BID
    ).one()
    if eligibility == "missing_product":
        product.deleted = 1
    elif eligibility == "private_product":
        product.metadata_json = {BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG: False}
    elif eligibility in {"active_subscription", "draft_trial"}:
        db.session.add(
            BillingSubscription(
                subscription_bid="pre-existing",
                creator_bid=creator,
                product_bid=(
                    BILLING_TRIAL_PRODUCT_BID
                    if eligibility == "draft_trial"
                    else "paid-product"
                ),
                status=(
                    BILLING_SUBSCRIPTION_STATUS_DRAFT
                    if eligibility == "draft_trial"
                    else BILLING_SUBSCRIPTION_STATUS_ACTIVE
                ),
                billing_provider="manual",
                metadata_json={},
            )
        )
    elif eligibility == "paid_trial_order":
        db.session.add(_order(creator, {}))
    db.session.commit()
    before_orders = BillingOrder.query.count()
    status, _ = trials._resolve_trial_bootstrap_status(creator)
    assert status == reason
    trials.bootstrap_new_creator_trial_credits(trial_app, creator)
    assert BillingOrder.query.count() == before_orders
    assert CreditLedgerEntry.query.count() == 0
    assert CreditWallet.query.count() == 0


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize("state", ["disabled", "missing_product", "private_product"])
def test_backfill_explains_catalog_gates_without_creating_rows(
    trial_app: Flask, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    _seed_creator(user_bid="trial-gated")
    product = BillingProduct.query.filter_by(
        product_bid=BILLING_TRIAL_PRODUCT_BID
    ).one()
    if state == "disabled":
        monkeypatch.setattr(trials, "_is_billing_enabled", lambda: False)
        expected = "billing_disabled"
    elif state == "missing_product":
        product.deleted = 1
        expected = "trial_product_missing"
    else:
        product.metadata_json = {BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG: False}
        expected = "trial_product_not_public"
    db.session.commit()
    result = trials.backfill_missing_creator_trial_credits(trial_app, limit=0)
    assert result["status"] == "noop"
    assert result["reason"] == expected
    assert result["limit"] is None
    assert result["records"] == []
    assert BillingOrder.query.count() == 0


@pytest.mark.usefixtures("catalog")
def test_backfill_missing_teacher_has_explicit_skipped_result(trial_app: Flask) -> None:
    result = trials.backfill_missing_creator_trial_credits(
        trial_app, creator_bid=" unknown ", limit=1
    )
    assert result["creator_count"] == result["skipped_count"] == 1
    assert result["granted_count"] == 0
    assert result["records"] == [
        {
            "creator_bid": "unknown",
            "status": "skipped",
            "reason": "creator_not_found",
        }
    ]


@pytest.mark.usefixtures("catalog")
def test_backfill_recovers_after_one_teacher_loses_insert_race(
    trial_app: Flask,
) -> None:
    _seed_creator(user_bid="conflicted")
    _seed_creator(user_bid="eligible")
    _seed_creator(user_bid="beyond-limit")

    def reject_first(
        _mapper: object, _connection: object, target: BillingSubscription
    ) -> None:
        if target.creator_bid == "conflicted":
            message = "trial uniqueness constraint"
            raise IntegrityError(message, {}, RuntimeError("duplicate"))

    event.listen(BillingSubscription, "before_insert", reject_first)
    try:
        result = trials.backfill_missing_creator_trial_credits(trial_app, limit=2)
    finally:
        event.remove(BillingSubscription, "before_insert", reject_first)
    assert result["creator_count"] == 2
    assert result["granted_count"] == result["skipped_count"] == 1
    assert result["records"] == [
        {
            "creator_bid": "conflicted",
            "status": "skipped",
            "reason": "integrity_conflict",
        },
        {"creator_bid": "eligible", "status": "granted", "reason": None},
    ]
    db.session.expire_all()
    assert BillingOrder.query.one().creator_bid == "eligible"
    assert BillingSubscription.query.one().creator_bid == "eligible"
    assert CreditWallet.query.one().available_credits == Decimal(100)
    assert CreditLedgerEntry.query.one().creator_bid == "eligible"
    assert CreditWalletBucket.query.one().creator_bid == "eligible"
    assert BillingRenewalEvent.query.one().creator_bid == "eligible"


@pytest.mark.usefixtures("catalog")
def test_bootstrap_insert_race_is_absorbed_without_partial_entitlements(
    trial_app: Flask,
) -> None:
    _seed_creator(user_bid="racing-teacher")

    def reject_order(
        _mapper: object, _connection: object, _target: BillingOrder
    ) -> None:
        message = "trial uniqueness constraint"
        raise IntegrityError(message, {}, RuntimeError("duplicate"))

    event.listen(BillingOrder, "before_insert", reject_order)
    try:
        trials.bootstrap_new_creator_trial_credits(trial_app, "racing-teacher")
    finally:
        event.remove(BillingOrder, "before_insert", reject_order)
    assert BillingSubscription.query.count() == BillingOrder.query.count() == 0
    assert CreditWallet.query.count() == CreditLedgerEntry.query.count() == 0


@pytest.mark.usefixtures("catalog")
def test_failed_grant_rolls_back_subscription_order_wallet_and_renewal(
    trial_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_creator(user_bid="failed-grant")
    real_grant = trials._grant_paid_order_credits

    def grant_then_reject(app: Flask, order: BillingOrder) -> bool:
        assert real_grant(app, order) is True
        db.session.flush()
        assert CreditLedgerEntry.query.count() == 1
        return False

    monkeypatch.setattr(trials, "_grant_paid_order_credits", grant_then_reject)
    with pytest.raises(RuntimeError, match="trial_order_credit_grant_failed"):
        trials.bootstrap_new_creator_trial_credits(trial_app, "failed-grant")
    db.session.expire_all()
    for model in (
        BillingSubscription,
        BillingOrder,
        CreditWallet,
        CreditWalletBucket,
        CreditLedgerEntry,
        BillingRenewalEvent,
    ):
        assert model.query.count() == 0


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize("expiry", ["invalid-date", " ", 123])
def test_legacy_order_with_unparseable_expiry_preserves_granted_state(
    trial_app: Flask, expiry: object
) -> None:
    _seed_creator(user_bid="legacy-order")
    db.session.add(
        _order(
            "legacy-order",
            {
                "trial_expires_at": expiry,
                "welcome_trial_dialog_acknowledged_at": "not-a-date",
                "audit_reference": "kept",
            },
        )
    )
    db.session.commit()
    offer = trials.resolve_new_creator_trial_offer("legacy-order", trigger="overview")
    assert offer.status == "granted"
    assert offer.granted_at == datetime(2026, 4, 1)
    assert offer.expires_at is None
    assert offer.welcome_dialog_acknowledged_at is None
    result = trials.acknowledge_trial_welcome_dialog(trial_app, "legacy-order")
    again = trials.acknowledge_trial_welcome_dialog(trial_app, "legacy-order")
    assert result.acknowledged is True
    assert again.acknowledged_at == result.acknowledged_at
    assert BillingOrder.query.one().metadata_json["audit_reference"] == "kept"


@pytest.mark.parametrize("metadata_key", ["metadata", "metadata_json"])
def test_dict_trial_catalog_contract_preserves_configured_terms(
    metadata_key: str,
) -> None:
    reference = {
        "product_bid": "imported-trial",
        "credit_amount": "12.5",
        "currency": "USD",
        metadata_key: {
            "trial_valid_days": 7,
            "highlights": ["one", "", None, "two"],
            "starts_on_first_grant": False,
        },
    }
    state = trials._build_trial_offer_state(reference, enabled=True, status="eligible")
    assert state.product_bid == "imported-trial"
    assert state.credit_amount == Decimal("12.5")
    assert state.valid_days == 7
    assert state.highlights == ("one", "two")
    assert state.starts_on_first_grant is False


@pytest.mark.usefixtures("catalog")
def test_missing_catalog_offer_is_disabled_with_default_terms() -> None:
    BillingProduct.query.filter_by(
        product_bid=BILLING_TRIAL_PRODUCT_BID
    ).one().deleted = 1
    db.session.commit()
    result = trials.resolve_new_creator_trial_offer("unknown", trigger="overview")
    assert result.enabled is False
    assert result.status == "disabled"
    assert result.highlights == []
    assert result.valid_days == 15


@pytest.mark.usefixtures("catalog")
def test_blank_trial_identity_is_noop(trial_app: Flask) -> None:
    assert trials._resolve_trial_bootstrap_status(" ") == ("invalid_creator_bid", None)
    trials.bootstrap_new_creator_trial_credits(trial_app, " ")
    trials._enqueue_trial_credit_notification(trial_app, " ")
    result = trials.acknowledge_trial_welcome_dialog(trial_app, " ")
    assert result.acknowledged is False
    assert BillingOrder.query.count() == 0

"""Unit-of-work behavior for the B5 billing call sites."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from flaskr import dao
from flaskr.service.billing import campaigns, trials, wallets
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    CreditLedgerEntry,
    CreditWalletBucket,
)

from tests.common.fixtures.bill_products import build_billing_product


def _committed_rows(app: object, table: object, *conditions: object) -> list[object]:
    with app.app_context(), dao.db.engine.connect() as connection:
        return connection.execute(table.select().where(*conditions)).fetchall()


def test_manual_credit_grant_late_failure_persists_nothing(
    app: object, monkeypatch: object
) -> None:
    creator_bid = uuid.uuid4().hex[:32]

    def failing_snapshot(*_args: object, **_kwargs: object) -> None:
        message = "snapshot boom"
        raise RuntimeError(message)

    monkeypatch.setattr(wallets, "persist_credit_wallet_snapshot", failing_snapshot)

    with app.app_context(), pytest.raises(RuntimeError, match="snapshot boom"):
        wallets.grant_manual_credit_wallet_balance(
            app,
            creator_bid=creator_bid,
            amount=Decimal(5),
            source_bid=f"grant-{creator_bid[:8]}",
        )

    assert (
        _committed_rows(
            app,
            CreditWalletBucket.__table__,
            CreditWalletBucket.creator_bid == creator_bid,
        )
        == []
    )
    assert (
        _committed_rows(
            app,
            CreditLedgerEntry.__table__,
            CreditLedgerEntry.creator_bid == creator_bid,
        )
        == []
    )


def test_manual_credit_grant_commits_bucket_and_ledger_together(app: object) -> None:
    creator_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        result = wallets.grant_manual_credit_wallet_balance(
            app,
            creator_bid=creator_bid,
            amount=Decimal(5),
            source_bid=f"grant-{creator_bid[:8]}",
        )
    assert result["status"] == "granted"
    buckets = _committed_rows(
        app, CreditWalletBucket.__table__, CreditWalletBucket.creator_bid == creator_bid
    )
    ledgers = _committed_rows(
        app, CreditLedgerEntry.__table__, CreditLedgerEntry.creator_bid == creator_bid
    )
    assert len(buckets) == 1
    assert len(ledgers) == 1


def test_trial_bootstrap_enqueues_notification_only_after_commit(
    app: object, monkeypatch: object
) -> None:
    creator_bid = uuid.uuid4().hex[:32]
    seen: list[str] = []
    monkeypatch.setattr(
        trials,
        "_resolve_trial_bootstrap_status",
        lambda *_a, **_k: ("grantable", {"product_bid": "trial"}),
    )
    monkeypatch.setattr(trials, "_bootstrap_trial_subscription", lambda *_a, **_k: None)
    monkeypatch.setattr(
        trials,
        "_enqueue_trial_credit_notification",
        lambda _app, bid: seen.append(bid),
    )

    # Failure inside the unit of work: nothing is enqueued.
    def failing_bootstrap(*_args: object, **_kwargs: object) -> None:
        message = "bootstrap boom"
        raise RuntimeError(message)

    monkeypatch.setattr(trials, "_bootstrap_trial_subscription", failing_bootstrap)
    with app.app_context(), pytest.raises(RuntimeError, match="bootstrap boom"):
        trials._bootstrap_new_creator_trial_credits(app, creator_bid)
    assert seen == []

    # Clean run: the notification is enqueued exactly once, after the commit.
    monkeypatch.setattr(trials, "_bootstrap_trial_subscription", lambda *_a, **_k: None)
    with app.app_context():
        trials._bootstrap_new_creator_trial_credits(app, creator_bid)
    assert seen == [creator_bid]


def test_campaign_create_late_failure_persists_no_campaign(
    app: object, monkeypatch: object
) -> None:
    name = f"UoW campaign {uuid.uuid4().hex[:6]}"
    product_bid = uuid.uuid4().hex
    written_campaigns: list[str] = []
    replace_products = campaigns._replace_campaign_products

    def failing_products(campaign_bid: str, products: object) -> None:
        replace_products(campaign_bid, products)
        dao.db.session.flush()
        assert BillingCampaign.query.filter_by(campaign_bid=campaign_bid).count() == 1
        assert (
            BillingCampaignProduct.query.filter_by(campaign_bid=campaign_bid).count()
            == 1
        )
        written_campaigns.append(campaign_bid)
        message = "products boom"
        raise RuntimeError(message)

    monkeypatch.setattr(campaigns, "_replace_campaign_products", failing_products)
    payload = {
        "name": name,
        "note": "",
        "benefit_type": "discount",
        "products": [
            {
                "product_bid": product_bid,
                "discount_type": "fixed",
                "campaign_price_amount": 500,
            }
        ],
        "start_at": "2026-01-01 00:00:00",
        "end_at": "2026-12-31 23:59:59",
        "enabled": False,
    }
    with app.app_context():
        dao.db.session.add(
            build_billing_product(
                "bill-product-plan-monthly",
                overrides={"product_bid": product_bid, "product_code": product_bid},
            )
        )
        dao.db.session.commit()
        with pytest.raises(RuntimeError, match="products boom"):
            campaigns.create_admin_billing_campaign(
                app, operator_user_bid="op", payload=payload
            )

    assert len(written_campaigns) == 1
    assert (
        _committed_rows(app, BillingCampaign.__table__, BillingCampaign.name == name)
        == []
    )
    assert (
        _committed_rows(
            app,
            BillingCampaignProduct.__table__,
            BillingCampaignProduct.campaign_bid == written_campaigns[0],
        )
        == []
    )

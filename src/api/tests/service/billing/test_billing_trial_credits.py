from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from flask import Flask, jsonify, request
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_TRIAL_PRODUCT_BID,
    BILLING_TRIAL_PRODUCT_CODE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.trials import bootstrap_new_creator_trial_credits
from flaskr.service.common.models import AppException
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.repository import create_user_entity
from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing.route_loader import (
    load_billing_routes_module,
    load_register_billing_routes,
)

billing_routes_module = load_billing_routes_module()
register_billing_routes = load_register_billing_routes()


def _seed_creator(*, user_bid: str, is_creator: bool = True) -> None:
    entity = create_user_entity(
        user_bid=user_bid,
        identify=f"{user_bid}@example.com",
        nickname="Creator",
        language="en-US",
        avatar="",
        state=USER_STATE_REGISTERED,
    )
    entity.is_creator = 1 if is_creator else 0
    dao.db.session.commit()


@pytest.fixture
def trial_billing_client(monkeypatch):
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )

    dao.db.init_app(app)

    @app.errorhandler(AppException)
    def _handle_app_exception(error: AppException):
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(
            user_id=request.headers.get("X-User-Id", "creator-trial"),
            language="en-US",
            is_creator=request.headers.get("X-Creator", "1") == "1",
        )

    monkeypatch.setattr(
        billing_routes_module,
        "is_billing_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.trials._is_billing_enabled",
        lambda: True,
    )

    register_billing_routes(app=app)

    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()

    return app.test_client()


def test_billing_overview_returns_product_backed_eligible_trial_without_mutation(
    trial_billing_client,
) -> None:
    app = trial_billing_client.application
    with app.app_context():
        _seed_creator(user_bid="creator-trial")

    first_payload = trial_billing_client.get("/api/billing/overview").get_json(
        force=True
    )
    second_payload = trial_billing_client.get("/api/billing/overview").get_json(
        force=True
    )

    for payload in (first_payload, second_payload):
        assert payload["code"] == 0
        assert payload["data"]["wallet"]["available_credits"] == 0
        assert payload["data"]["trial_offer"] == {
            "enabled": True,
            "status": "eligible",
            "product_bid": BILLING_TRIAL_PRODUCT_BID,
            "product_code": BILLING_TRIAL_PRODUCT_CODE,
            "display_name": "module.billing.package.free.title",
            "description": "module.billing.package.free.description",
            "currency": "CNY",
            "price_amount": 0,
            "credit_amount": 100,
            "highlights": [
                "module.billing.package.features.free.publish",
                "module.billing.package.features.free.preview",
            ],
            "valid_days": 15,
            "starts_on_first_grant": True,
            "granted_at": None,
            "expires_at": None,
            "welcome_dialog_acknowledged_at": None,
        }

    with app.app_context():
        assert CreditWallet.query.filter_by(creator_bid="creator-trial").count() == 0
        assert (
            CreditWalletBucket.query.filter_by(creator_bid="creator-trial").count() == 0
        )
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid="creator-trial").count() == 0
        )


def test_trial_bootstrap_creates_manual_order_subscription_and_expire_event_once(
    trial_billing_client,
) -> None:
    app = trial_billing_client.application
    with app.app_context():
        _seed_creator(user_bid="creator-trial")
        bootstrap_new_creator_trial_credits(app, "creator-trial")
        bootstrap_new_creator_trial_credits(app, "creator-trial")

        wallet = CreditWallet.query.filter_by(creator_bid="creator-trial").one()
        bucket = CreditWalletBucket.query.filter_by(creator_bid="creator-trial").one()
        ledger = CreditLedgerEntry.query.filter_by(creator_bid="creator-trial").one()
        order = BillingOrder.query.filter_by(creator_bid="creator-trial").one()
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-trial"
        ).one()
        renewal_event = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        ).one()

        assert wallet.available_credits == Decimal("100.0000000000")
        assert wallet.lifetime_granted_credits == Decimal("100.0000000000")

        assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
        assert bucket.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
        assert bucket.source_bid == order.bill_order_bid
        assert bucket.available_credits == Decimal("100.0000000000")

        assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT
        assert ledger.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
        assert ledger.source_bid == order.bill_order_bid
        assert ledger.idempotency_key == f"grant:{order.bill_order_bid}"

        assert order.product_bid == BILLING_TRIAL_PRODUCT_BID
        assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START
        assert order.payment_provider == "manual"
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert order.payable_amount == 0
        assert order.paid_amount == 0
        assert order.paid_at is not None

        assert subscription.product_bid == BILLING_TRIAL_PRODUCT_BID
        assert subscription.billing_provider == "manual"
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert subscription.current_period_start_at == order.paid_at
        assert subscription.current_period_end_at is not None
        assert (
            subscription.current_period_end_at - subscription.current_period_start_at
            == timedelta(days=15)
        )

        assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
        assert renewal_event.scheduled_at == subscription.current_period_end_at


def test_billing_overview_returns_granted_for_bootstrapped_trial_subscription(
    trial_billing_client,
) -> None:
    app = trial_billing_client.application
    with app.app_context():
        _seed_creator(user_bid="creator-trial")
        bootstrap_new_creator_trial_credits(app, "creator-trial")

    payload = trial_billing_client.get("/api/billing/overview").get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["subscription"]["product_bid"] == BILLING_TRIAL_PRODUCT_BID
    assert payload["data"]["subscription"]["billing_provider"] == "manual"
    assert payload["data"]["trial_offer"]["status"] == "granted"
    assert payload["data"]["trial_offer"]["product_code"] == BILLING_TRIAL_PRODUCT_CODE
    assert payload["data"]["trial_offer"]["granted_at"] is not None
    assert payload["data"]["trial_offer"]["expires_at"] is not None
    assert payload["data"]["trial_offer"]["welcome_dialog_acknowledged_at"] is None


def test_trial_bootstrap_skips_grant_when_billing_disabled(
    trial_billing_client,
    monkeypatch,
) -> None:
    app = trial_billing_client.application
    with app.app_context():
        _seed_creator(user_bid="creator-trial-disabled")

    monkeypatch.setattr(
        "flaskr.service.billing.trials._is_billing_enabled", lambda: False
    )

    with app.app_context():
        bootstrap_new_creator_trial_credits(app, "creator-trial-disabled")

        assert (
            CreditWallet.query.filter_by(
                creator_bid="creator-trial-disabled",
                deleted=0,
            ).count()
            == 0
        )
        assert (
            BillingOrder.query.filter_by(
                creator_bid="creator-trial-disabled",
                deleted=0,
            ).count()
            == 0
        )


def test_legacy_trial_ledger_marks_offer_granted_and_blocks_new_bootstrap(
    trial_billing_client,
) -> None:
    app = trial_billing_client.application
    granted_at = datetime(2026, 4, 9, 12, 0, 0)
    expires_at = granted_at + timedelta(days=15)

    with app.app_context():
        _seed_creator(user_bid="creator-trial")
        wallet = CreditWallet(
            wallet_bid="wallet-legacy-trial",
            creator_bid="creator-trial",
            available_credits=Decimal("100.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("100.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.flush()
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-legacy-trial",
                creator_bid="creator-trial",
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_GIFT,
                source_bid=BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
                idempotency_key=(
                    "trial:"
                    f"{BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE}:creator-trial"
                ),
                amount=Decimal("100.0000000000"),
                balance_after=Decimal("100.0000000000"),
                expires_at=expires_at,
                consumable_from=granted_at,
                metadata_json={
                    "trial_program": BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE
                },
                created_at=granted_at,
                updated_at=granted_at,
            )
        )
        dao.db.session.commit()

        bootstrap_new_creator_trial_credits(app, "creator-trial")

    payload = trial_billing_client.get("/api/billing/overview").get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["trial_offer"]["status"] == "granted"
    assert payload["data"]["trial_offer"]["granted_at"] is not None
    assert payload["data"]["trial_offer"]["expires_at"] is not None
    assert payload["data"]["trial_offer"]["welcome_dialog_acknowledged_at"] is None

    with app.app_context():
        assert BillingOrder.query.filter_by(creator_bid="creator-trial").count() == 0
        assert (
            BillingSubscription.query.filter_by(creator_bid="creator-trial").count()
            == 0
        )


def test_trial_welcome_ack_route_writes_subscription_metadata_and_is_idempotent(
    trial_billing_client,
) -> None:
    app = trial_billing_client.application
    with app.app_context():
        _seed_creator(user_bid="creator-trial")
        bootstrap_new_creator_trial_credits(app, "creator-trial")

    first_payload = trial_billing_client.post(
        "/api/billing/trial-offer/welcome/ack"
    ).get_json(force=True)
    second_payload = trial_billing_client.post(
        "/api/billing/trial-offer/welcome/ack"
    ).get_json(force=True)
    overview_payload = trial_billing_client.get("/api/billing/overview").get_json(
        force=True
    )

    assert first_payload["code"] == 0
    assert first_payload["data"]["acknowledged"] is True
    assert first_payload["data"]["acknowledged_at"] is not None
    assert second_payload["code"] == 0
    assert second_payload["data"]["acknowledged"] is True
    assert (
        second_payload["data"]["acknowledged_at"]
        == first_payload["data"]["acknowledged_at"]
    )
    assert (
        overview_payload["data"]["trial_offer"]["welcome_dialog_acknowledged_at"]
        == first_payload["data"]["acknowledged_at"]
    )

    with app.app_context():
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-trial"
        ).one()
        assert (
            subscription.metadata_json["welcome_trial_dialog_acknowledged_at"]
            is not None
        )


def test_trial_welcome_ack_route_falls_back_to_order_metadata(
    trial_billing_client,
) -> None:
    app = trial_billing_client.application
    with app.app_context():
        _seed_creator(user_bid="creator-trial")
        paid_at = datetime(2026, 4, 9, 12, 0, 0)
        dao.db.session.add(
            BillingOrder(
                bill_order_bid="bill-trial-order-only",
                creator_bid="creator-trial",
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
                paid_at=paid_at,
                metadata_json={},
            )
        )
        dao.db.session.commit()

    payload = trial_billing_client.post(
        "/api/billing/trial-offer/welcome/ack"
    ).get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["acknowledged"] is True
    assert payload["data"]["acknowledged_at"] is not None

    with app.app_context():
        order = BillingOrder.query.filter_by(
            creator_bid="creator-trial",
            bill_order_bid="bill-trial-order-only",
        ).one()
        assert order.metadata_json["welcome_trial_dialog_acknowledged_at"] is not None


def test_trial_welcome_ack_route_falls_back_to_legacy_trial_ledger_metadata(
    trial_billing_client,
) -> None:
    app = trial_billing_client.application
    granted_at = datetime(2026, 4, 9, 12, 0, 0)
    expires_at = granted_at + timedelta(days=15)

    with app.app_context():
        _seed_creator(user_bid="creator-trial")
        wallet = CreditWallet(
            wallet_bid="wallet-legacy-ack",
            creator_bid="creator-trial",
            available_credits=Decimal("100.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("100.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.flush()
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-legacy-ack",
                creator_bid="creator-trial",
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_GIFT,
                source_bid=BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
                idempotency_key=(
                    "trial:"
                    f"{BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE}:creator-trial"
                ),
                amount=Decimal("100.0000000000"),
                balance_after=Decimal("100.0000000000"),
                expires_at=expires_at,
                consumable_from=granted_at,
                metadata_json={},
                created_at=granted_at,
                updated_at=granted_at,
            )
        )
        dao.db.session.commit()

    payload = trial_billing_client.post(
        "/api/billing/trial-offer/welcome/ack"
    ).get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"]["acknowledged"] is True
    assert payload["data"]["acknowledged_at"] is not None

    with app.app_context():
        ledger = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-trial",
            ledger_bid="ledger-legacy-ack",
        ).one()
        assert ledger.metadata_json["welcome_trial_dialog_acknowledged_at"] is not None


def test_trial_welcome_ack_route_returns_false_without_granted_trial(
    trial_billing_client,
) -> None:
    app = trial_billing_client.application
    with app.app_context():
        _seed_creator(user_bid="creator-trial")

    payload = trial_billing_client.post(
        "/api/billing/trial-offer/welcome/ack"
    ).get_json(force=True)

    assert payload["code"] == 0
    assert payload["data"] == {
        "acknowledged": False,
        "acknowledged_at": None,
    }

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace
import types

from flask import Flask, jsonify, request
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_PRODUCT_SEEDS,
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
    BillingProduct,
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

_API_ROOT = Path(__file__).resolve().parents[3]
_ROUTE_DIR = _API_ROOT / "flaskr" / "route"
_BILLING_ROUTE_FILE = _API_ROOT / "flaskr" / "service" / "billing" / "routes.py"


def _load_register_billing_routes():
    package_name = "flaskr.route"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(_ROUTE_DIR)]
        sys.modules[package_name] = package

    common_name = f"{package_name}.common"
    if common_name not in sys.modules:
        common_spec = importlib.util.spec_from_file_location(
            common_name,
            _ROUTE_DIR / "common.py",
        )
        assert common_spec is not None and common_spec.loader is not None
        common_module = importlib.util.module_from_spec(common_spec)
        sys.modules[common_name] = common_module
        common_spec.loader.exec_module(common_module)

    full_name = "flaskr.service.billing.routes"
    if full_name in sys.modules:
        return sys.modules[full_name].register_billing_routes

    spec = importlib.util.spec_from_file_location(full_name, _BILLING_ROUTE_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module.register_billing_routes


register_billing_routes = _load_register_billing_routes()


def _seed_products() -> list[BillingProduct]:
    items: list[BillingProduct] = []
    for seed in BILLING_PRODUCT_SEEDS:
        payload = dict(seed)
        payload["metadata_json"] = payload.pop("metadata", None)
        items.append(BillingProduct(**payload))
    return items


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
def trial_billing_client():
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

    register_billing_routes(app=app)

    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(_seed_products())
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
        assert bucket.source_bid == order.billing_order_bid
        assert bucket.available_credits == Decimal("100.0000000000")

        assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT
        assert ledger.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
        assert ledger.source_bid == order.billing_order_bid
        assert ledger.idempotency_key == f"grant:{order.billing_order_bid}"

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

    with app.app_context():
        assert BillingOrder.query.filter_by(creator_bid="creator-trial").count() == 0
        assert (
            BillingSubscription.query.filter_by(creator_bid="creator-trial").count()
            == 0
        )

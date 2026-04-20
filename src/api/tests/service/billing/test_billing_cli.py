from __future__ import annotations

import json

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import BILL_SYS_CONFIG_SEEDS, CREDIT_USAGE_RATE_SEEDS
from flaskr.service.billing.cli import register_billing_commands
from flaskr.service.billing.models import BillingProduct, CreditUsageRate
from flaskr.service.config.models import Config


@pytest.fixture
def billing_cli_runner():
    app = Flask(__name__)
    app.testing = True

    @app.cli.group()
    def console():
        """Test console root."""

    register_billing_commands(console)
    return app.test_cli_runner()


@pytest.fixture
def billing_cli_db_app():
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
        SECRET_KEY="billing-cli-test-secret",
        REDIS_KEY_PREFIX="billing-cli-test:",
    )
    dao.db.init_app(app)

    @app.cli.group()
    def console():
        """Test console root."""

    register_billing_commands(console)

    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_billing_backfill_settlement_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "backfill-settlement"]
    )

    assert result.exit_code != 0
    assert "Pass --usage-bid, a usage id range, or --all" in result.output


def test_billing_backfill_settlement_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.backfill_bill_usage_settlement",
        lambda app, **kwargs: {
            "status": "completed",
            "processed_count": 2,
            "backfill": True,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "backfill-settlement",
            "--usage-id-start",
            "10",
            "--usage-id-end",
            "12",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "completed"
    assert payload["processed_count"] == 2
    assert payload["kwargs"]["usage_id_start"] == 10
    assert payload["kwargs"]["usage_id_end"] == 12


def test_billing_rebuild_wallets_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.rebuild_credit_wallet_snapshots",
        lambda app, **kwargs: {
            "status": "rebuilt",
            "wallet_count": 1,
            "wallets": [{"wallet_bid": "wallet-1"}],
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "rebuild-wallets",
            "--creator-bid",
            "creator-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "rebuilt"
    assert payload["kwargs"]["creator_bid"] == "creator-cli-1"


def test_billing_repair_topup_expiry_cli_requires_creator_bid(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "repair-topup-expiry"]
    )

    assert result.exit_code != 0
    assert "Pass --creator-bid for topup expiry repair." in result.output


def test_billing_repair_topup_expiry_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.repair_topup_grant_expiries",
        lambda app, **kwargs: {
            "status": "repaired",
            "repaired_bucket_count": 1,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "repair-topup-expiry",
            "--creator-bid",
            "creator-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "repaired"
    assert payload["kwargs"]["creator_bid"] == "creator-cli-1"


def test_billing_repair_subscription_cycle_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "repair-subscription-cycle"]
    )

    assert result.exit_code != 0
    assert (
        "Pass --creator-bid or --subscription-bid for subscription cycle repair."
        in result.output
    )


def test_billing_repair_subscription_cycle_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.repair_subscription_cycle_mismatches",
        lambda app, **kwargs: {
            "status": "repaired",
            "repaired_subscription_count": 1,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "repair-subscription-cycle",
            "--creator-bid",
            "creator-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "repaired"
    assert payload["kwargs"]["creator_bid"] == "creator-cli-1"


def test_billing_reconcile_order_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.reconcile_billing_provider_reference",
        lambda app, **kwargs: {
            "status": "paid",
            "bill_order_bid": "bill-order-cli-1",
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "reconcile-order",
            "--bill-order-bid",
            "bill-order-cli-1",
            "--payment-provider",
            "stripe",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "paid"
    assert payload["kwargs"]["payment_provider"] == "stripe"


def test_billing_retry_renewal_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.retry_billing_renewal_event",
        lambda app, **kwargs: {
            "status": "applied",
            "renewal_event_bid": kwargs.get("renewal_event_bid"),
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "retry-renewal",
            "--renewal-event-bid",
            "renewal-event-cli-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "applied"
    assert payload["renewal_event_bid"] == "renewal-event-cli-1"


def test_billing_requeue_subscription_purchase_sms_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.requeue_subscription_purchase_sms",
        lambda app, **kwargs: {
            "status": "enqueued",
            "bill_order_bid": kwargs.get("bill_order_bid"),
            "enqueued": True,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "requeue-subscription-purchase-sms",
            "--bill-order-bid",
            "bill-order-cli-sms-1",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "enqueued"
    assert payload["bill_order_bid"] == "bill-order-cli-sms-1"
    assert payload["enqueued"] is True


def test_billing_rebuild_daily_aggregates_cli_requires_explicit_scope(
    billing_cli_runner,
) -> None:
    result = billing_cli_runner.invoke(
        args=["console", "billing", "rebuild-daily-aggregates"]
    )

    assert result.exit_code != 0
    assert "Pass --date-from/--date-to or --all" in result.output


def test_billing_rebuild_daily_aggregates_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.rebuild_daily_aggregates",
        lambda app, **kwargs: {
            "status": "rebuilt",
            "day_count": 3,
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "rebuild-daily-aggregates",
            "--creator-bid",
            "creator-cli-1",
            "--shifu-bid",
            "shifu-cli-1",
            "--date-from",
            "2026-04-08",
            "--date-to",
            "2026-04-10",
        ]
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "rebuilt"
    assert payload["day_count"] == 3
    assert payload["kwargs"]["creator_bid"] == "creator-cli-1"
    assert payload["kwargs"]["shifu_bid"] == "shifu-cli-1"
    assert payload["kwargs"]["date_from"] == "2026-04-08"
    assert payload["kwargs"]["date_to"] == "2026-04-10"


def test_billing_seed_bootstrap_data_cli_is_idempotent(
    billing_cli_db_app: Flask,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()

    first_result = runner.invoke(args=["console", "billing", "seed-bootstrap-data"])
    second_result = runner.invoke(args=["console", "billing", "seed-bootstrap-data"])

    first_payload = json.loads(first_result.output)
    second_payload = json.loads(second_result.output)

    assert first_result.exit_code == 0
    assert second_result.exit_code == 0
    assert first_payload["rates"]["inserted"] == len(CREDIT_USAGE_RATE_SEEDS)
    assert first_payload["configs"]["inserted"] == len(BILL_SYS_CONFIG_SEEDS)
    assert second_payload["rates"]["updated"] == len(CREDIT_USAGE_RATE_SEEDS)
    assert second_payload["configs"]["updated"] == len(BILL_SYS_CONFIG_SEEDS)
    assert second_payload["products"]["count"] == 0

    with billing_cli_db_app.app_context():
        assert CreditUsageRate.query.count() == len(CREDIT_USAGE_RATE_SEEDS)
        assert Config.query.count() == len(BILL_SYS_CONFIG_SEEDS)


def test_billing_upsert_product_cli_allows_manual_custom_product_values(
    billing_cli_db_app: Flask,
) -> None:
    runner = billing_cli_db_app.test_cli_runner()
    base_args = [
        "console",
        "billing",
        "upsert-product",
        "--product-bid",
        "bill-product-custom-cli",
        "--product-code",
        "creator-custom-cli",
        "--product-type",
        "custom",
        "--billing-mode",
        "manual",
        "--billing-interval",
        "none",
        "--billing-interval-count",
        "0",
        "--display-name-i18n-key",
        "module.billing.catalog.custom.cli.title",
        "--description-i18n-key",
        "module.billing.catalog.custom.cli.description",
        "--currency",
        "usd",
        "--price-amount",
        "2599",
        "--credit-amount",
        "42.5000000000",
        "--allocation-interval",
        "manual",
        "--auto-renew-enabled",
        "0",
        "--status",
        "active",
        "--sort-order",
        "120",
        "--entitlement-json",
        '{"support_tier":"priority"}',
        "--metadata-json",
        '{"badge":"launch"}',
    ]

    first_result = runner.invoke(args=base_args)
    second_result = runner.invoke(
        args=[
            *base_args[:-2],
            "--metadata-json",
            '{"badge":"updated","segment":"enterprise"}',
        ]
    )

    first_payload = json.loads(first_result.output)
    second_payload = json.loads(second_result.output)

    assert first_result.exit_code == 0
    assert second_result.exit_code == 0
    assert first_payload["created"] is True
    assert second_payload["created"] is False
    assert second_payload["product_bid"] == "bill-product-custom-cli"

    with billing_cli_db_app.app_context():
        product = BillingProduct.query.filter_by(
            product_bid="bill-product-custom-cli"
        ).one()
        assert product.product_code == "creator-custom-cli"
        assert product.currency == "USD"
        assert product.price_amount == 2599
        assert str(product.credit_amount) == "42.5000000000"
        assert product.metadata_json == {
            "badge": "updated",
            "segment": "enterprise",
        }
        assert product.entitlement_payload == {"support_tier": "priority"}

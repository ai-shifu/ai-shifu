from __future__ import annotations

import json

from flask import Flask
import pytest

from flaskr.service.billing.cli import register_billing_commands


@pytest.fixture
def billing_cli_runner():
    app = Flask(__name__)
    app.testing = True

    @app.cli.group()
    def console():
        """Test console root."""

    register_billing_commands(console)
    return app.test_cli_runner()


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


def test_billing_reconcile_order_cli_prints_helper_payload(
    billing_cli_runner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.cli.reconcile_billing_provider_reference",
        lambda app, **kwargs: {
            "status": "paid",
            "billing_order_bid": "billing-order-cli-1",
            "kwargs": kwargs,
        },
    )

    result = billing_cli_runner.invoke(
        args=[
            "console",
            "billing",
            "reconcile-order",
            "--billing-order-bid",
            "billing-order-cli-1",
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

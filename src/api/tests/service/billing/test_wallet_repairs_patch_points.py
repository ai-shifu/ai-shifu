"""Verify wallet repair flows keep honoring patches applied to ``wallets``."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import flaskr.service.billing.wallets as wallets_module
from flaskr import dao
from flaskr.service.billing.consts import BILLING_SUBSCRIPTION_STATUS_ACTIVE
from flaskr.service.billing.models import BillingSubscription
from flaskr.service.billing.wallets import repair_renewal_state_drift

if TYPE_CHECKING:
    import pytest
    from flask import Flask

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


def test_repair_renewal_state_drift_reads_patched_wallets_now_utc(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The cycle ends far in the future, so only the patched clock makes it stale.
    period_end_at = datetime(2098, 1, 1, 0, 0, 0)
    patched_now = datetime(2098, 1, 2, 0, 0, 0)
    clock_calls: list[datetime] = []

    def patched_now_utc() -> datetime:
        clock_calls.append(patched_now)
        return patched_now

    with billing_wallet_lifecycle_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="subscription-patched-clock",
            creator_bid="creator-patched-clock",
            product_bid="bill-product-patched-clock",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2097, 12, 1, 0, 0, 0),
            current_period_end_at=period_end_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.commit()
        monkeypatch.setattr(wallets_module, "now_utc", patched_now_utc)

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid="creator-patched-clock",
            dry_run=True,
        )

    assert clock_calls
    assert payload["status"] == "dry_run"
    assert payload["creator_count"] == 1
    assert payload["stale_subscription_count"] == 1

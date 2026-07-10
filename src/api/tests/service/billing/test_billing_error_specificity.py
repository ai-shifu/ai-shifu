from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

import flaskr.service.billing.checkout as checkout_module
import flaskr.service.billing.credit_notifications as credit_notifications_module
import flaskr.service.billing.manual_credit_grants as manual_credit_grants_module
import flaskr.service.billing.manual_plan_grants as manual_plan_grants_module
from flaskr.service.billing.credit_notifications import save_credit_notification_policy
from flaskr.service.billing.manual_credit_grants import (
    MANUAL_CREDIT_GRANT_SOURCE_REWARD,
    MANUAL_CREDIT_VALIDITY_1D,
    grant_manual_credits_to_user,
)
from flaskr.service.billing.manual_plan_grants import grant_manual_plan_to_user
from flaskr.service.common.models import AppException, ERROR_CODE


class _UnavailableLock:
    def acquire(self, blocking: bool = True) -> bool:
        assert blocking is True
        return False

    def release(self) -> None:  # pragma: no cover - should not be called
        raise AssertionError("unacquired lock should not be released")


class _LockFactory:
    def lock(self, *_args, **_kwargs):
        return _UnavailableLock()


def test_subscription_checkout_lock_conflict_returns_busy_error(app, monkeypatch):
    monkeypatch.setattr(checkout_module.cache_provider, "cache", _LockFactory())

    with app.app_context(), pytest.raises(AppException) as exc_info:
        with checkout_module._subscription_checkout_lock(app, "creator-busy"):
            raise AssertionError("lock body should not execute")

    assert exc_info.value.code == ERROR_CODE["server.billing.subscriptionCheckoutBusy"]


def test_manual_plan_grant_lock_conflict_returns_busy_error(app, monkeypatch):
    monkeypatch.setattr(manual_plan_grants_module.redis, "lock", _LockFactory().lock)

    with pytest.raises(AppException) as exc_info:
        grant_manual_plan_to_user(
            app,
            user_bid="creator-busy",
            product_bid="bill-product-plan-monthly",
            operator_user_bid="operator-1",
            request_id="request-busy",
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.manualPlanGrantBusy"]


def test_manual_credit_grant_failure_returns_specific_error(app, monkeypatch):
    monkeypatch.setattr(
        manual_credit_grants_module,
        "grant_manual_credit_wallet_balance",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="failed",
            ledger_bid="",
            metadata_json={},
            amount=Decimal("0"),
        ),
    )

    with pytest.raises(AppException) as exc_info:
        grant_manual_credits_to_user(
            app,
            user_bid="creator-credit-failed",
            operator_user_bid="operator-1",
            request_id="request-credit-failed",
            amount="10",
            grant_source=MANUAL_CREDIT_GRANT_SOURCE_REWARD,
            validity_preset=MANUAL_CREDIT_VALIDITY_1D,
            display_name="Manual credit",
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.manualCreditGrantFailed"]


def test_credit_notification_policy_save_failure_returns_specific_error(app, monkeypatch):
    monkeypatch.setattr(credit_notifications_module, "add_config", lambda *_, **__: False)

    with pytest.raises(AppException) as exc_info:
        save_credit_notification_policy(
            app,
            {"enabled": False, "types": {}},
            updated_by="operator-1",
        )

    assert (
        exc_info.value.code
        == ERROR_CODE["server.billing.notificationPolicySaveFailed"]
    )

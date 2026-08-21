"""Verify billing error specificity behavior."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Never

import flaskr.service.billing.checkout as checkout_module
import flaskr.service.billing.credit_notifications as credit_notifications_module
import flaskr.service.billing.manual_credit_grants as manual_credit_grants_module
import flaskr.service.billing.manual_plan_grants as manual_plan_grants_module
import pytest
from flaskr.service.billing.credit_notifications import save_credit_notification_policy
from flaskr.service.billing.manual_credit_grants import (
    MANUAL_CREDIT_GRANT_SOURCE_REWARD,
    MANUAL_CREDIT_VALIDITY_1D,
    grant_manual_credits_to_user,
)
from flaskr.service.billing.manual_plan_grants import grant_manual_plan_to_user
from flaskr.service.common.models import ERROR_CODE, AppError


class _UnavailableLock:
    def acquire(self, blocking: bool = True) -> bool:
        assert blocking is True
        return False

    def release(self) -> None:  # pragma: no cover - should not be called
        message = "unacquired lock should not be released"
        raise AssertionError(message)


class _LockFactory:
    def lock(self, *_args: object, **_kwargs: object) -> object:
        return _UnavailableLock()


def test_subscription_checkout_lock_conflict_returns_busy_error(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> Never:
    monkeypatch.setattr(checkout_module.cache_provider, "cache", _LockFactory())

    message = "lock body should not execute"
    with (
        app.app_context(),
        pytest.raises(AppError) as exc_info,
        checkout_module._subscription_checkout_lock(app, "creator-busy"),
    ):
        raise AssertionError(message)

    assert exc_info.value.code == ERROR_CODE["server.billing.subscriptionCheckoutBusy"]


def test_manual_plan_grant_lock_conflict_returns_busy_error(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(manual_plan_grants_module.redis, "lock", _LockFactory().lock)

    with pytest.raises(AppError) as exc_info:
        grant_manual_plan_to_user(
            app,
            user_bid="creator-busy",
            product_bid="bill-product-plan-monthly",
            operator_user_bid="operator-1",
            request_id="request-busy",
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.manualPlanGrantBusy"]


def test_manual_credit_grant_failure_returns_specific_error(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        manual_credit_grants_module,
        "grant_manual_credit_wallet_balance",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="failed",
            ledger_bid="",
            metadata_json={},
            amount=Decimal(0),
        ),
    )

    with pytest.raises(AppError) as exc_info:
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


def test_credit_notification_policy_save_failure_returns_specific_error(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        credit_notifications_module, "add_config", lambda *_, **__: False
    )

    with pytest.raises(AppError) as exc_info:
        save_credit_notification_policy(
            app,
            {"enabled": False, "types": {}},
            updated_by="operator-1",
        )

    assert (
        exc_info.value.code == ERROR_CODE["server.billing.notificationPolicySaveFailed"]
    )

"""Tests for one-time billing cache compensation scripts."""

from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Self

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import grant_cache_overcharge_bonus_plan as bonus_plan  # noqa: E402
from billing_cache_compensation_common import (  # noqa: E402
    AMOUNT_HEADER,
    DEFAULT_SHEET_NAME,
    USER_BID_HEADER,
    load_reference_rows,
)
from flaskr.service.billing.consts import (  # noqa: E402
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
)
from flaskr.service.billing.manual_credit_grants import (  # noqa: E402
    MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
    MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
)
from flaskr.service.billing.models import (  # noqa: E402
    BillingOrder,
    BillingProduct,
    CreditLedgerEntry,
)
from grant_cache_overcharge_bonus_plan import (  # noqa: E402
    _CHECKOUT_TYPE,
    _MANUAL_PROVIDER_NAME,
    _compare_existing_bonus_order,
    _provider_reference,
)
from grant_cache_overcharge_credit_compensation import (  # noqa: E402
    _compare_existing_credit_grant,
)


class _FakeApp:
    def app_context(self) -> Self:
        return self

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_reference_loader_rejects_duplicate_user_bid(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        f"{USER_BID_HEADER},{AMOUNT_HEADER}\nuser-a,100\nuser-a,50\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate user_bid"):
        load_reference_rows(str(csv_path), sheet_name=DEFAULT_SHEET_NAME)


def test_reference_loader_accepts_standard_thousands_amount(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        f'{USER_BID_HEADER},{AMOUNT_HEADER}\nuser-a,"1,234.56"\n',
        encoding="utf-8",
    )

    rows = load_reference_rows(str(csv_path), sheet_name=DEFAULT_SHEET_NAME)

    assert rows[0].amount == Decimal("1234.56")


def test_reference_loader_rejects_invalid_amount(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        f"{USER_BID_HEADER},{AMOUNT_HEADER}\nuser-a,not-a-number\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid credit amount"):
        load_reference_rows(str(csv_path), sheet_name=DEFAULT_SHEET_NAME)


def test_existing_credit_grant_reports_amount_mismatch() -> None:
    row = type(
        "Row",
        (),
        {"user_bid": "user-a", "amount": Decimal("150.00")},
    )()
    ledger = CreditLedgerEntry(
        creator_bid="user-a",
        amount=Decimal("100.00"),
        idempotency_key="operator_manual_grant:batch:credit:user-a",
        expires_at=datetime(2026, 9, 1, 0, 0, 0),
        metadata_json={
            "grant_source": MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
            "validity_preset": MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
        },
    )

    mismatch = _compare_existing_credit_grant(
        ledger,
        row=row,
        request_id="batch:credit:user-a",
    )

    assert "amount" in mismatch


def test_existing_credit_grant_uses_stored_period_end_after_renewal() -> None:
    row = type(
        "Row",
        (),
        {"user_bid": "user-a", "amount": Decimal("100.00")},
    )()
    ledger = CreditLedgerEntry(
        creator_bid="user-a",
        amount=Decimal("100.00"),
        idempotency_key="operator_manual_grant:batch:credit:user-a",
        expires_at=datetime(2026, 9, 1, 0, 0, 0),
        metadata_json={
            "grant_source": MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
            "validity_preset": MANUAL_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
            "compensation_period_end_at": "2026-09-01T00:00:00Z",
        },
    )

    mismatch = _compare_existing_credit_grant(
        ledger,
        row=row,
        request_id="batch:credit:user-a",
    )

    assert "expires_at" not in mismatch


def test_existing_bonus_order_reports_product_mismatch() -> None:
    product = BillingProduct(product_bid="target-product")
    order = BillingOrder(
        creator_bid="user-a",
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        product_bid="wrong-product",
        subscription_bid="subscription-a",
        payment_provider=_MANUAL_PROVIDER_NAME,
        channel=_MANUAL_PROVIDER_NAME,
        provider_reference_id=_provider_reference("batch:bonus-plan:user-a"),
        status=BILLING_ORDER_STATUS_PAID,
        metadata_json={
            "checkout_type": _CHECKOUT_TYPE,
            "campaign_id": "batch",
            "request_id": "batch:bonus-plan:user-a",
            "renewal_cycle_start_at": datetime(2026, 9, 1, 0, 0, 0).isoformat(),
            "renewal_cycle_end_at": datetime(2026, 10, 1, 0, 0, 0).isoformat(),
        },
    )

    mismatch = _compare_existing_bonus_order(
        order,
        user_bid="user-a",
        product=product,
        campaign_id="batch",
        request_id="batch:bonus-plan:user-a",
    )

    assert "product_bid" in mismatch


def test_bonus_main_dry_run_does_not_resume_existing_sms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        f"{USER_BID_HEADER},{AMOUNT_HEADER}\nuser-a,100\n",
        encoding="utf-8",
    )
    product = BillingProduct(
        product_bid="product-a",
        product_code="creator-plan-monthly-pro",
        price_amount=19900,
    )
    order = BillingOrder(
        bill_order_bid="order-a",
        creator_bid="user-a",
        subscription_bid="subscription-a",
    )
    resume_calls: list[object] = []

    monkeypatch.setattr(sys, "argv", _bonus_argv(csv_path))
    monkeypatch.setattr(bonus_plan, "create_app", _create_fake_app)
    monkeypatch.setattr(bonus_plan, "_load_target_product", lambda **_: product)
    monkeypatch.setattr(bonus_plan, "_validate_product", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bonus_plan, "load_user_aggregate", lambda _user_bid: object())
    monkeypatch.setattr(bonus_plan, "_load_existing_bonus_order", lambda **_: order)
    monkeypatch.setattr(
        bonus_plan, "_compare_existing_bonus_order", lambda *_, **__: {}
    )
    monkeypatch.setattr(bonus_plan, "dump_json", lambda _payload: None)
    monkeypatch.setattr(
        bonus_plan,
        "_resume_existing_subscription_sms",
        lambda *args, **kwargs: resume_calls.append((args, kwargs)),
    )

    assert bonus_plan.main() == 0
    assert resume_calls == []


def test_bonus_main_returns_two_for_existing_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        f"{USER_BID_HEADER},{AMOUNT_HEADER}\nuser-a,100\n",
        encoding="utf-8",
    )
    product = BillingProduct(
        product_bid="product-a",
        product_code="creator-plan-monthly-pro",
        price_amount=19900,
    )
    order = BillingOrder(
        bill_order_bid="order-a",
        creator_bid="user-a",
        subscription_bid="subscription-a",
    )

    monkeypatch.setattr(sys, "argv", _bonus_argv(csv_path))
    monkeypatch.setattr(bonus_plan, "create_app", _create_fake_app)
    monkeypatch.setattr(bonus_plan, "_load_target_product", lambda **_: product)
    monkeypatch.setattr(bonus_plan, "_validate_product", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bonus_plan, "load_user_aggregate", lambda _user_bid: object())
    monkeypatch.setattr(bonus_plan, "_load_existing_bonus_order", lambda **_: order)
    monkeypatch.setattr(
        bonus_plan,
        "_compare_existing_bonus_order",
        lambda *_, **__: {"product_bid": {"expected": "a", "actual": "b"}},
    )
    monkeypatch.setattr(bonus_plan, "dump_json", lambda _payload: None)

    assert bonus_plan.main() == 2


def _bonus_argv(csv_path: Path) -> list[str]:
    return [
        "grant_cache_overcharge_bonus_plan.py",
        "--input",
        str(csv_path),
        "--subscription-sms-template-code",
        "SMS_TEST",
        "--subscription-sms-product-name",
        "AI Shifu test plan",
    ]


def _create_fake_app() -> _FakeApp:
    return _FakeApp()

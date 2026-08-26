"""Tests for one-time billing cache compensation scripts."""

from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

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


def test_reference_loader_rejects_duplicate_user_bid(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        f"{USER_BID_HEADER},{AMOUNT_HEADER}\nuser-a,100\nuser-a,50\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate user_bid"):
        load_reference_rows(str(csv_path), sheet_name=DEFAULT_SHEET_NAME)


def test_existing_credit_grant_reports_amount_mismatch() -> None:
    row = type(
        "Row",
        (),
        {"user_bid": "user-a", "amount": Decimal("150.00")},
    )()
    subscription = type(
        "Subscription",
        (),
        {"current_period_end_at": datetime(2026, 9, 1, 0, 0, 0)},
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
        subscription=subscription,
    )

    assert "amount" in mismatch


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

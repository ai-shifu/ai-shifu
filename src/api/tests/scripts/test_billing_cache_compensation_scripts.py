"""Tests for one-time billing cache compensation scripts."""

from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Self
from unittest.mock import Mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import grant_cache_overcharge_bonus_plan as bonus_plan  # noqa: E402
import grant_cache_overcharge_credit_compensation as credit_compensation  # noqa: E402
import grant_cache_overcharge_teacher_bonus_plan as teacher_bonus_plan  # noqa: E402
import restore_manual_credit_expiry_reset as expiry_reset  # noqa: E402
from billing_cache_compensation_common import (  # noqa: E402
    AMOUNT_HEADER,
    DEFAULT_SHEET_NAME,
    USER_BID_HEADER,
    add_mismatch,
    load_reference_rows,
)
from flaskr.service.billing.consts import (  # noqa: E402
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.manual_credit_grants import (  # noqa: E402
    MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
)
from flaskr.service.billing.models import (  # noqa: E402
    BillingOrder,
    BillingProduct,
    CreditLedgerEntry,
    CreditWalletBucket,
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
from grant_cache_overcharge_teacher_bonus_plan import TeacherBonusTarget  # noqa: E402

from tests.service.billing.cycle_state_test_helpers import (  # noqa: E402
    build_cycle_state_app,
)


class _FakeApp:
    def app_context(self) -> Self:
        return self

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_expiry_reset_candidate_requires_and_reconstructs_incident_evidence() -> None:
    app = build_cycle_state_app()
    granted_at = datetime(2026, 5, 15, 2, 14, 57)
    shortened_at = datetime(2026, 8, 26, 8, 47, 0)
    wrong_expiry = datetime(2026, 9, 24, 15, 59, 59)

    with app.app_context():
        from flaskr import dao

        dao.db.create_all()
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expiry-reset",
            wallet_bid="wallet-expiry-reset",
            creator_bid="creator-expiry-reset",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid="manual-expiry-reset",
            priority=20,
            original_credits=Decimal(55000),
            available_credits=Decimal(0),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal("31049.86"),
            expired_credits=Decimal("23950.14"),
            effective_from=granted_at,
            effective_to=wrong_expiry,
            status=CREDIT_BUCKET_STATUS_EXPIRED,
        )
        grant = CreditLedgerEntry(
            ledger_bid="grant-expiry-reset",
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=bucket.source_bid,
            idempotency_key="operator_manual_grant:original",
            amount=Decimal(55000),
            balance_after=Decimal(55000),
            expires_at=wrong_expiry,
            consumable_from=granted_at,
            metadata_json={"grant_type": "manual_grant", "validity_preset": "1y"},
            created_at=granted_at,
            updated_at=shortened_at,
        )
        expired = CreditLedgerEntry(
            ledger_bid="expire-expiry-reset",
            creator_bid=bucket.creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid=bucket.source_bid,
            idempotency_key="expire:bucket-expiry-reset",
            amount=Decimal("-23950.14"),
            balance_after=Decimal(0),
            expires_at=wrong_expiry,
            consumable_from=granted_at,
        )
        order = BillingOrder(
            bill_order_bid="order-expiry-reset",
            creator_bid=bucket.creator_bid,
            order_type=7301,
            product_bid="bill-product-plan-monthly-pro",
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            status=BILLING_ORDER_STATUS_PAID,
            created_at=shortened_at,
            metadata_json={
                "cache_overcharge_bonus_plan": True,
                "applied_cycle_end_at": wrong_expiry.isoformat(),
            },
        )
        dao.db.session.add_all([bucket, grant, expired, order])
        dao.db.session.commit()

        candidate = expiry_reset._load_candidate(bucket.wallet_bucket_bid)

        assert candidate.amount == Decimal("23950.14")
        assert candidate.intended_expires_at == datetime(2027, 5, 15, 2, 14, 57)
        assert candidate.source_expire_ledger_bid == expired.ledger_bid


def test_expiry_reset_existing_recovery_remains_verifiable_after_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = expiry_reset.RecoveryCandidate(
        creator_bid="creator-a",
        source_wallet_bucket_bid="source-bucket-a",
        amount=Decimal(100),
        intended_expires_at=datetime(2026, 5, 15, 2, 14, 57),
        source_expire_ledger_bid="expire-ledger-a",
        later_manual_grants=(
            expiry_reset.LaterManualGrant(
                ledger_bid="recovery-ledger-a",
                amount=Decimal(100),
                grant_source=MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
            ),
        ),
    )
    existing = CreditLedgerEntry(
        ledger_bid="recovery-ledger-a",
        creator_bid="creator-a",
        amount=Decimal(100),
        expires_at=candidate.intended_expires_at,
        metadata_json={
            "recovery_campaign_id": expiry_reset.DEFAULT_CAMPAIGN_ID,
            "source_wallet_bucket_bid": candidate.source_wallet_bucket_bid,
            "source_expire_ledger_bid": candidate.source_expire_ledger_bid,
        },
    )
    payloads: list[dict[str, object]] = []

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_manual_credit_expiry_reset.py",
            "--wallet-bucket-bid",
            candidate.source_wallet_bucket_bid,
        ],
    )
    monkeypatch.setattr(expiry_reset, "create_app", _create_fake_app)
    monkeypatch.setattr(expiry_reset, "now_utc", lambda: datetime(2027, 1, 1))
    monkeypatch.setattr(expiry_reset, "_load_candidate", lambda _: candidate)
    monkeypatch.setattr(expiry_reset, "_existing_recovery", lambda _: existing)
    monkeypatch.setattr(expiry_reset, "dump_json", payloads.append)

    assert expiry_reset.main() == 0
    assert payloads[0]["results"][0]["status"] == "existing_match"


def test_expiry_reset_apply_includes_provenance_in_atomic_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = expiry_reset.RecoveryCandidate(
        creator_bid="creator-a",
        source_wallet_bucket_bid="source-bucket-a",
        amount=Decimal(100),
        intended_expires_at=datetime(2027, 5, 15, 2, 14, 57),
        source_expire_ledger_bid="expire-ledger-a",
        later_manual_grants=(),
    )
    grant = Mock(
        return_value=SimpleNamespace(status="granted", ledger_bid="recovery-ledger-a")
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_manual_credit_expiry_reset.py",
            "--wallet-bucket-bid",
            candidate.source_wallet_bucket_bid,
            "--apply",
        ],
    )
    monkeypatch.setattr(expiry_reset, "create_app", _create_fake_app)
    monkeypatch.setattr(expiry_reset, "now_utc", lambda: datetime(2026, 9, 29))
    monkeypatch.setattr(expiry_reset, "_load_candidate", lambda _: candidate)
    monkeypatch.setattr(expiry_reset, "_existing_recovery", lambda _: None)
    monkeypatch.setattr(expiry_reset, "grant_manual_credits_with_expiry", grant)
    monkeypatch.setattr(expiry_reset, "dump_json", lambda _: None)

    assert expiry_reset.main() == 0
    assert grant.call_args.kwargs["audit_metadata"] == {
        "recovery_campaign_id": expiry_reset.DEFAULT_CAMPAIGN_ID,
        "source_wallet_bucket_bid": candidate.source_wallet_bucket_bid,
        "source_expire_ledger_bid": candidate.source_expire_ledger_bid,
    }


def test_expiry_reset_rejects_possible_compensation_under_another_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = expiry_reset.RecoveryCandidate(
        creator_bid="creator-a",
        source_wallet_bucket_bid="source-bucket-a",
        amount=Decimal(100),
        intended_expires_at=datetime(2027, 5, 15, 2, 14, 57),
        source_expire_ledger_bid="expire-ledger-a",
        later_manual_grants=(
            expiry_reset.LaterManualGrant(
                ledger_bid="other-compensation-ledger",
                amount=Decimal(75),
                grant_source=MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
            ),
        ),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_manual_credit_expiry_reset.py",
            "--wallet-bucket-bid",
            candidate.source_wallet_bucket_bid,
            "--apply",
        ],
    )
    monkeypatch.setattr(expiry_reset, "create_app", _create_fake_app)
    monkeypatch.setattr(expiry_reset, "now_utc", lambda: datetime(2026, 9, 29))
    monkeypatch.setattr(expiry_reset, "_load_candidate", lambda _: candidate)
    monkeypatch.setattr(expiry_reset, "_existing_recovery", lambda _: None)

    with pytest.raises(ValueError, match="possible_prior_compensation"):
        expiry_reset.main()


def test_expiry_reset_dry_run_reports_unrelated_later_reward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = expiry_reset.RecoveryCandidate(
        creator_bid="creator-a",
        source_wallet_bucket_bid="source-bucket-a",
        amount=Decimal(100),
        intended_expires_at=datetime(2027, 5, 15, 2, 14, 57),
        source_expire_ledger_bid="expire-ledger-a",
        later_manual_grants=(
            expiry_reset.LaterManualGrant(
                ledger_bid="later-reward-ledger",
                amount=Decimal(250),
                grant_source="reward",
            ),
        ),
    )
    payloads: list[dict[str, object]] = []

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_manual_credit_expiry_reset.py",
            "--wallet-bucket-bid",
            candidate.source_wallet_bucket_bid,
        ],
    )
    monkeypatch.setattr(expiry_reset, "create_app", _create_fake_app)
    monkeypatch.setattr(expiry_reset, "now_utc", lambda: datetime(2026, 9, 29))
    monkeypatch.setattr(expiry_reset, "_load_candidate", lambda _: candidate)
    monkeypatch.setattr(expiry_reset, "_existing_recovery", lambda _: None)
    monkeypatch.setattr(expiry_reset, "dump_json", payloads.append)

    assert expiry_reset.main() == 0
    result = payloads[0]["results"][0]
    assert result["status"] == "eligible"
    assert result["later_manual_grants"] == [
        {
            "ledger_bid": "later-reward-ledger",
            "amount": "250",
            "grant_source": "reward",
        }
    ]


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


def test_reference_loader_preserves_xlsx_numeric_zero_amount(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    xlsx_path = tmp_path / "input.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = DEFAULT_SHEET_NAME
    worksheet.append([USER_BID_HEADER, AMOUNT_HEADER])
    worksheet.append(["user-a", 0])
    workbook.save(xlsx_path)

    rows = load_reference_rows(str(xlsx_path), sheet_name=DEFAULT_SHEET_NAME)

    assert rows[0].amount == Decimal("0.00")


def test_add_mismatch_compares_decimal_values_without_scale_noise() -> None:
    mismatch: dict[str, object] = {}

    add_mismatch(
        mismatch,
        "amount",
        expected=Decimal("8739.02"),
        actual=Decimal("8739.0200000000"),
    )

    assert mismatch == {}


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
            "validity_preset": "align_subscription",
        },
    )

    mismatch = _compare_existing_credit_grant(
        ledger,
        row=row,
        request_id="batch:credit:user-a",
    )

    assert "amount" in mismatch


@pytest.mark.parametrize(
    "validity_metadata",
    [
        {"validity_preset": "align_subscription"},
        {"grant_channel": "cache_overcharge_compensation_script"},
    ],
)
def test_existing_credit_grant_uses_stored_period_end_after_renewal(
    validity_metadata: dict[str, object],
) -> None:
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
            **validity_metadata,
            "compensation_period_end_at": "2026-09-01T00:00:00Z",
        },
    )

    mismatch = _compare_existing_credit_grant(
        ledger,
        row=row,
        request_id="batch:credit:user-a",
    )

    assert mismatch == {}


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


def test_teacher_bonus_main_skips_original_batch_and_dry_run_does_not_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = BillingProduct(
        product_bid="product-a",
        product_code="creator-plan-monthly-pro",
        price_amount=19900,
    )
    payloads: list[dict[str, object]] = []
    persist_calls: list[object] = []
    sms_calls: list[object] = []

    monkeypatch.setattr(sys, "argv", _teacher_bonus_argv())
    monkeypatch.setattr(teacher_bonus_plan, "create_app", _create_fake_app)
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_load_teacher_targets",
        lambda _user_bids: [
            TeacherBonusTarget(
                user_bid="already-bonus",
                identify="13800138000",
                nickname="previous",
                state=1102,
            ),
            TeacherBonusTarget(
                user_bid="new-teacher",
                identify="teacher@example.com",
                nickname="new",
                state=1102,
            ),
        ],
    )
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_load_previous_bonus_creator_bids",
        lambda _campaign_id: {"already-bonus"},
    )
    monkeypatch.setattr(teacher_bonus_plan, "_load_target_product", lambda **_: product)
    monkeypatch.setattr(
        teacher_bonus_plan, "_validate_product", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        teacher_bonus_plan, "_load_existing_bonus_order", lambda **_: None
    )
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_resolve_order_shape",
        lambda **_: {"metadata": {}, "preview": {"grant_mode": "immediate"}},
    )
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_persist_bonus_order",
        lambda *args, **kwargs: persist_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_send_bonus_subscription_sms",
        lambda *args, **kwargs: sms_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(teacher_bonus_plan, "dump_json", payloads.append)

    assert teacher_bonus_plan.main() == 0
    assert persist_calls == []
    assert sms_calls == []
    assert payloads[0]["candidate_teacher_count"] == 2
    assert payloads[0]["excluded_original_bonus_count"] == 1
    assert payloads[0]["eligible_count"] == 1
    assert payloads[0]["results"][0]["reason"] == "already_in_original_bonus_batch"


def test_teacher_bonus_main_existing_mismatch_blocks_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = BillingProduct(
        product_bid="product-a",
        product_code="creator-plan-monthly-pro",
        price_amount=19900,
    )
    order = BillingOrder(
        bill_order_bid="order-a",
        creator_bid="teacher-a",
        subscription_bid="subscription-a",
    )

    persist_calls: list[object] = []

    monkeypatch.setattr(sys, "argv", [*_teacher_bonus_argv(), "--apply"])
    monkeypatch.setattr(teacher_bonus_plan, "create_app", _create_fake_app)
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_load_teacher_targets",
        lambda _user_bids: [
            TeacherBonusTarget(
                user_bid="teacher-a",
                identify="13800138000",
                nickname="teacher",
                state=1102,
            )
        ],
    )
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_load_previous_bonus_creator_bids",
        lambda _campaign_id: set(),
    )
    monkeypatch.setattr(teacher_bonus_plan, "_load_target_product", lambda **_: product)
    monkeypatch.setattr(
        teacher_bonus_plan, "_validate_product", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        teacher_bonus_plan, "_load_existing_bonus_order", lambda **_: order
    )
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_compare_existing_bonus_order",
        lambda *_, **__: {"product_bid": {"expected": "a", "actual": "b"}},
    )
    monkeypatch.setattr(
        teacher_bonus_plan,
        "_persist_bonus_order",
        lambda *args, **kwargs: persist_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(teacher_bonus_plan, "dump_json", lambda _payload: None)

    assert teacher_bonus_plan.main() == 2
    assert persist_calls == []


def test_teacher_bonus_main_rejects_blank_sms_template_before_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_calls: list[object] = []

    monkeypatch.setattr(
        sys,
        "argv",
        _teacher_bonus_argv(template_code="   "),
    )
    monkeypatch.setattr(
        teacher_bonus_plan,
        "create_app",
        lambda: app_calls.append(object()),
    )

    with pytest.raises(RuntimeError, match="--subscription-sms-template-code"):
        teacher_bonus_plan.main()
    assert app_calls == []


def test_teacher_bonus_masks_identifiers_and_sms_mobile() -> None:
    target = TeacherBonusTarget(
        user_bid="teacher-a",
        identify="13800138000",
        nickname="teacher",
        state=1102,
    )

    payload = teacher_bonus_plan._target_to_payload(target)
    sms_result = teacher_bonus_plan._sanitize_sms_result(
        {"status": "sent", "mobile": "13900139000"}
    )

    assert payload["identify"] == "138****8000"
    assert teacher_bonus_plan._mask_identifier("teacher@example.com") == (
        "te***@example.com"
    )
    assert sms_result["mobile"] == "139****9000"


def test_teacher_bonus_escapes_like_literal_prefix() -> None:
    assert teacher_bonus_plan._escape_like_literal("cache_overcharge%\\") == (
        "cache\\_overcharge\\%\\\\"
    )


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


def _teacher_bonus_argv(template_code: str = "SMS_TEST") -> list[str]:
    return [
        "grant_cache_overcharge_teacher_bonus_plan.py",
        "--subscription-sms-template-code",
        template_code,
        "--subscription-sms-product-name",
        "AI Shifu test plan",
    ]


def _create_fake_app() -> _FakeApp:
    return _FakeApp()


def test_credit_compensation_passes_exact_subscription_expiry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        f"{USER_BID_HEADER},{AMOUNT_HEADER}\nuser-a,100\n", encoding="utf-8"
    )
    expires_at = datetime(2026, 9, 30, 8, 12, 34, 123456)
    subscription = SimpleNamespace(
        subscription_bid="subscription-a", current_period_end_at=expires_at
    )
    grant = Mock(
        return_value=SimpleNamespace(
            status="granted",
            ledger_bid="ledger-a",
            wallet_bucket_bid="bucket-a",
            expires_at=expires_at,
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "grant_cache_overcharge_credit_compensation.py",
            "--input",
            str(csv_path),
            "--apply",
        ],
    )
    monkeypatch.setattr(credit_compensation, "create_app", _create_fake_app)
    monkeypatch.setattr(credit_compensation, "load_user_aggregate", lambda _: object())
    monkeypatch.setattr(
        credit_compensation,
        "load_primary_active_subscription",
        lambda *_, **__: subscription,
    )
    monkeypatch.setattr(
        credit_compensation, "_load_existing_credit_grant", lambda _: None
    )
    monkeypatch.setattr(credit_compensation, "grant_manual_credits_with_expiry", grant)
    monkeypatch.setattr(
        credit_compensation, "_write_compensation_grant_metadata", lambda **_: None
    )
    monkeypatch.setattr(credit_compensation, "dump_json", lambda _: None)

    assert credit_compensation.main() == 0
    grant.assert_called_once()
    assert grant.call_args.kwargs["expires_at"] == expires_at
    assert "validity_preset" not in grant.call_args.kwargs
    assert "validity_value" not in grant.call_args.kwargs
    assert "validity_unit" not in grant.call_args.kwargs


@pytest.mark.parametrize(
    "validity_metadata",
    [
        {"validity_preset": "1m"},
        {"grant_channel": "operator_user_management"},
        {
            "grant_channel": "cache_overcharge_compensation_script",
            "validity_value": 1,
            "validity_unit": "month",
        },
    ],
)
def test_credit_compensation_rejects_other_grant_contracts(
    validity_metadata: dict[str, object],
) -> None:
    ledger = CreditLedgerEntry(
        creator_bid="user-a",
        amount=Decimal(100),
        idempotency_key="operator_manual_grant:batch:credit:user-a",
        expires_at=datetime(2026, 9, 1),
        metadata_json={
            "grant_source": MANUAL_CREDIT_GRANT_SOURCE_COMPENSATION,
            **validity_metadata,
        },
    )
    assert _compare_existing_credit_grant(
        ledger,
        row=SimpleNamespace(user_bid="user-a", amount=Decimal(100)),
        request_id="batch:credit:user-a",
    )

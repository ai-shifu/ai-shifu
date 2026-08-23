"""Verify credit grant allocation views behavior."""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_TYPE_MANUAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_TOPUP,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.credit_grant_allocation_views import (
    build_credit_allocation_view,
    build_credit_grant_view,
    resolve_credit_asset_kind,
)
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from sqlalchemy import text


@pytest.fixture
def billing_view_app() -> object:
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
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _bucket(
    *,
    bucket_category: int,
    source_type: int,
    source_bid: str = "source-1",
    metadata_json: dict | None = None,
    wallet_bucket_bid: str = "bucket-1",
    wallet_bid: str = "wallet-1",
    creator_bid: str = "teacher-1",
    deleted: int = 0,
) -> CreditWalletBucket:
    return CreditWalletBucket(
        wallet_bucket_bid=wallet_bucket_bid,
        wallet_bid=wallet_bid,
        creator_bid=creator_bid,
        bucket_category=bucket_category,
        source_type=source_type,
        source_bid=source_bid,
        priority=20,
        original_credits=Decimal("10.0000000000"),
        available_credits=Decimal("7.0000000000"),
        reserved_credits=Decimal("2.0000000000"),
        consumed_credits=Decimal("1.0000000000"),
        expired_credits=Decimal(0),
        effective_from=datetime(2026, 4, 1, 0, 0, 0),
        effective_to=datetime(2026, 5, 1, 0, 0, 0),
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json=metadata_json or {},
        deleted=deleted,
    )


def _grant_ledger(
    *,
    entry_type: int = CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    source_type: int = CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    source_bid: str = "source-1",
    metadata_json: dict | None = None,
    wallet_bucket_bid: str = "bucket-1",
    wallet_bid: str = "wallet-1",
    creator_bid: str = "teacher-1",
) -> CreditLedgerEntry:
    return CreditLedgerEntry(
        ledger_bid="ledger-1",
        creator_bid=creator_bid,
        wallet_bid=wallet_bid,
        wallet_bucket_bid=wallet_bucket_bid,
        entry_type=entry_type,
        source_type=source_type,
        source_bid=source_bid,
        idempotency_key="ledger-1",
        amount=Decimal("10.0000000000"),
        balance_after=Decimal("12.0000000000"),
        consumable_from=datetime(2026, 4, 1, 0, 0, 0),
        expires_at=datetime(2026, 5, 1, 0, 0, 0),
        metadata_json=metadata_json or {},
    )


def test_subscription_bucket_is_interpreted_as_plan_credits() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    )

    view = build_credit_allocation_view(bucket)

    assert view.asset_kind == "plan_credits"
    assert view.bucket_category_label == "subscription"
    assert view.runtime_bucket_category_label == "subscription"
    assert view.available_credits == Decimal("7.0000000000")
    assert view.effective_to == datetime(2026, 5, 1, 0, 0, 0)


def test_topup_bucket_is_interpreted_as_pack_credits() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
    )

    view = build_credit_allocation_view(bucket)

    assert view.asset_kind == "pack_credits"
    assert view.bucket_category_label == "topup"
    assert view.runtime_bucket_category_label == "topup"


def test_campaign_bonus_uses_bucket_category_for_canonical_asset_kind() -> None:
    topup_bonus = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    )
    plan_bonus = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    )

    assert build_credit_allocation_view(topup_bonus).asset_kind == "pack_credits"
    assert build_credit_allocation_view(plan_bonus).asset_kind == "plan_credits"


def test_legacy_gift_or_manual_without_bucket_evidence_stays_internal() -> None:
    assert (
        resolve_credit_asset_kind(source_type=CREDIT_SOURCE_TYPE_GIFT)
        == "internal_legacy"
    )
    assert (
        resolve_credit_asset_kind(source_type=CREDIT_SOURCE_TYPE_MANUAL)
        == "internal_legacy"
    )


def test_legacy_manual_allocation_without_category_evidence_stays_internal() -> None:
    bucket = _bucket(
        bucket_category=0,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        source_bid="manual-source-1",
    )

    view = build_credit_allocation_view(bucket)

    assert view.asset_kind == "internal_legacy"


def test_legacy_gift_can_use_metadata_bucket_hint() -> None:
    asset_kind = resolve_credit_asset_kind(
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        metadata={"bucket_category": "topup"},
    )

    assert asset_kind == "pack_credits"


def test_unknown_campaign_bonus_without_bucket_evidence_stays_unknown() -> None:
    asset_kind = resolve_credit_asset_kind(
        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS
    )

    assert asset_kind == "unknown"


def test_unknown_allocation_fails_closed_instead_of_runtime_default() -> None:
    bucket = _bucket(bucket_category=0, source_type=0)

    view = build_credit_allocation_view(bucket)

    assert view.runtime_bucket_category_label == "subscription"
    assert view.asset_kind == "unknown"


def test_campaign_bonus_with_missing_or_null_category_stays_unknown() -> None:
    for metadata in (
        {},
        {"bucket_category": None},
        {"bucket_category": "null"},
        {"bucket_category": ""},
    ):
        bucket = _bucket(
            bucket_category=0,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            metadata_json=metadata,
        )

        assert build_credit_allocation_view(bucket).asset_kind == "unknown"


def test_unknown_order_type_and_missing_order_fail_closed() -> None:
    assert (
        resolve_credit_asset_kind(
            source_type=CREDIT_SOURCE_TYPE_GIFT,
            metadata={"bill_order_bid": "missing-order"},
            load_order_type=lambda _order_bid: None,
        )
        == "unknown"
    )
    assert (
        resolve_credit_asset_kind(
            source_type=CREDIT_SOURCE_TYPE_GIFT,
            metadata={"bill_order_bid": "manual-order"},
            load_order_type=lambda _order_bid: BILLING_ORDER_TYPE_MANUAL,
        )
        == "unknown"
    )


def test_category_source_metadata_conflict_fails_closed() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
        metadata_json={"bucket_category": "topup"},
    )

    assert build_credit_allocation_view(bucket).asset_kind == "unknown"


def test_free_bucket_maps_to_plan_credits_for_legacy_trial_allocations() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
        source_type=CREDIT_SOURCE_TYPE_GIFT,
    )

    view = build_credit_allocation_view(bucket)

    assert view.asset_kind == "plan_credits"
    assert view.runtime_bucket_category_label == "subscription"


def test_generic_manual_bucket_is_internal_legacy() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        metadata_json={"checkout_type": "manual_grant"},
    )

    view = build_credit_allocation_view(bucket)

    assert view.asset_kind == "internal_legacy"


def test_current_manual_referral_reward_shape_is_plan_credits() -> None:
    metadata = {
        "grant_type": "referral_reward",
        "reward_scene": "referral",
        "reward_program": "referral_reward",
        "validity_strategy": "stack_by_reward_scene",
    }
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        source_bid="referral_reward",
        metadata_json=metadata,
    )
    ledger = _grant_ledger(
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        source_bid="referral_reward",
        metadata_json=metadata,
    )

    assert build_credit_allocation_view(bucket).asset_kind == "plan_credits"
    assert build_credit_grant_view(ledger, bucket=bucket).asset_kind == "plan_credits"


def test_partial_manual_referral_reward_evidence_stays_internal_legacy() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        source_bid="referral_reward",
        metadata_json={"grant_type": "referral_reward"},
    )

    assert build_credit_allocation_view(bucket).asset_kind == "internal_legacy"


def test_referral_and_preorder_metadata_are_plan_credits() -> None:
    assert (
        resolve_credit_asset_kind(
            source_type=CREDIT_SOURCE_TYPE_GIFT,
            metadata={"checkout_type": "referral_invitation_reward"},
        )
        == "plan_credits"
    )
    assert (
        resolve_credit_asset_kind(
            source_type=CREDIT_SOURCE_TYPE_GIFT,
            metadata={"checkout_type": "subscription_preorder"},
        )
        == "plan_credits"
    )


def test_grant_view_carries_state_and_allocation_without_mutating_models() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
    )
    ledger = _grant_ledger(
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
        metadata_json={"bucket_credit_state": "reserved"},
    )
    original_bucket_metadata = dict(bucket.metadata_json)
    original_ledger_metadata = dict(ledger.metadata_json)

    view = build_credit_grant_view(ledger, bucket=bucket)

    assert view.asset_kind == "pack_credits"
    assert view.grant_state == "reserved"
    assert view.entry_type_label == "grant"
    assert view.allocation is not None
    assert view.allocation.wallet_bucket_bid == "bucket-1"
    assert bucket.metadata_json == original_bucket_metadata
    assert ledger.metadata_json == original_ledger_metadata


def test_grant_view_does_not_attach_mismatched_or_deleted_allocation() -> None:
    ledger = _grant_ledger(
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        metadata_json={"bucket_credit_state": "available"},
    )

    mismatched = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
        wallet_bucket_bid="other-bucket",
    )
    deleted = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
        deleted=1,
    )

    assert build_credit_grant_view(ledger, bucket=mismatched).allocation is None
    assert build_credit_grant_view(ledger, bucket=deleted).allocation is None
    assert (
        build_credit_grant_view(ledger, bucket=mismatched).asset_kind == "plan_credits"
    )


def test_grant_view_conflicting_ledger_and_allocation_evidence_is_unknown() -> None:
    ledger = _grant_ledger(
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        metadata_json={"bucket_credit_state": "available"},
    )
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        source_type=CREDIT_SOURCE_TYPE_TOPUP,
    )

    view = build_credit_grant_view(ledger, bucket=bucket)

    assert view.allocation is not None
    assert view.allocation.asset_kind == "pack_credits"
    assert view.asset_kind == "unknown"


def test_multiple_grants_can_share_one_allocation_view() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    )
    first = _grant_ledger(source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION)
    second = _grant_ledger(source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION)
    second.ledger_bid = "ledger-2"

    first_view = build_credit_grant_view(first, bucket=bucket)
    second_view = build_credit_grant_view(second, bucket=bucket)

    assert first_view.allocation is not None
    assert second_view.allocation is not None
    assert first_view.asset_kind == "plan_credits"
    assert second_view.asset_kind == "plan_credits"


def test_deleted_grant_view_fails_closed_and_ignores_allocation() -> None:
    ledger = _grant_ledger(
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        metadata_json={"bucket_credit_state": "available"},
    )
    ledger.deleted = 1
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    )

    view = build_credit_grant_view(ledger, bucket=bucket)

    assert view.asset_kind == "unknown"
    assert view.allocation is None


def test_grant_view_without_bucket_uses_ledger_source() -> None:
    ledger = _grant_ledger(
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        metadata_json={"bucket_credit_state": "available"},
    )

    view = build_credit_grant_view(ledger)

    assert view.asset_kind == "plan_credits"
    assert view.grant_state == "available"
    assert view.allocation is None


def test_non_grant_ledger_is_not_treated_as_grant_state() -> None:
    ledger = _grant_ledger(
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        metadata_json={"bucket_credit_state": "available"},
    )

    view = build_credit_grant_view(ledger)

    assert view.grant_state == "not_grant"
    assert view.entry_type_label == "consume"


def test_order_type_loader_can_classify_legacy_gift_without_schema_changes() -> None:
    calls: list[str] = []

    def load_order_type(order_bid: str) -> int | None:
        calls.append(order_bid)
        return BILLING_ORDER_TYPE_TOPUP

    bucket = _bucket(
        bucket_category=0,
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        metadata_json={"bill_order_bid": "order-pack-1"},
    )

    view = build_credit_allocation_view(bucket, load_order_type=load_order_type)

    assert view.asset_kind == "pack_credits"
    assert calls == ["order-pack-1"]


def test_direct_asset_resolver_can_classify_legacy_gift_order() -> None:
    asset_kind = resolve_credit_asset_kind(
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        metadata={"bill_order_bid": "order-pack-1"},
        load_order_type=lambda _order_bid: BILLING_ORDER_TYPE_TOPUP,
    )

    assert asset_kind == "pack_credits"


def test_subscription_order_type_loader_maps_legacy_gift_to_plan_credits() -> None:
    bucket = _bucket(
        bucket_category=0,
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        metadata_json={"bill_order_bid": "order-plan-1"},
    )

    view = build_credit_allocation_view(
        bucket,
        load_order_type=lambda _order_bid: BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    )

    assert view.asset_kind == "plan_credits"


def test_campaign_bonus_without_bucket_uses_order_evidence() -> None:
    ledger = _grant_ledger(
        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
        source_bid="campaign-1",
        metadata_json={"bill_order_bid": "order-pack-1"},
    )

    view = build_credit_grant_view(
        ledger,
        load_order_type=lambda _order_bid: BILLING_ORDER_TYPE_TOPUP,
    )

    assert view.asset_kind == "pack_credits"


def test_legacy_trial_gift_without_bucket_uses_source_bid_evidence() -> None:
    ledger = _grant_ledger(
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        source_bid="new_creator_v1",
        wallet_bucket_bid="",
        metadata_json={"bucket_credit_state": "available"},
    )

    view = build_credit_grant_view(ledger)

    assert view.asset_kind == "plan_credits"


def test_manual_generic_metadata_does_not_become_plan_credits() -> None:
    bucket = _bucket(
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        metadata_json={"product_type": "plan", "program_code": "other_program"},
    )

    view = build_credit_allocation_view(bucket)

    assert view.asset_kind == "internal_legacy"


def test_non_finite_metadata_bucket_category_fails_closed() -> None:
    for value in (math.inf, math.nan):
        assert (
            resolve_credit_asset_kind(
                source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
                metadata={"bucket_category": value},
            )
            == "unknown"
        )


def test_order_type_fallback_does_not_trigger_session_autoflush(
    billing_view_app: Flask,
) -> None:
    with billing_view_app.app_context():
        dirty_order = BillingOrder(
            bill_order_bid="dirty-order",
            creator_bid="teacher-1",
            order_type=BILLING_ORDER_TYPE_TOPUP,
            product_bid="product-1",
            status=1,
        )
        deleted_order = BillingOrder(
            bill_order_bid="deleted-order",
            creator_bid="teacher-1",
            order_type=BILLING_ORDER_TYPE_TOPUP,
            product_bid="product-1",
            status=1,
        )
        dao.db.session.add_all([dirty_order, deleted_order])
        dao.db.session.commit()

        dirty_order.status = 2
        dao.db.session.delete(deleted_order)
        dao.db.session.add(
            BillingOrder(
                bill_order_bid="pending-new-order",
                creator_bid="teacher-1",
                order_type=BILLING_ORDER_TYPE_TOPUP,
                product_bid="product-1",
                status=1,
            )
        )

        def load_order_type(order_bid: str) -> int | None:
            assert order_bid == "order-pack-1"
            return BillingOrder.query.filter_by(bill_order_bid=order_bid).count() or (
                BILLING_ORDER_TYPE_TOPUP
            )

        asset_kind = resolve_credit_asset_kind(
            source_type=CREDIT_SOURCE_TYPE_GIFT,
            metadata={"bill_order_bid": "order-pack-1"},
            load_order_type=load_order_type,
        )

        assert asset_kind == "pack_credits"
        assert len(dao.db.session.new) == 1
        assert len(dao.db.session.dirty) == 1
        assert len(dao.db.session.deleted) == 1
        with dao.db.session.no_autoflush:
            rows = dao.db.session.execute(
                text(
                    "select bill_order_bid, status from bill_orders "
                    "where bill_order_bid in "
                    "('pending-new-order', 'dirty-order', 'deleted-order') "
                    "order by bill_order_bid"
                )
            ).all()
        assert rows == [("deleted-order", 1), ("dirty-order", 1)]

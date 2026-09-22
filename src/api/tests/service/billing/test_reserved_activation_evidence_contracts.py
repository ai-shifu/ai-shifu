"""Verify reserved renewals reject incomplete evidence and activate atomically."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import reserved_renewal_activation as activation
from flaskr.service.billing import subscriptions
from flaskr.service.billing.consts import (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_GIFT,
)
from flaskr.service.billing.models import (
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)

from tests.service.billing.cycle_state_test_helpers import (
    add_reserved_renewal_activation_state,
    build_cycle_state_app,
    create_cycle_state_renewal_order,
    create_cycle_state_renewal_product,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def reserved_cycle() -> Iterator[SimpleNamespace]:
    app = build_cycle_state_app()
    with app.app_context():
        db.create_all()
        start, end = datetime(2026, 5, 1), datetime(2026, 6, 1)
        product = create_cycle_state_renewal_product()
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-activation-boundary",
            creator_bid="creator-renewal-activation-boundary",
            product_bid=product.product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=start,
            current_period_end_at=end,
        )
        order = create_cycle_state_renewal_order(
            metadata_json={"renewal_cycle_start_at": "2026-05-01T00:00:00Z"}
        )
        wallet, bucket, ledger = add_reserved_renewal_activation_state(
            product=product,
            subscription=subscription,
            order=order,
            current_cycle_start=datetime(2026, 4, 1),
            current_cycle_end=start,
            next_cycle_end=end,
        )
        db.session.add_all([product, subscription, order])
        db.session.commit()
        yield SimpleNamespace(
            app=app,
            start=start,
            end=end,
            product=product,
            subscription=subscription,
            order=order,
            wallet=wallet,
            bucket=bucket,
            ledger=ledger,
        )
        db.session.remove()
        db.drop_all()


def _add_bonus(state: SimpleNamespace) -> tuple[CreditWalletBucket, CreditLedgerEntry]:
    state.order.campaign_bid = "renewal-campaign"
    state.order.campaign_bonus_credit_amount = 10
    bucket = CreditWalletBucket(
        wallet_bucket_bid="bonus-bucket",
        wallet_bid=state.wallet.wallet_bid,
        creator_bid=state.order.creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        source_bid=state.order.bill_order_bid,
        priority=20,
        original_credits=10,
        reserved_credits=10,
        available_credits=0,
        effective_from=state.start,
        effective_to=state.end,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
    )
    ledger = CreditLedgerEntry(
        ledger_bid="bonus-ledger",
        wallet_bid=state.wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        creator_bid=state.order.creator_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        source_bid=state.order.bill_order_bid,
        idempotency_key=f"grant:campaign_bonus:{state.order.bill_order_bid}",
        amount=10,
        balance_after=3,
        metadata_json={"bucket_credit_state": "reserved"},
    )
    state.wallet.reserved_credits = 1010
    db.session.add_all([bucket, ledger])
    db.session.commit()
    return bucket, ledger


def _activate(
    state: SimpleNamespace,
) -> tuple[activation.ReservedActivationTarget, ...]:
    return activation.activate_reserved_renewal_grants_for_cycle(
        state.app,
        order=state.order,
        effective_from=state.start,
        effective_to=state.end,
        expire_bucket_balance_for_transition=subscriptions._expire_credit_bucket_balance_for_transition,
    )


@pytest.mark.parametrize(
    ("damage", "error"),
    [
        ("ledger", "missing_subscription_ledger"),
        ("state", "invalid_subscription_state"),
        ("amount", "invalid_subscription_amount"),
        ("amount-metadata", "subscription_amount_mismatch"),
        ("bucket", "missing_subscription_bucket"),
        ("reserved", "insufficient_subscription_reserved"),
        ("product", "missing_subscription_product"),
        ("product-id", "missing_subscription_product"),
        ("cycle-amount", "subscription_cycle_amount_mismatch"),
    ],
)
def test_preflight_rejects_broken_subscription_evidence_without_writes(
    reserved_cycle: SimpleNamespace,
    damage: str,
    error: str,
) -> None:
    state = reserved_cycle
    if damage == "ledger":
        state.ledger.deleted = 1
    elif damage == "state":
        state.ledger.metadata_json = {"bucket_credit_state": "absorbed"}
    elif damage == "amount":
        state.ledger.amount = 0
    elif damage == "amount-metadata":
        state.ledger.metadata_json = {
            "bucket_credit_state": "reserved",
            "grant_credit_amount": "999",
        }
    elif damage == "bucket":
        state.bucket.deleted = 1
    elif damage == "reserved":
        state.bucket.reserved_credits = 999
    elif damage == "product":
        state.product.deleted = 1
    elif damage == "product-id":
        state.order.product_bid = ""
    else:
        state.product.credit_amount = 2000
    db.session.commit()
    original_version = state.wallet.version
    with pytest.raises(activation.IncompleteReservedGrantActivationError, match=error):
        activation.validate_reserved_renewal_cycle_activation(
            state.order,
            effective_from=state.start,
        )
    db.session.expire_all()
    assert state.wallet.version == original_version
    assert state.wallet.available_credits == 3
    assert state.bucket.available_credits == 3
    assert CreditLedgerEntry.query.count() == 1


@pytest.mark.parametrize(
    ("damage", "error"),
    [
        ("ledger", "missing_campaign_bonus_ledger"),
        ("state", "invalid_campaign_bonus_state"),
        ("amount", "campaign_bonus_amount_mismatch"),
        ("bucket-id", "missing_campaign_bonus_bucket"),
        ("bucket", "missing_campaign_bonus_bucket"),
        ("reserved", "insufficient_campaign_bonus_reserved"),
    ],
)
def test_campaign_preflight_failure_preserves_other_reserved_grants(
    reserved_cycle: SimpleNamespace,
    damage: str,
    error: str,
) -> None:
    state = reserved_cycle
    bucket, ledger = _add_bonus(state)
    if damage == "ledger":
        ledger.deleted = 1
    elif damage == "state":
        ledger.metadata_json = {}
    elif damage == "amount":
        ledger.amount = 9
    elif damage == "bucket-id":
        ledger.wallet_bucket_bid = ""
    elif damage == "bucket":
        bucket.deleted = 1
    else:
        bucket.reserved_credits = 9
    db.session.commit()
    with (
        pytest.raises(activation.IncompleteReservedGrantActivationError, match=error),
        unit_of_work(),
    ):
        _activate(state)
    db.session.expire_all()
    assert state.ledger.metadata_json["bucket_credit_state"] == "reserved"
    assert state.bucket.reserved_credits == 1000
    assert state.bucket.available_credits == state.wallet.available_credits == 3


@pytest.mark.parametrize("fallback_bucket", [False, True])
def test_cycle_activation_releases_bonus_once_and_updates_ledger_balances(
    reserved_cycle: SimpleNamespace,
    fallback_bucket: bool,
) -> None:
    state = reserved_cycle
    bonus_bucket, bonus_ledger = _add_bonus(state)
    if fallback_bucket:
        state.ledger.wallet_bucket_bid = ""
        db.session.commit()
    with unit_of_work():
        targets = _activate(state)
        activation.sync_activated_reserved_renewal_ledger_balances(
            targets=targets,
            final_balance_after=Decimal(1010),
        )
    db.session.expire_all()
    assert len(targets) == 2
    assert state.bucket.available_credits == 1000
    assert state.bucket.expired_credits == 3
    assert state.bucket.reserved_credits == bonus_bucket.reserved_credits == 0
    assert bonus_bucket.available_credits == 10
    assert state.wallet.available_credits == 1010
    assert state.wallet.reserved_credits == 0
    assert state.ledger.balance_after == 1000
    assert bonus_ledger.balance_after == 1010
    version = state.wallet.version
    with unit_of_work():
        assert _activate(state) == ()
    db.session.expire_all()
    assert state.wallet.version == version
    assert bonus_bucket.available_credits == 10


@pytest.mark.parametrize(
    "damage", ["skipped", "ledger", "amount", "bucket", "available"]
)
def test_incomplete_final_bonus_rolls_back_prior_subscription_activation(
    reserved_cycle: SimpleNamespace,
    damage: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = reserved_cycle
    bonus_bucket, bonus_ledger = _add_bonus(state)
    mutate = activation.activate_reserved_grant_credit
    observed = []

    def fail_final_bonus(**kwargs: object) -> object:
        result = mutate(**kwargs)
        if kwargs["grant_entry"] is bonus_ledger:
            assert state.ledger.metadata_json["bucket_credit_state"] == "available"
            observed.append(state.bucket.available_credits)
            if damage == "skipped":
                bonus_ledger.metadata_json = {"bucket_credit_state": "reserved"}
            elif damage == "ledger":
                bonus_ledger.deleted = 1
            elif damage == "amount":
                bonus_ledger.amount = 9
            elif damage == "bucket":
                bonus_bucket.deleted = 1
            else:
                bonus_bucket.available_credits = 0
        return result

    monkeypatch.setattr(activation, "activate_reserved_grant_credit", fail_final_bonus)
    with (
        pytest.raises(activation.IncompleteReservedGrantActivationError),
        unit_of_work(),
    ):
        _activate(state)
    assert observed == [Decimal(1000)]
    db.session.expire_all()
    assert state.bucket.available_credits == state.wallet.available_credits == 3
    assert state.bucket.reserved_credits == 1000
    assert state.wallet.reserved_credits == 1010
    assert bonus_bucket.reserved_credits == bonus_ledger.amount == 10
    assert bonus_bucket.available_credits == 0
    assert bonus_bucket.deleted == bonus_ledger.deleted == 0
    assert state.ledger.metadata_json["bucket_credit_state"] == "reserved"
    assert bonus_ledger.metadata_json["bucket_credit_state"] == "reserved"


@pytest.mark.parametrize("damage", ["missing", "reserved"])
def test_balance_sync_rejects_unactivated_ledger_and_rolls_back_prior_update(
    reserved_cycle: SimpleNamespace,
    damage: str,
) -> None:
    state = reserved_cycle
    _, bonus = _add_bonus(state)
    with unit_of_work():
        targets = _activate(state)
    if damage == "missing":
        bonus.deleted = 1
    else:
        bonus.metadata_json = {"bucket_credit_state": "reserved"}
    db.session.commit()
    old_balance = state.ledger.balance_after
    with (
        pytest.raises(activation.IncompleteReservedGrantActivationError),
        unit_of_work(),
    ):
        activation.sync_activated_reserved_renewal_ledger_balances(
            targets=targets,
            final_balance_after=Decimal(2000),
        )
    db.session.expire_all()
    assert state.ledger.balance_after == old_balance


def test_cycle_matching_normalizes_offset_times_and_legacy_missing_bucket_link(
    reserved_cycle: SimpleNamespace,
) -> None:
    state = reserved_cycle
    state.ledger.metadata_json = {
        "bucket_credit_state": "reserved",
        "credit_amount": "1000",
    }
    state.ledger.wallet_bucket_bid = ""
    db.session.commit()
    offset_start = state.start.replace(tzinfo=UTC).astimezone(
        timezone(timedelta(hours=8))
    )
    targets = activation.validate_reserved_renewal_cycle_activation(
        state.order,
        effective_from=offset_start,
    )
    assert len(targets) == 1
    assert targets[0].wallet_bucket_bid == state.bucket.wallet_bucket_bid
    assert targets[0].amount == 1000

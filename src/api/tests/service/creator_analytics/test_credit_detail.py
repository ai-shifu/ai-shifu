"""End-to-end tests for POST /api/creator-analytics/credit-detail.

The endpoint joins bill_usage x credit_ledger_entries server-side and
returns the actual credit deduction per usage row, scoped to the caller's
shifu permission. These tests cover the happy path, the
``source_type = USAGE`` security filter, scope enforcement, optional
filters (scene / type / date range), pagination, absolute-value rendering,
audit logging, and the empty-result fall-through when no ledger entry
matches a usage record.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.creator_analytics import engine as analytics_engine

from .conftest import (
    seed_bill_usage_record,
    seed_credit_ledger_entry,
    seed_owned_course,
)


ENDPOINT = "/api/creator-analytics/credit-detail"


@pytest.fixture(autouse=True)
def _reset_analytics_engine_singleton():
    analytics_engine.reset_for_tests()
    yield
    analytics_engine.reset_for_tests()


def _post(test_client, body):
    return test_client.post(ENDPOINT, json=body)


def _seed_usage_with_ledger(
    *,
    shifu_bid: str,
    user_bid: str,
    creator_bid: str,
    suffix: str,
    amount: float,
    usage_scene: int = 1203,
    usage_type: int = 1101,
    provider: str = "deepseek",
    model: str = "deepseek-v4-flash",
    created_at=None,
) -> str:
    """Seed a paired (BillUsageRecord, CreditLedgerEntry) for one charge."""

    usage_bid = f"u-{shifu_bid}-{suffix}"
    seed_bill_usage_record(
        usage_bid=usage_bid,
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        progress_record_bid=f"pr-{suffix}",
        outline_item_bid=f"ol-{suffix}",
        usage_type=usage_type,
        usage_scene=usage_scene,
        provider=provider,
        model=model,
        created_at=created_at,
    )
    seed_credit_ledger_entry(
        ledger_bid=f"l-{shifu_bid}-{suffix}",
        creator_bid=creator_bid,
        source_bid=usage_bid,
        amount=amount,
        created_at=created_at,
    )
    return usage_bid


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_credit_detail_returns_summary_and_rows(mock_request_user, test_client, app):
    """3 paired usage / ledger rows → summary aggregates them and rows
    list each charge. amount stored as a negative number; API returns
    the absolute value as `credits`."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="1",
            amount=-0.51,
        )
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="2",
            amount=-0.32,
        )
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u2",
            creator_bid="teacher-1",
            suffix="3",
            amount=-1.10,
            usage_scene=1202,
        )

    response = _post(test_client, {"shifu_bid": "shifu-a"})
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json(force=True)
    assert payload["code"] == 0

    data = payload["data"]
    assert data["summary"]["total_records"] == 3
    assert float(data["summary"]["total_credits"]) == pytest.approx(1.93)
    assert data["summary"]["unique_users"] == 2
    assert data["summary"]["unique_progress"] == 3
    # Single wallet absorbed every charge: the course owner. The summary
    # exposes the count, callers must look at per-row wallet_creator_bid
    # if they care which wallet it was (or which wallets, in the rare
    # subscription / proxy-payment split case).
    assert data["summary"]["unique_wallets"] == 1
    assert "wallet_creator_bid" not in data["summary"]
    assert len(data["rows"]) == 3
    for row in data["rows"]:
        assert float(row["credits"]) >= 0  # ABS applied
        assert row["wallet_creator_bid"] == "teacher-1"


# ---------------------------------------------------------------------------
# source_type = USAGE security filter (key security guard)
# ---------------------------------------------------------------------------


def test_credit_detail_excludes_non_usage_ledger_entries(
    mock_request_user, test_client, app
):
    """A ledger entry with source_type != USAGE (e.g. subscription / topup)
    must never appear in the result, even if its source_bid happens to
    match an existing bill_usage.usage_bid (which would not happen in
    production, but the filter must be defensive)."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        # Legitimate USAGE row — must appear
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="legit",
            amount=-0.5,
        )
        # Plant a SUBSCRIPTION ledger row pointing at the same usage_bid;
        # the join must filter it out via source_type clause.
        seed_credit_ledger_entry(
            ledger_bid="l-poison",
            creator_bid="teacher-1",
            source_bid="u-shifu-a-legit",
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            amount=100.00,  # would massively skew summary if leaked
            idempotency_key="poison-1",
        )

    response = _post(test_client, {"shifu_bid": "shifu-a"})
    data = response.get_json(force=True)["data"]
    # Only the legitimate USAGE row contributes — total credits stays at 0.5
    assert data["summary"]["total_records"] == 1
    assert float(data["summary"]["total_credits"]) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# unique_wallets — multi-wallet corner case
# ---------------------------------------------------------------------------


def test_credit_detail_summary_unique_wallets_counts_distinct_creators(
    mock_request_user, test_client, app
):
    """Most courses bill against a single wallet (the author's), but
    subscription / proxy-payment / sponsorship scenarios can split charges
    across multiple wallets for the same shifu. The summary must surface
    this as a distinct count so a caller does not treat the per-row
    wallet_creator_bid as "the" wallet for the course (raised on PR #1771
    review of the original `min(creator_bid)` aggregate)."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        # Two charges hit teacher-1's own wallet (the normal case)
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="own1",
            amount=-0.5,
        )
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u2",
            creator_bid="teacher-1",
            suffix="own2",
            amount=-0.3,
        )
        # One charge hit a different wallet (e.g. a platform-credit grant)
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u3",
            creator_bid="sponsor-x",
            suffix="sponsor",
            amount=-1.0,
        )

    response = _post(test_client, {"shifu_bid": "shifu-a"})
    data = response.get_json(force=True)["data"]
    assert data["summary"]["total_records"] == 3
    assert data["summary"]["unique_wallets"] == 2
    # Per-row wallet_creator_bid is preserved so callers can see which
    # wallets paid for which charges.
    row_wallets = {row["wallet_creator_bid"] for row in data["rows"]}
    assert row_wallets == {"teacher-1", "sponsor-x"}


# ---------------------------------------------------------------------------
# Permission / scope enforcement
# ---------------------------------------------------------------------------


def test_credit_detail_user_cannot_query_other_shifu(
    mock_request_user, test_client, app
):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-mine", user_id="teacher-1")
        seed_owned_course(shifu_bid="shifu-other", user_id="teacher-2")
        _seed_usage_with_ledger(
            shifu_bid="shifu-other",
            user_bid="u1",
            creator_bid="teacher-2",
            suffix="1",
            amount=-9.99,
        )

    response = _post(test_client, {"shifu_bid": "shifu-other"})
    payload = response.get_json(force=True)
    assert payload["code"] == 11001  # server.creatorAnalytics.noPermission


def test_credit_detail_results_are_scoped_to_requested_shifu(
    mock_request_user, test_client, app
):
    """Even when the caller owns multiple shifu, only the requested one's
    rows surface — the join is anchored on bill_usage.shifu_bid."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        seed_owned_course(shifu_bid="shifu-b", user_id="teacher-1")
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="a1",
            amount=-1.0,
        )
        _seed_usage_with_ledger(
            shifu_bid="shifu-b",
            user_bid="u2",
            creator_bid="teacher-1",
            suffix="b1",
            amount=-2.0,
        )

    response = _post(test_client, {"shifu_bid": "shifu-a"})
    data = response.get_json(force=True)["data"]
    assert data["summary"]["total_records"] == 1
    assert float(data["summary"]["total_credits"]) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_credit_detail_filters_by_usage_scene(mock_request_user, test_client, app):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="prod",
            amount=-1.0,
            usage_scene=1203,
        )
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="prev",
            amount=-2.0,
            usage_scene=1202,
        )

    response = _post(test_client, {"shifu_bid": "shifu-a", "usage_scene": [1203]})
    data = response.get_json(force=True)["data"]
    assert data["summary"]["total_records"] == 1
    assert all(row["usage_scene"] == 1203 for row in data["rows"])


def test_credit_detail_filters_by_usage_type(mock_request_user, test_client, app):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="llm",
            amount=-1.0,
            usage_type=1101,
        )
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="tts",
            amount=-2.0,
            usage_type=1102,
        )

    response = _post(test_client, {"shifu_bid": "shifu-a", "usage_type": [1101]})
    data = response.get_json(force=True)["data"]
    assert data["summary"]["total_records"] == 1
    assert all(row["usage_type"] == 1101 for row in data["rows"])


def test_credit_detail_filters_by_date_range(mock_request_user, test_client, app):
    """start_date and end_date are inclusive bounds on bill_usage.created_at."""

    mock_request_user(user_id="teacher-1")
    today = datetime(2026, 5, 16, 10, 0, 0)
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="d-15",
            amount=-1.0,
            created_at=today - timedelta(days=1),
        )
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="d-16",
            amount=-2.0,
            created_at=today,
        )
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="d-17",
            amount=-4.0,
            created_at=today + timedelta(days=1),
        )

    response = _post(
        test_client,
        {"shifu_bid": "shifu-a", "start_date": "2026-05-16", "end_date": "2026-05-16"},
    )
    data = response.get_json(force=True)["data"]
    assert data["summary"]["total_records"] == 1
    assert float(data["summary"]["total_credits"]) == pytest.approx(2.0)


def test_credit_detail_rejects_invalid_scene_value(mock_request_user, test_client, app):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")

    response = _post(test_client, {"shifu_bid": "shifu-a", "usage_scene": [9999]})
    payload = response.get_json(force=True)
    assert payload["code"] == 11002  # invalidDsl


def test_credit_detail_rejects_end_before_start(mock_request_user, test_client, app):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "start_date": "2026-05-16",
            "end_date": "2026-05-15",
        },
    )
    assert response.get_json(force=True)["code"] == 11002


# ---------------------------------------------------------------------------
# Pagination + empty edge cases
# ---------------------------------------------------------------------------


def test_credit_detail_pagination(mock_request_user, test_client, app):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        for i in range(5):
            _seed_usage_with_ledger(
                shifu_bid="shifu-a",
                user_bid=f"u{i}",
                creator_bid="teacher-1",
                suffix=str(i),
                amount=-(i + 1) * 0.5,
            )

    response = _post(test_client, {"shifu_bid": "shifu-a", "limit": 2, "offset": 1})
    data = response.get_json(force=True)["data"]
    # Summary aggregates over the full filtered set, not the paginated rows
    assert data["summary"]["total_records"] == 5
    assert len(data["rows"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 1


def test_credit_detail_empty_when_bill_usage_has_no_ledger_entries(
    mock_request_user, test_client, app
):
    """If settlement failed for every usage row (no ledger entry exists),
    the join collapses to zero rows — surfaces as empty summary."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        seed_bill_usage_record(
            usage_bid="u-lonely",
            shifu_bid="shifu-a",
            user_bid="u1",
        )
        # NB: no seed_credit_ledger_entry call — usage exists, but no
        # corresponding ledger row.

    response = _post(test_client, {"shifu_bid": "shifu-a"})
    data = response.get_json(force=True)["data"]
    assert data["summary"]["total_records"] == 0
    assert float(data["summary"]["total_credits"]) == pytest.approx(0.0)
    assert data["summary"]["unique_wallets"] == 0
    assert data["rows"] == []


def test_credit_detail_rejects_limit_above_max(mock_request_user, test_client, app):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")

    # ANALYTICS_QUERY_LIMIT_MAX defaults to 1000; 1001 must reject.
    response = _post(test_client, {"shifu_bid": "shifu-a", "limit": 1001})
    assert response.get_json(force=True)["code"] == 11007  # invalidLimit


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def test_credit_detail_emits_audit_log(
    mock_request_user, test_client, app, monkeypatch
):
    """Each call must log user_id + shifu_bid + row count + filter summary
    so retroactive auditing can reconstruct who hit credit-detail.

    Uses the same `monkeypatch app.logger.info` capture pattern as the
    user_users lookup audit test (see test_query.py) — pytest's caplog
    fixture does not see Flask's per-app logger by default.
    """

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        _seed_usage_with_ledger(
            shifu_bid="shifu-a",
            user_bid="u1",
            creator_bid="teacher-1",
            suffix="1",
            amount=-0.5,
        )

    info_calls: list[tuple] = []
    real_info = app.logger.info
    monkeypatch.setattr(
        app.logger,
        "info",
        lambda *args, **kwargs: (
            info_calls.append((args, kwargs)),
            real_info(*args, **kwargs),
        )[1],
    )

    response = _post(test_client, {"shifu_bid": "shifu-a"})
    assert response.status_code == 200

    audit_entries = [
        args
        for args, _ in info_calls
        if args
        and isinstance(args[0], str)
        and "creator_analytics.credit_detail" in args[0]
    ]
    assert audit_entries, "Expected a credit_detail audit log entry"
    # The first positional arg is the fmt string; subsequent args are the
    # values logger.info substitutes in. user_id / shifu_bid appear as
    # substitution args, not in the fmt string itself.
    first = audit_entries[0]
    assert "teacher-1" in first, f"user_id missing from audit log: {first}"
    assert "shifu-a" in first, f"shifu_bid missing from audit log: {first}"

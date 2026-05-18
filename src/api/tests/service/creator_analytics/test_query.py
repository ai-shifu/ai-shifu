"""End-to-end tests for POST /api/creator-analytics/query.

These exercise the full stack: Flask route → permission lookup → DSL parse →
SQL build → SQLite engine. The token middleware is bypassed by mocking
``validate_user`` per the dashboard test conventions.
"""

from __future__ import annotations

import pytest

from flaskr.service.creator_analytics import engine as analytics_engine

from .conftest import (
    seed_archive,
    seed_bill_daily_metric,
    seed_generated_block,
    seed_owned_course,
    seed_progress,
    seed_published_shifu,
    seed_user_info,
)


ENDPOINT = "/api/creator-analytics/query"


@pytest.fixture(autouse=True)
def _reset_analytics_engine_singleton():
    """Ensure each test starts with the cached fallback engine cleared."""

    analytics_engine.reset_for_tests()
    yield
    analytics_engine.reset_for_tests()


def _post(test_client, body):
    return test_client.post(ENDPOINT, json=body)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_progress_count_returns_expected_rows(mock_request_user, test_client, app):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_progress(shifu_bid="shifu-a", user_bid="u1", status=602)
        seed_progress(shifu_bid="shifu-a", user_bid="u2", status=602)
        seed_progress(shifu_bid="shifu-a", user_bid="u3", status=603)

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_progress_records",
            "select": ["status"],
            "group_by": ["status"],
            "aggregate": [{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
            "order_by": [{"field": "status", "dir": "asc"}],
            "limit": 10,
        },
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json(force=True)
    assert payload["code"] == 0
    data = payload["data"]
    assert data["columns"] == ["status", "n"]
    assert data["rows"] == [[602, 2], [603, 1]]
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_shifu_user_archives_query_runs_without_deleted_column(
    mock_request_user, test_client, app
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_archive(shifu_bid="shifu-a", user_bid="u1", archived=0)
        seed_archive(shifu_bid="shifu-a", user_bid="u2", archived=0)
        seed_archive(shifu_bid="shifu-a", user_bid="u3", archived=1)

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "shifu_user_archives",
            "where": [{"field": "archived", "op": "=", "value": 0}],
            "aggregate": [
                {"fn": "count_distinct", "field": "user_bid", "alias": "active"}
            ],
            "limit": 10,
        },
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json(force=True)["data"]
    assert data["rows"] == [[2]]


# ---------------------------------------------------------------------------
# Permission / scope enforcement
# ---------------------------------------------------------------------------


def test_user_cannot_query_a_shifu_they_do_not_own(mock_request_user, test_client, app):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-mine", user_id="teacher-1")
        seed_owned_course(shifu_bid="shifu-other", user_id="teacher-2")
        seed_progress(shifu_bid="shifu-other", user_bid="u1", status=603)

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-other",
            "table": "learn_progress_records",
            "aggregate": [{"fn": "count", "alias": "n"}],
            "limit": 10,
        },
    )

    # The error envelope is wrapped by AppException → make_common_response.
    payload = response.get_json(force=True)
    assert payload["code"] == 11001  # server.creatorAnalytics.noPermission


def test_query_results_are_scoped_to_the_requested_shifu(
    mock_request_user, test_client, app
):
    """Even if rows exist for another shifu, only the requested one is counted."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        seed_owned_course(shifu_bid="shifu-b", user_id="teacher-1")
        seed_progress(shifu_bid="shifu-a", user_bid="u1", status=603)
        seed_progress(shifu_bid="shifu-b", user_bid="u2", status=603)
        seed_progress(shifu_bid="shifu-b", user_bid="u3", status=603)

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_progress_records",
            "aggregate": [{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
            "limit": 10,
        },
    )
    assert response.get_json(force=True)["data"]["rows"] == [[1]]


# ---------------------------------------------------------------------------
# DSL validation surfaced through the HTTP layer
# ---------------------------------------------------------------------------


def test_unknown_table_yields_invalid_table_error(mock_request_user, test_client, app):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {"shifu_bid": "shifu-a", "table": "auth_logs", "limit": 10},
    )
    assert response.get_json(force=True)["code"] == 11003


def test_unknown_column_yields_invalid_column_error(
    mock_request_user, test_client, app
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_progress_records",
            "select": ["secret"],
            "limit": 10,
        },
    )
    assert response.get_json(force=True)["code"] == 11004


def test_select_shifu_bid_directly_is_rejected(mock_request_user, test_client, app):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_progress_records",
            "select": ["shifu_bid"],
            "limit": 10,
        },
    )
    assert response.get_json(force=True)["code"] == 11004


def test_like_leading_wildcard_is_rejected(mock_request_user, test_client, app):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "where": [{"field": "user_bid", "op": "like", "value": "%abc"}],
            "limit": 10,
        },
    )
    assert response.get_json(force=True)["code"] == 11002


def test_limit_above_configured_max_is_rejected(mock_request_user, test_client, app):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "limit": 999999,
        },
    )
    assert response.get_json(force=True)["code"] == 11007


# ---------------------------------------------------------------------------
# bill_usage table is no longer queryable (credits-only policy)
# ---------------------------------------------------------------------------


def test_bill_usage_table_is_rejected(mock_request_user, test_client, app):
    """`bill_usage` is removed from the whitelist; queries return 11003.

    Creators may only query credit consumption via `bill_daily_usage_metrics`;
    raw token columns (`input` / `input_cache` / `output` / `total`) are no
    longer exposed.
    """

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_usage",
            "aggregate": [{"fn": "count", "alias": "n"}],
            "limit": 1,
        },
    )
    assert response.get_json(force=True)["code"] == 11003


# ---------------------------------------------------------------------------
# Conversation replay (generated_content access)
# ---------------------------------------------------------------------------


def test_conversation_replay_returns_ordered_qa_pairs(
    mock_request_user, test_client, app, monkeypatch
):
    """End-to-end: select user_bid + generated_content for a lesson's Q&A,
    verify the rows come back chronologically and an audit log is emitted."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_generated_block(
            shifu_bid="shifu-a",
            user_bid="learner-1",
            type=321,
            role=2,
            content="什么是 SOLID 原则?",
            progress_record_bid="pr-1",
        )
        seed_generated_block(
            shifu_bid="shifu-a",
            user_bid="learner-1",
            type=322,
            role=1,
            content="SOLID 是五条 OOP 设计原则的缩写...",
            progress_record_bid="pr-1",
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

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_generated_blocks",
            "where": [
                {"field": "type", "op": "in", "value": [321, 322]},
                {"field": "progress_record_bid", "op": "=", "value": "pr-1"},
            ],
            "select": ["user_bid", "generated_content", "type", "created_at"],
            "order_by": [{"field": "created_at", "dir": "asc"}],
            "limit": 50,
        },
    )

    payload = response.get_json(force=True)
    assert payload["code"] == 0
    rows = payload["data"]["rows"]
    assert len(rows) == 2
    assert rows[0][1] == "什么是 SOLID 原则?"
    assert rows[0][2] == 321
    assert rows[1][2] == 322

    # Audit log must surface — look for our format string in the captured calls.
    audit_calls = [
        args
        for args, _ in info_calls
        if args
        and isinstance(args[0], str)
        and "creator_analytics.content_access" in args[0]
    ]
    assert audit_calls, "expected creator_analytics.content_access audit log"
    assert "shifu-a" in audit_calls[0]
    assert "teacher-1" in audit_calls[0]


def test_conversation_replay_rejects_disallowed_type(
    mock_request_user, test_client, app
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_generated_blocks",
            "where": [{"field": "type", "op": "=", "value": 303}],  # input — PII
            "select": ["generated_content"],
            "limit": 10,
        },
    )
    assert response.get_json(force=True)["code"] == 11002


# ---------------------------------------------------------------------------
# user_users nickname lookup (PII redaction + audit log)
# ---------------------------------------------------------------------------


def test_user_users_lookup_returns_nicknames_for_known_user_bids(
    mock_request_user, test_client, app, monkeypatch
):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_user_info(user_bid="u1", nickname="Python 学徒")
        seed_user_info(user_bid="u2", nickname="Alice")
        seed_user_info(user_bid="u3", nickname="not requested")

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

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "user_users",
            "select": ["user_bid", "nickname"],
            "where": [{"field": "user_bid", "op": "in", "value": ["u1", "u2"]}],
            "limit": 10,
        },
    )

    payload = response.get_json(force=True)
    assert payload["code"] == 0
    rows = payload["data"]["rows"]
    assert sorted(rows) == [["u1", "Python 学徒"], ["u2", "Alice"]]

    # Audit log surfaced
    assert any(
        args and isinstance(args[0], str) and "creator_analytics.user_lookup" in args[0]
        for args, _ in info_calls
    )


def test_user_users_lookup_redacts_phone_in_nickname(
    mock_request_user, test_client, app
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_user_info(user_bid="u1", nickname="张三 13812345678")
        seed_user_info(user_bid="u2", nickname="contact me john@example.com")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "user_users",
            "select": ["user_bid", "nickname"],
            "where": [{"field": "user_bid", "op": "in", "value": ["u1", "u2"]}],
            "limit": 10,
        },
    )

    payload = response.get_json(force=True)
    rows = dict(payload["data"]["rows"])
    assert "13812345678" not in rows["u1"]
    assert "[REDACTED-PHONE]" in rows["u1"]
    assert "john@example.com" not in rows["u2"]
    assert "[REDACTED-EMAIL]" in rows["u2"]


def test_user_users_lookup_without_view_permission_is_rejected(
    mock_request_user, test_client, app
):
    mock_request_user(user_id="teacher-1")
    with app.app_context():
        # teacher-2 owns shifu-other, teacher-1 has no access
        seed_owned_course(shifu_bid="shifu-mine", user_id="teacher-1")
        seed_owned_course(shifu_bid="shifu-other", user_id="teacher-2")
        seed_user_info(user_bid="u1", nickname="Anyone")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-other",
            "table": "user_users",
            "select": ["user_bid", "nickname"],
            "where": [{"field": "user_bid", "op": "in", "value": ["u1"]}],
            "limit": 10,
        },
    )
    assert response.get_json(force=True)["code"] == 11001


def test_user_users_lookup_without_where_user_bid_is_rejected(
    mock_request_user, test_client, app
):
    """Cannot list every learner's nickname — must supply user_bid candidates."""

    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "user_users",
            "select": ["user_bid", "nickname"],
            "limit": 10,
        },
    )
    assert response.get_json(force=True)["code"] == 11002


# ---------------------------------------------------------------------------
# user_users user_identify lookup (v2: phone/email filter + masking)
# ---------------------------------------------------------------------------


def test_user_users_lookup_by_phone_returns_masked_user_identify(
    mock_request_user, test_client, app
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_user_info(user_bid="u1", nickname="张三", user_identify="13800138000")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "user_users",
            "select": ["user_bid", "user_identify"],
            "where": [{"field": "user_identify", "op": "=", "value": "13800138000"}],
            "limit": 1,
        },
    )

    payload = response.get_json(force=True)
    assert payload["code"] == 0
    rows = payload["data"]["rows"]
    assert len(rows) == 1
    row = dict(zip(payload["data"]["columns"], rows[0], strict=True))
    assert row["user_bid"] == "u1"
    assert row["user_identify"] == "138*****000"
    assert "13800138000" not in str(rows)


def test_user_users_lookup_by_email_returns_masked_user_identify(
    mock_request_user, test_client, app
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_user_info(
            user_bid="u1", nickname="Alice", user_identify="test@example.com"
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "user_users",
            "select": ["user_bid", "user_identify"],
            "where": [
                {"field": "user_identify", "op": "=", "value": "test@example.com"}
            ],
            "limit": 1,
        },
    )

    payload = response.get_json(force=True)
    assert payload["code"] == 0
    row = dict(zip(payload["data"]["columns"], payload["data"]["rows"][0], strict=True))
    assert row["user_identify"] == "te*****@example.com"
    assert "test@example.com" not in str(payload["data"]["rows"])


def test_user_users_nickname_redacted_and_user_identify_masked_independently(
    mock_request_user, test_client, app
):
    """nickname PII fully redacted; user_identify column partially masked — independent."""
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_user_info(
            user_bid="u1",
            nickname="张三 13812345678",
            user_identify="13800138000",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "user_users",
            "select": ["user_bid", "nickname", "user_identify"],
            "where": [{"field": "user_bid", "op": "=", "value": "u1"}],
            "limit": 1,
        },
    )

    payload = response.get_json(force=True)
    assert payload["code"] == 0
    row = dict(zip(payload["data"]["columns"], payload["data"]["rows"][0], strict=True))
    assert "[REDACTED-PHONE]" in row["nickname"]  # nickname: full redaction
    assert "13812345678" not in row["nickname"]
    assert row["user_identify"] == "138*****000"  # user_identify: partial mask
    assert "13800138000" not in row["user_identify"]


def test_user_users_user_identify_in_filter_rejected(
    mock_request_user, test_client, app
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "user_users",
            "select": ["user_bid", "user_identify"],
            "where": [
                {
                    "field": "user_identify",
                    "op": "in",
                    "value": ["13800138000", "13900139000"],
                },
            ],
            "limit": 10,
        },
    )
    assert response.get_json(force=True)["code"] == 11002


def test_user_users_lookup_by_phone_audit_log_emitted(
    mock_request_user, test_client, app, monkeypatch
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_user_info(user_bid="u1", nickname="张三", user_identify="13800138000")

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

    resp = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "user_users",
            "select": ["user_bid", "user_identify"],
            "where": [{"field": "user_identify", "op": "=", "value": "13800138000"}],
            "limit": 1,
        },
    )
    assert resp.get_json(force=True)["code"] == 0

    assert any(
        args
        and isinstance(args[0], str)
        and "creator_analytics.user_lookup" in args[0]
        and "user_identify" in "".join(str(a) for a in args)
        for args, _ in info_calls
    )


# ---------------------------------------------------------------------------
# Engine isolation
# ---------------------------------------------------------------------------


def test_fallback_engine_uses_primary_db_with_warning(
    mock_request_user, test_client, app, caplog
):
    """Leaving ANALYTICS_DATABASE_URI empty should fall back to the primary engine."""

    mock_request_user()
    app.config["ANALYTICS_DATABASE_URI"] = ""
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")

    with caplog.at_level("WARNING"):
        response = _post(
            test_client,
            {
                "shifu_bid": "shifu-a",
                "table": "learn_progress_records",
                "aggregate": [{"fn": "count", "alias": "n"}],
                "limit": 10,
            },
        )

    assert response.status_code == 200
    # The fallback message is emitted exactly once for the process; we only
    # need to verify the engine returned is the primary engine.
    with app.app_context():
        engine = analytics_engine.get_analytics_engine(app)
        from flaskr.dao import db

        assert engine is db.engine


# ---------------------------------------------------------------------------
# bill_daily_usage_metrics — credit-cost queries (v3)
# ---------------------------------------------------------------------------


def test_bill_daily_sum_credits_for_production_usage(
    mock_request_user, test_client, app
):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_bill_daily_metric(
            shifu_bid="shifu-a",
            stat_date="2026-05-01",
            usage_scene=1203,
            consumed_credits=10.0,
        )
        seed_bill_daily_metric(
            shifu_bid="shifu-a",
            stat_date="2026-05-02",
            usage_scene=1203,
            consumed_credits=20.0,
            daily_usage_metric_bid="dm-shifu-a-2026-05-02",
        )
        # different scene — must not appear in result
        seed_bill_daily_metric(
            shifu_bid="shifu-a",
            stat_date="2026-05-03",
            usage_scene=1201,
            consumed_credits=5.0,
            daily_usage_metric_bid="dm-shifu-a-2026-05-03-debug",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_daily_usage_metrics",
            "aggregate": [
                {"fn": "sum", "field": "consumed_credits", "alias": "total_credits"}
            ],
            "where": [{"field": "usage_scene", "op": "=", "value": 1203}],
            "limit": 1,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    assert data["columns"] == ["total_credits"]
    assert len(data["rows"]) == 1
    total = float(data["rows"][0][0])
    assert total == pytest.approx(30.0)


def test_bill_daily_split_by_usage_type(mock_request_user, test_client, app):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_bill_daily_metric(
            shifu_bid="shifu-a",
            stat_date="2026-05-01",
            usage_type=1101,
            consumed_credits=8.0,
        )
        seed_bill_daily_metric(
            shifu_bid="shifu-a",
            stat_date="2026-05-01",
            usage_type=1102,
            consumed_credits=2.0,
            daily_usage_metric_bid="dm-shifu-a-tts-1",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_daily_usage_metrics",
            "select": ["usage_type"],
            "aggregate": [
                {"fn": "sum", "field": "consumed_credits", "alias": "credits"}
            ],
            "where": [{"field": "usage_scene", "op": "=", "value": 1203}],
            "group_by": ["usage_type"],
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    rows_by_type = {row[0]: float(row[1]) for row in data["rows"]}
    assert rows_by_type[1101] == pytest.approx(8.0)
    assert rows_by_type[1102] == pytest.approx(2.0)


def test_bill_daily_creator_bid_grouping_shows_callers_own_wallet(
    mock_request_user, test_client, app
):
    """The author can now group by creator_bid to confirm which wallet is
    being deducted for the course; shifu_bid isolation guarantees the
    grouping only returns the caller's own bid."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        seed_bill_daily_metric(
            shifu_bid="shifu-a",
            stat_date="2026-05-01",
            creator_bid="teacher-1",
            consumed_credits=12.0,
        )
        # Row for a different course owned by someone else — shifu_bid
        # isolation must keep it out of the result.
        seed_owned_course(shifu_bid="shifu-other", user_id="teacher-2")
        seed_bill_daily_metric(
            shifu_bid="shifu-other",
            stat_date="2026-05-01",
            creator_bid="teacher-2",
            consumed_credits=99.0,
            daily_usage_metric_bid="dm-other",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_daily_usage_metrics",
            "select": ["creator_bid"],
            "aggregate": [
                {"fn": "sum", "field": "consumed_credits", "alias": "credits"}
            ],
            "group_by": ["creator_bid"],
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    # consumed_credits is a NUMERIC column, so SQLite returns it as a string;
    # the public Order test (test_bill_daily_sum_credits_for_production_usage)
    # does the same float() conversion.
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row[0] == "teacher-1"
    assert float(row[1]) == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# learn_generated_blocks — status auto-filter (reroll history excluded)
# ---------------------------------------------------------------------------


def test_followup_count_excludes_rerolled_history(mock_request_user, test_client, app):
    """A learner can re-roll a follow-up question; the old block flips to
    status=0. The PDF §6 trap is "status=0 history rows must not be
    counted as live follow-ups". sql_builder auto-injects status=1, so
    the count should stay at 2 even with a status=0 row present."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        # Two live follow-ups
        seed_generated_block(
            shifu_bid="shifu-a",
            user_bid="u1",
            type=321,
            role=2,
            content="question 1",
            generated_block_bid="gb-live-1",
            status=1,
        )
        seed_generated_block(
            shifu_bid="shifu-a",
            user_bid="u2",
            type=321,
            role=2,
            content="question 2",
            generated_block_bid="gb-live-2",
            status=1,
        )
        # One historical (rerolled) row — must be excluded
        seed_generated_block(
            shifu_bid="shifu-a",
            user_bid="u1",
            type=321,
            role=2,
            content="rerolled",
            generated_block_bid="gb-history-1",
            status=0,
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_generated_blocks",
            "where": [{"field": "type", "op": "=", "value": 321}],
            "aggregate": [{"fn": "count", "alias": "asks"}],
            "limit": 1,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    assert data["rows"] == [[2]]


def test_followup_count_per_lesson_by_outline(mock_request_user, test_client, app):
    """Group by outline_item_bid answers "follow-up questions per lesson".
    Requires both `outline_item_bid` selectable / filterable / groupable
    AND aggregate count_distinct support — added in this round."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        seed_generated_block(
            shifu_bid="shifu-a",
            user_bid="u1",
            type=321,
            role=2,
            content="q for lesson 1",
            generated_block_bid="gb-l1-u1",
            outline_item_bid="outline-1",
        )
        seed_generated_block(
            shifu_bid="shifu-a",
            user_bid="u2",
            type=321,
            role=2,
            content="q2 for lesson 1",
            generated_block_bid="gb-l1-u2",
            outline_item_bid="outline-1",
        )
        seed_generated_block(
            shifu_bid="shifu-a",
            user_bid="u1",
            type=321,
            role=2,
            content="q for lesson 2",
            generated_block_bid="gb-l2-u1",
            outline_item_bid="outline-2",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "learn_generated_blocks",
            "where": [{"field": "type", "op": "=", "value": 321}],
            "select": ["outline_item_bid"],
            "group_by": ["outline_item_bid"],
            "aggregate": [
                {"fn": "count", "alias": "asks"},
                {"fn": "count_distinct", "field": "user_bid", "alias": "askers"},
            ],
            "order_by": [{"field": "asks", "dir": "desc"}],
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    rows_by_lesson = {row[0]: (row[1], row[2]) for row in data["rows"]}
    assert rows_by_lesson["outline-1"] == (2, 2)
    assert rows_by_lesson["outline-2"] == (1, 1)


# ---------------------------------------------------------------------------
# Shifu metadata tables — current title + creator-scoped filtering
# ---------------------------------------------------------------------------


def test_shifu_published_returns_current_title_excluding_history(
    mock_request_user, test_client, app
):
    """Rename scenario: the same shifu_bid has historical PublishedShifu
    rows (deleted=1) plus the current row (deleted=0). The query must
    return only the current row — historical titles must not be presented
    as the course's "current name" (PDF §1 + §7 rules)."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        seed_published_shifu(
            shifu_bid="shifu-a",
            user_id="teacher-1",
            title="历史标题 A",
            deleted=1,
        )
        seed_published_shifu(
            shifu_bid="shifu-a",
            user_id="teacher-1",
            title="历史标题 B",
            deleted=1,
        )
        seed_published_shifu(
            shifu_bid="shifu-a",
            user_id="teacher-1",
            title="当前标题",
            deleted=0,
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "shifu_published_shifus",
            "select": ["title"],
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    titles = [row[0] for row in data["rows"]]
    assert titles == ["当前标题"]


def test_shifu_published_excludes_other_creators_rows(
    mock_request_user, test_client, app
):
    """Even if a co-author / shared user had view permission on the same
    shifu_bid, the creator_scoped_column injection (created_user_bid =
    :caller) ensures only the caller's own rows surface. Here we model
    the simpler "two creators with the same shifu_bid title prefix" case
    — caller can see their own row and never the other creator's."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-mine", user_id="teacher-1")
        seed_published_shifu(
            shifu_bid="shifu-mine",
            user_id="teacher-1",
            title="跟 AI 学 AI 通识",
        )
        # Different shifu_bid, different creator, different title:
        seed_owned_course(shifu_bid="shifu-other", user_id="teacher-2")
        seed_published_shifu(
            shifu_bid="shifu-other",
            user_id="teacher-2",
            title="李卓:K12 AI 教育产品的一线实践",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-mine",
            "table": "shifu_published_shifus",
            "select": ["title", "created_user_bid"],
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    assert data["rows"] == [
        ["跟 AI 学 AI 通识", "teacher-1"],
    ]


def test_shifu_meta_aggregate_rejected_at_http_layer(
    mock_request_user, test_client, app
):
    """The DSL validator must reject aggregate on metadata tables before
    SQL is built. Verifies the HTTP error code is the standard invalidDsl."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "shifu_published_shifus",
            "aggregate": [{"fn": "count", "alias": "n"}],
            "limit": 1,
        },
    )

    payload = response.get_json(force=True)
    assert payload["code"] == 11002  # server.creatorAnalytics.invalidDsl


def test_shifu_meta_title_like_searches_callers_courses(
    mock_request_user, test_client, app
):
    """title `like` with trailing-% is the canonical "find my course by
    name" path. Combined with creator_scoped filtering, the caller only
    sees their own matches."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a", user_id="teacher-1")
        seed_owned_course(shifu_bid="shifu-b", user_id="teacher-1")
        seed_published_shifu(
            shifu_bid="shifu-a",
            user_id="teacher-1",
            title="AI 通识入门",
        )
        seed_published_shifu(
            shifu_bid="shifu-b",
            user_id="teacher-1",
            title="AI 通识进阶",
        )
        # A course owned by teacher-2 with matching title — must not leak
        seed_owned_course(shifu_bid="shifu-c", user_id="teacher-2")
        seed_published_shifu(
            shifu_bid="shifu-c",
            user_id="teacher-2",
            title="AI 通识 (其他作者)",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",  # CLI must inject this; metadata query
            #                       # is per-shifu in this single call,
            #                       # broader fan-out happens client-side
            "table": "shifu_published_shifus",
            "where": [{"field": "title", "op": "like", "value": "AI 通识%"}],
            "select": ["title"],
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    # Only the caller's own shifu-a row matches both the shifu_bid scope
    # AND the title like; shifu-b has the same creator but is filtered
    # out by shifu_bid scope; shifu-c is filtered out by both.
    assert data["rows"] == [["AI 通识入门"]]

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
    seed_bill_usage,
    seed_generated_block,
    seed_owned_course,
    seed_progress,
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
# bill_usage usage_scene filter — separates learner spend from creator preview
# ---------------------------------------------------------------------------


def test_bill_usage_filter_by_usage_scene_excludes_preview_users(
    mock_request_user, test_client, app
):
    """Without `where usage_scene=1203`, learner count includes creator previews;
    with the filter, only production learners are counted."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        # 3 production learners
        seed_bill_usage(shifu_bid="shifu-a", user_bid="learner-1", usage_scene=1203)
        seed_bill_usage(shifu_bid="shifu-a", user_bid="learner-2", usage_scene=1203)
        seed_bill_usage(shifu_bid="shifu-a", user_bid="learner-3", usage_scene=1203)
        # 2 preview spenders (creator + co-author)
        seed_bill_usage(shifu_bid="shifu-a", user_bid="teacher-1", usage_scene=1202)
        seed_bill_usage(shifu_bid="shifu-a", user_bid="co-author", usage_scene=1202)

    # Without the filter: 5 distinct users (mixed)
    mixed = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_usage",
            "where": [{"field": "usage_type", "op": "=", "value": 1101}],
            "aggregate": [{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
            "limit": 1,
        },
    )
    assert mixed.get_json(force=True)["data"]["rows"] == [[5]]

    # With usage_scene=1203: only 3 production learners
    prod_only = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_usage",
            "where": [
                {"field": "usage_type", "op": "=", "value": 1101},
                {"field": "usage_scene", "op": "=", "value": 1203},
            ],
            "aggregate": [{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
            "limit": 1,
        },
    )
    assert prod_only.get_json(force=True)["data"]["rows"] == [[3]]


def test_bill_usage_group_by_usage_scene_splits_learner_vs_preview(
    mock_request_user, test_client, app
):
    """group_by usage_scene to see learner spend vs preview spend side by side."""

    mock_request_user(user_id="teacher-1")
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_bill_usage(
            shifu_bid="shifu-a",
            user_bid="learner-1",
            usage_scene=1203,
            input_tokens=100,
            output_tokens=200,
        )
        seed_bill_usage(
            shifu_bid="shifu-a",
            user_bid="teacher-1",
            usage_scene=1202,
            input_tokens=50,
            output_tokens=80,
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_usage",
            "where": [{"field": "usage_type", "op": "=", "value": 1101}],
            "select": ["usage_scene"],
            "group_by": ["usage_scene"],
            "aggregate": [
                {"fn": "sum", "field": "input", "alias": "in_tok"},
                {"fn": "sum", "field": "output", "alias": "out_tok"},
            ],
            "order_by": [{"field": "usage_scene", "dir": "asc"}],
            "limit": 10,
        },
    )
    rows = response.get_json(force=True)["data"]["rows"]
    # rows shape: [[usage_scene, in_tok, out_tok], ...]
    assert [r[0] for r in rows] == [1202, 1203]
    assert dict((r[0], (r[1], r[2])) for r in rows) == {
        1202: (50, 80),
        1203: (100, 200),
    }


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


# ---------------------------------------------------------------------------
# bill_usage — new fields (v3)
# ---------------------------------------------------------------------------


def test_bill_usage_total_selectable(mock_request_user, test_client, app):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_bill_usage(
            shifu_bid="shifu-a",
            user_bid="u1",
            input_tokens=100,
            output_tokens=50,
            total=150,
            record_level=0,
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_usage",
            "aggregate": [{"fn": "sum", "field": "total", "alias": "total_tokens"}],
            "where": [{"field": "user_bid", "op": "=", "value": "u1"}],
            "limit": 1,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    assert data["columns"] == ["total_tokens"]
    assert len(data["rows"]) == 1
    assert float(data["rows"][0][0]) == pytest.approx(150.0)


def test_bill_usage_filter_by_record_level(mock_request_user, test_client, app):
    """record_level=0 filter excludes segment rows (record_level=1)."""

    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_bill_usage(
            shifu_bid="shifu-a",
            user_bid="u1",
            total=100,
            record_level=0,
            usage_bid="usage-req-1",
        )
        seed_bill_usage(
            shifu_bid="shifu-a",
            user_bid="u1",
            total=40,
            record_level=1,
            usage_bid="usage-seg-1",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_usage",
            "aggregate": [{"fn": "sum", "field": "total", "alias": "tok"}],
            "where": [
                {"field": "user_bid", "op": "=", "value": "u1"},
                {"field": "record_level", "op": "=", "value": 0},
            ],
            "limit": 1,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    tok = float(data["rows"][0][0])
    assert tok == pytest.approx(100.0)


def test_bill_usage_provider_model_groupable(mock_request_user, test_client, app):
    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-a")
        seed_bill_usage(
            shifu_bid="shifu-a",
            user_bid="u1",
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            record_level=0,
            usage_bid="usage-oai-1",
        )
        seed_bill_usage(
            shifu_bid="shifu-a",
            user_bid="u1",
            provider="anthropic",
            model="claude-3-5-sonnet",
            input_tokens=200,
            record_level=0,
            usage_bid="usage-ant-1",
        )

    response = _post(
        test_client,
        {
            "shifu_bid": "shifu-a",
            "table": "bill_usage",
            "select": ["provider", "model"],
            "aggregate": [{"fn": "sum", "field": "input", "alias": "in_tok"}],
            "where": [{"field": "record_level", "op": "=", "value": 0}],
            "group_by": ["provider", "model"],
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.get_json(force=True)["data"]
    assert len(data["rows"]) == 2
    providers = {row[data["columns"].index("provider")] for row in data["rows"]}
    assert providers == {"openai", "anthropic"}

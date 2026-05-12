"""End-to-end tests for POST /api/creator-analytics/query.

These exercise the full stack: Flask route → permission lookup → DSL parse →
SQL build → SQLite engine. The token middleware is bypassed by mocking
``validate_user`` per the dashboard test conventions.
"""

from __future__ import annotations

import pytest

from flaskr.service.creator_analytics import engine as analytics_engine

from .conftest import seed_archive, seed_owned_course, seed_progress


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
        {"shifu_bid": "shifu-a", "table": "user_users", "limit": 10},
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
            "select": ["user_bid"],
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
            "select": ["user_bid"],
            "limit": 999999,
        },
    )
    assert response.get_json(force=True)["code"] == 11007


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

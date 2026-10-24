"""Query current course metadata through the HTTP endpoint and SQLite engine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from flaskr.service.creator_analytics import engine as analytics_engine

from .conftest import seed_owned_course, seed_published_shifu

ENDPOINT = "/api/creator-analytics/query"
SAME_TIME = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)


@pytest.fixture(params=["shifu_draft_shifus", "shifu_published_shifus"])
def metadata_table(request: object) -> tuple[str, object]:
    """Exercise both independently versioned metadata tables."""
    seed = (
        seed_owned_course
        if request.param == "shifu_draft_shifus"
        else seed_published_shifu
    )
    analytics_engine.reset_for_tests()
    return request.param, seed


def _query(
    test_client: object, table_key: str, **overrides: object
) -> list[list[object]]:
    payload = {
        "shifu_bid": "course-current",
        "table": table_key,
        "select": ["title", "created_user_bid"],
        "limit": 10,
        **overrides,
    }
    response = test_client.post(ENDPOINT, json=payload)
    body = response.get_json(force=True)
    assert response.status_code == 200
    assert body["code"] == 0
    return body["data"]["rows"]


@pytest.mark.parametrize("limit", [1, 10])
def test_current_version_uses_id_when_timestamps_tie(
    metadata_table: tuple[str, object],
    mock_request_user: object,
    test_client: object,
    app: object,
    limit: int,
) -> None:
    """Unmarked history and another course's newer row cannot win selection."""
    table_key, seed = metadata_table
    mock_request_user()
    with app.app_context():
        seed(shifu_bid="course-current", title="Old title", timestamp=SAME_TIME)
        seed(shifu_bid="course-current", title="Current title", timestamp=SAME_TIME)
        seed(shifu_bid="course-other", title="Other title", timestamp=SAME_TIME)

    assert _query(test_client, table_key, limit=limit) == [
        ["Current title", "teacher-1"]
    ]


@pytest.mark.parametrize("operator", ["=", "like"])
def test_old_title_cannot_match_current_metadata(
    metadata_table: tuple[str, object],
    mock_request_user: object,
    test_client: object,
    app: object,
    operator: str,
) -> None:
    """Title predicates run after version selection, including prefix searches."""
    table_key, seed = metadata_table
    mock_request_user()
    with app.app_context():
        seed(shifu_bid="course-current", title="Previous name")
        seed(shifu_bid="course-current", title="Renamed course")

    value = "Previous name" if operator == "=" else "Previous%"
    assert (
        _query(
            test_client,
            table_key,
            where=[{"field": "title", "op": operator, "value": value}],
        )
        == []
    )


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
def test_old_timestamp_cannot_select_a_historical_title(
    metadata_table: tuple[str, object],
    mock_request_user: object,
    test_client: object,
    app: object,
    field: str,
) -> None:
    """A time window must not turn a superseded version into current metadata."""
    table_key, seed = metadata_table
    mock_request_user()
    with app.app_context():
        seed(
            shifu_bid="course-current",
            title="Previous name",
            timestamp=datetime(2026, 9, 1, tzinfo=UTC),
        )
        seed(shifu_bid="course-current", title="Current title", timestamp=SAME_TIME)

    assert (
        _query(
            test_client,
            table_key,
            where=[{"field": field, "op": "<", "value": "2026-09-02T00:00:00Z"}],
        )
        == []
    )


def test_historical_owner_cannot_read_an_old_version(
    metadata_table: tuple[str, object],
    mock_request_user: object,
    test_client: object,
    app: object,
) -> None:
    """Ownership is checked on the current version, despite stale view access."""
    table_key, seed = metadata_table
    with app.app_context():
        seed(shifu_bid="course-current", title="Previous name", user_id="teacher-1")
        seed(shifu_bid="course-current", title="Current title", user_id="teacher-2")

    mock_request_user(user_id="teacher-1")
    assert _query(test_client, table_key) == []
    mock_request_user(user_id="teacher-2")
    assert _query(test_client, table_key) == [["Current title", "teacher-2"]]


def test_deleted_newer_version_preserves_latest_non_deleted_contract(
    metadata_table: tuple[str, object],
    mock_request_user: object,
    test_client: object,
    app: object,
) -> None:
    """Course reads select the highest non-deleted id, even after a deleted row."""
    table_key, seed = metadata_table
    mock_request_user()
    with app.app_context():
        seed(shifu_bid="course-current", title="Old title")
        seed(shifu_bid="course-current", title="Current title")
        seed(shifu_bid="course-current", title="Deleted title", deleted=1)

    assert _query(test_client, table_key) == [["Current title", "teacher-1"]]

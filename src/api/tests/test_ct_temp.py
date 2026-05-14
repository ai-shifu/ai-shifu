def test_content_type_check(mock_request_user, test_client, app):
    from tests.service.creator_analytics.conftest import (
        seed_owned_course,
        seed_progress,
    )

    mock_request_user()
    with app.app_context():
        seed_owned_course(shifu_bid="shifu-ct")
        seed_progress(shifu_bid="shifu-ct", user_bid="u1", status=602)

    resp = test_client.post(
        "/api/creator-analytics/query",
        json={
            "shifu_bid": "shifu-ct",
            "table": "learn_progress_records",
            "aggregate": [{"fn": "count", "alias": "n"}],
            "limit": 1,
        },
    )
    import sys

    sys.stderr.write(f"STATUS: {resp.status_code}\n")
    sys.stderr.write(f"CONTENT_TYPE: {resp.content_type}\n")
    sys.stderr.write(f"GET_JSON: {resp.get_json()}\n")
    sys.stderr.write(f"FORCE_JSON: {resp.get_json(force=True)}\n")
    sys.stderr.flush()
    assert True

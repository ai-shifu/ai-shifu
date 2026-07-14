"""Golden JSON fixtures for key non-SSE endpoints.

Each case performs a cheap authenticated GET against the seeded golden shifu
(or a global endpoint), normalizes the full response envelope
(``{code, message, data}``) with the shared normalizer, and compares it to a
recorded fixture under ``tests/golden/fixtures/``.

Endpoints covered in this first batch:

- ``GET /health``                                             (health check)
- ``GET /api/learn/shifu/<shifu_bid>``                        (shifu info)
- ``GET /api/learn/shifu/<shifu_bid>/outline-item-tree``      (outline tree)
- ``GET /api/learn/shifu/<shifu_bid>/run/<outline_bid>``      (run status)
- ``GET /api/learn/shifu/<shifu_bid>/records/<outline_bid>``  (learn records)
- ``GET /api/user/get_profile?course_id=<shifu_bid>``         (profile labels)
- ``GET /api/user/onboarding/status``                         (onboarding)

The corpus intentionally starts small and grows in later batches toward the
~30-endpoint contract-test corpus described in the backend overhaul master
plan (Phase 0 / reused in Phase 3).

Update mode: ``UPDATE_GOLDEN=1 pytest tests/golden/`` rewrites the fixtures.
"""

from __future__ import annotations

import pytest

from tests.golden.conftest import (
    GOLDEN_LESSON_BID,
    GOLDEN_SHIFU_BID,
    assert_or_update_golden,
    mock_validate_user,
    seed_golden_user,
)
from tests.golden.normalize import IdNormalizer, normalize_json_payload

JSON_USER_BID = "golden-user-json-0001"

JSON_GOLDEN_CASES = [
    ("health", "/health"),
    ("shifu_info", f"/api/learn/shifu/{GOLDEN_SHIFU_BID}?preview_mode=false"),
    (
        "outline_item_tree",
        f"/api/learn/shifu/{GOLDEN_SHIFU_BID}/outline-item-tree?preview_mode=false",
    ),
    ("run_status", f"/api/learn/shifu/{GOLDEN_SHIFU_BID}/run/{GOLDEN_LESSON_BID}"),
    (
        "learn_records",
        f"/api/learn/shifu/{GOLDEN_SHIFU_BID}/records/{GOLDEN_LESSON_BID}"
        "?preview_mode=false",
    ),
    ("user_profile", f"/api/user/get_profile?course_id={GOLDEN_SHIFU_BID}"),
    ("onboarding_status", "/api/user/onboarding/status"),
]


@pytest.mark.parametrize(
    "fixture_key,path",
    JSON_GOLDEN_CASES,
    ids=[case[0] for case in JSON_GOLDEN_CASES],
)
def test_json_endpoint_golden(
    app, test_client, monkeypatch, golden_shifu, fixture_key, path
):
    seed_golden_user(app, JSON_USER_BID)
    mock_validate_user(monkeypatch, JSON_USER_BID)

    response = test_client.get(path, headers={"Token": "golden-token"})
    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload is not None
    assert payload.get("code") == 0, f"{path} returned business error: {payload}"

    assert_or_update_golden(
        f"api_{fixture_key}.json",
        normalize_json_payload(payload, IdNormalizer()),
    )

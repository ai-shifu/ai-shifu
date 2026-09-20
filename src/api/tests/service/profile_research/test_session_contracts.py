"""Regression coverage for the accompanying runtime fix."""

import json

import pytest
from flaskr.service.profile_research import session as sessions

from tests.service.profile_research.test_runtime import (
    _make_runtime,
    _start_test_session,
)


@pytest.mark.parametrize("raw", ["{", "null", "[]", "1", b"{}", b"\xff"])
def test_invalid_cache_payload_fails_closed_without_refresh(raw: object) -> None:
    _app, runtime, _providers = _make_runtime()
    cache = runtime.store._cache
    key = runtime.store._key("corrupt")
    cache.setex(key, 30, raw)
    stored = cache.get(key)
    with pytest.raises(sessions.ProfileResearchSessionNotFound):
        runtime.store.load("corrupt")
    assert cache.get(key) == stored


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": 0},
        {"schema_version": "invalid"},
        {"last_events": 1},
        {"variables": []},
        {"context": {}},
        {"block_index": "invalid"},
        {"last_expected_block_index": "invalid"},
    ],
)
def test_cached_state_validation_rejects_incompatible_fields(overrides: dict) -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    payload = runtime.store.load(view["session_id"]).to_cache_payload()
    payload.update(overrides)
    with pytest.raises(sessions.ProfileResearchSessionNotFound):
        sessions._ProfileResearchSession.from_cache_payload(payload)


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "config_revision",
        "block_index",
        "block_count",
        "profile_draft_block_index",
        "last_expected_block_index",
    ],
)
@pytest.mark.parametrize("number", ["Infinity", "-Infinity", "1e309", "-1e309"])
def test_nonfinite_cached_integer_fields_fail_as_missing_sessions(
    field: str, number: str
) -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    key = runtime.store._key(view["session_id"])
    payload = runtime.store.load(view["session_id"]).to_cache_payload()
    payload[field] = "nonfinite-placeholder"
    raw = json.dumps(payload).replace('"nonfinite-placeholder"', number)
    runtime.store._cache.setex(key, 30, raw)
    with pytest.raises(sessions.ProfileResearchSessionNotFound) as error:
        runtime.store.load(view["session_id"])
    assert error.value.public_code == "transient_markdownflow_session_not_found"
    assert runtime.store._cache.get(key) == raw.encode("utf-8")

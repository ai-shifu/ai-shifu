"""Verify profile-research cache corruption, admission, and lock recovery."""

import json
from unittest.mock import Mock

import pytest
from flaskr.service.profile_research import session as sessions
from flaskr.service.profile_research.runtime import ProfileResearchRuntime
from markdown_flow import USER_ANSWER_CONTEXT_KEY

from tests.service.profile_research.test_runtime import (
    _assistant_runtime,
    _import_answers,
    _make_runtime,
    _save_session_without_active_pointer,
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


def test_cache_normalizes_legacy_variables_and_filters_invalid_context_messages() -> (
    None
):
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    payload = runtime.store.load(view["session_id"]).to_cache_payload()
    payload.update(
        variables={1: 2, "answers": [3, False], "empty": None},
        context=[
            None,
            {"role": "", "content": "ignore"},
            {"role": "user", "content": " "},
            {"role": "assistant", "content": "Question", USER_ANSWER_CONTEXT_KEY: 7},
        ],
        last_events=None,
    )
    restored = sessions._ProfileResearchSession.from_cache_payload(payload)
    assert restored.variables == {"1": "2", "answers": ["3", "False"]}
    assert restored.context == [
        {"role": "assistant", "content": "Question", USER_ANSWER_CONTEXT_KEY: "7"}
    ]
    assert restored.last_events == []
    assert sessions._normalize_session_variables(None) == {}
    assert sessions._normalize_session_context(None) == []


@pytest.mark.parametrize(
    "user_input",
    [
        [],
        {1: ["value"]},
        {"": ["value"]},
        {"key": [1]},
        {"a": ["x"] * 51, "b": ["y"] * 50},
        {"a": ["x" * 4000], "b": ["x" * 4000], "c": ["x" * 2001]},
    ],
)
def test_invalid_learner_input_is_rejected_before_any_provider_work(
    user_input: object,
) -> None:
    _app, runtime, providers = _make_runtime()
    view = _start_test_session(runtime)
    with pytest.raises(sessions.ProfileResearchValidationError):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=view["session_id"],
                user_input=user_input,
                expected_purpose=sessions.PROFILE_ONBOARDING_PURPOSE,
            )
        )
    assert providers == []
    assert runtime.store.load(view["session_id"]).block_index == 0


@pytest.mark.parametrize(
    "overrides",
    [{"user_bid": " "}, {"purpose": "invalid"}, {"config_revision": "bad"}],
)
def test_invalid_start_identity_or_revision_creates_no_active_session(
    overrides: dict,
) -> None:
    _app, runtime, providers = _make_runtime()
    kwargs = {
        "user_bid": "user-1",
        "document": "?[Continue]",
        "purpose": sessions.PROFILE_ONBOARDING_PURPOSE,
        "config_revision": 1,
        "output_language": None,
    }
    kwargs.update(overrides)
    with pytest.raises(sessions.ProfileResearchValidationError):
        runtime.start_session(**kwargs)
    assert providers == []
    assert (
        runtime.store.active_session_id(
            user_bid="user-1", purpose=sessions.PROFILE_ONBOARDING_PURPOSE
        )
        is None
    )


@pytest.mark.parametrize(
    ("config_key", "value"),
    [
        ("DEFAULT_LLM_MODEL", " "),
        ("DEFAULT_LLM_TEMPERATURE", "invalid"),
        ("DEFAULT_LLM_TEMPERATURE", -0.1),
        ("DEFAULT_LLM_TEMPERATURE", 2.1),
    ],
)
def test_invalid_runtime_configuration_cannot_replace_active_session(
    config_key: str, value: object
) -> None:
    app, runtime, _providers = _make_runtime()
    original = _start_test_session(runtime)
    app.config[config_key] = value
    with pytest.raises(sessions.ProfileResearchValidationError):
        _start_test_session(runtime)
    assert (
        runtime.store.active_session_id(
            user_bid="user-1", purpose=sessions.PROFILE_ONBOARDING_PURPOSE
        )
        == original["session_id"]
    )


@pytest.mark.parametrize(
    ("request_id", "expected_index"),
    [(None, 0), ("request", None), (" ", 0), ("x" * 129, 0)],
)
def test_replay_requires_valid_request_identity_pair(
    request_id: str | None, expected_index: int | None
) -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    session = runtime.store.load(view["session_id"])
    with pytest.raises(sessions.ProfileResearchValidationError):
        ProfileResearchRuntime._replay_or_validate_request(
            session,
            request_id=request_id,
            expected_block_index=expected_index,
            user_input={},
        )


@pytest.mark.parametrize("field", ["block_count", "block_index"])
def test_corrupt_cursor_does_not_publish_partial_state_and_releases_owner_lock(
    field: str,
) -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    session = runtime.store.load(view["session_id"])
    setattr(session, field, -1)
    runtime.store.save(session)
    with pytest.raises(sessions.ProfileResearchSessionNotFound):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=session.session_id,
                user_input=None,
                expected_purpose=sessions.PROFILE_ONBOARDING_PURPOSE,
            )
        )
    assert getattr(runtime.store.load(session.session_id), field) == -1
    lock = runtime.store.owner_lock(
        user_bid="user-1", purpose=sessions.PROFILE_ONBOARDING_PURPOSE
    )
    assert lock.acquire(blocking=False) is True
    lock.release()


def test_busy_session_lock_releases_owner_admission_for_a_later_run() -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    lock = runtime.store.lock(view["session_id"])
    assert lock.acquire(blocking=False) is True
    with pytest.raises(sessions.ProfileResearchSessionBusy):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=view["session_id"],
                user_input=None,
                expected_purpose=sessions.PROFILE_ONBOARDING_PURPOSE,
            )
        )
    lock.release()
    events = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=view["session_id"],
            user_input=None,
            expected_purpose=sessions.PROFILE_ONBOARDING_PURPOSE,
        )
    )
    assert events[-1]["is_terminal"] is True


def test_lock_release_failure_does_not_mask_the_original_run_error() -> None:
    lock = Mock()
    lock.acquire.return_value = True
    lock.release.side_effect = RuntimeError("lost lease")
    message = "original failure"
    with (
        pytest.raises(ValueError, match="original failure"),
        sessions._hold_profile_research_lock(lock),
    ):
        raise ValueError(message)
    lock.release.assert_called_once()


def test_implicit_purpose_delete_and_absent_active_session_are_idempotent() -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    runtime.delete_session(
        user_bid="user-1", session_id=view["session_id"], expected_purpose=None
    )
    runtime.delete_active_session(
        user_bid="user-1", purpose=sessions.PROFILE_ONBOARDING_PURPOSE
    )
    with pytest.raises(sessions.ProfileResearchSessionNotFound):
        runtime.store.load(view["session_id"])
    with pytest.raises(sessions.ProfileResearchSessionNotFound):
        runtime.delete_active_session(
            user_bid="", purpose=sessions.PROFILE_ONBOARDING_PURPOSE
        )


def test_corrupt_cached_purpose_cannot_be_resolved_implicitly() -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    session = runtime.store.load(view["session_id"])
    payload = session.to_cache_payload()
    payload["purpose"] = "unknown"
    runtime.store._cache.setex(
        runtime.store._key(session.session_id), 30, json.dumps(payload)
    )
    with pytest.raises(sessions.ProfileResearchSessionNotFound):
        runtime.delete_session(
            user_bid="user-1", session_id=session.session_id, expected_purpose=None
        )


def test_content_block_rejects_unsolicited_answers_without_advancing() -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(
        runtime, document="Explain the process.\n\n---\n\n?[Continue]"
    )
    with pytest.raises(sessions.ProfileResearchValidationError, match="not expected"):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=view["session_id"],
                user_input={"input": ["answer"]},
                expected_purpose=sessions.PROFILE_ONBOARDING_PURPOSE,
            )
        )
    assert runtime.store.load(view["session_id"]).block_index == 0


def test_empty_profile_summary_does_not_complete_the_session() -> None:
    _app, runtime, _providers = _make_runtime(output_chunks=[" "])
    view = _start_test_session(runtime)
    session = runtime.store.load(view["session_id"])
    session.block_index = session.profile_draft_block_index
    runtime.store.save(session)
    with pytest.raises(sessions.ProfileResearchError, match="draft is empty"):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=session.session_id,
                user_input=None,
                expected_purpose=sessions.PROFILE_ONBOARDING_PURPOSE,
            )
        )
    stored = runtime.store.load(session.session_id)
    assert stored.done is False
    assert stored.profile_draft == ""
    assert stored.block_index == session.profile_draft_block_index


def test_assistant_import_cannot_write_a_session_replaced_by_a_new_owner_session() -> (
    None
):
    app, runtime, view, providers = _assistant_runtime()
    previous = runtime.store.load(view["session_id"])
    current = _start_test_session(runtime)
    _save_session_without_active_pointer(runtime, previous)
    with app.app_context(), pytest.raises(sessions.ProfileResearchSessionNotFound):
        _import_answers(runtime, view)
    assert providers == []
    assert (
        runtime.store.active_session_id(
            user_bid="user-1", purpose=sessions.PROFILE_ONBOARDING_PURPOSE
        )
        == current["session_id"]
    )


def test_assistant_import_rejects_oversized_collected_nickname_without_staging_answers() -> (
    None
):
    app, runtime, view, providers = _assistant_runtime()
    session = runtime.store.load(view["session_id"])
    session.variables["sys_user_nickname"] = "x" * 1000
    runtime.store.save(session)
    before = session.to_cache_payload()
    with (
        app.app_context(),
        pytest.raises(
            sessions.ProfileResearchValidationError, match="nickname is too long"
        ),
    ):
        _import_answers(runtime, view)
    assert runtime.store.load(session.session_id).to_cache_payload() == before
    assert len(providers) == 1


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


@pytest.mark.parametrize(
    "user_input",
    [
        False,
        0,
        [],
        "answer",
        ["answer"],
        {"input": "answer"},
        {"input": [1]},
        {"input": [" "]},
        {"input": []},
        {"": ["answer"]},
        {"input": ["x" * 4_001]},
    ],
)
def test_corrupt_replay_input_is_reported_as_missing_session_and_does_not_prevent_restart(
    user_input: object,
) -> None:
    _app, runtime, providers = _make_runtime()
    previous = _start_test_session(runtime)
    key = runtime.store._key(previous["session_id"])
    payload = runtime.store.load(previous["session_id"]).to_cache_payload()
    payload["last_user_input"] = user_input
    raw = json.dumps(payload)
    runtime.store._cache.setex(key, 30, raw)
    with pytest.raises(sessions.ProfileResearchSessionNotFound) as error:
        runtime.store.load(previous["session_id"])
    assert error.value.public_code == "transient_markdownflow_session_not_found"
    assert runtime.store._cache.get(key) == raw.encode("utf-8")
    replacement = _start_test_session(runtime)
    assert replacement["session_id"] != previous["session_id"]
    assert (
        runtime.store.active_session_id(
            user_bid="user-1", purpose=sessions.PROFILE_ONBOARDING_PURPOSE
        )
        == replacement["session_id"]
    )
    assert runtime.store.load(replacement["session_id"]).last_user_input == {}
    assert providers == []


@pytest.mark.parametrize("user_input", [None, {}, {"input": ["valid", "0"]}])
def test_valid_cached_replay_input_keeps_its_existing_shape(user_input: object) -> None:
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    payload = runtime.store.load(view["session_id"]).to_cache_payload()
    payload["last_user_input"] = user_input
    restored = sessions._ProfileResearchSession.from_cache_payload(payload)
    assert restored.last_user_input == (user_input or {})

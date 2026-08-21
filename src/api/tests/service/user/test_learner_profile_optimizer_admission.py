"""Verify learner profile optimizer admission behavior."""

from __future__ import annotations

import pytest
from flaskr import dao
from flaskr.service.common.models import AppError
from flaskr.service.profile import learner_profile_optimizer_admission as admission


class FakeRedis:
    """Simulate Redis behavior for tests."""

    def __init__(self) -> None:
        """Track in-flight admission tokens and requested acquisition TTLs."""
        self.in_flight_tokens: dict[str, str] = {}
        self.acquire_ttls: list[int] = []

    def eval(self, script, numkeys, *args: object):
        assert numkeys == 1
        key = str(args[0])
        token = str(args[1])
        if script == admission._ACQUIRE_ADMISSION_SCRIPT:
            self.acquire_ttls.append(int(args[2]))
            if key in self.in_flight_tokens:
                return 0
            self.in_flight_tokens[key] = token
            return 1

        assert script == admission._RELEASE_ADMISSION_SCRIPT
        if self.in_flight_tokens.get(key) == token:
            self.in_flight_tokens.pop(key, None)
            return 1
        return 0

    def expire_in_flight(self) -> None:
        self.in_flight_tokens.clear()


class ExplodingRedis:
    """Simulate a Redis failure for tests."""

    def eval(self, *_args: object, **_kwargs):
        message = "redis unavailable"
        raise RuntimeError(message)


@pytest.fixture(autouse=True)
def reset_local_admission_state():
    with admission._local_lock:
        admission._local_in_flight_state.clear()
    yield
    with admission._local_lock:
        admission._local_in_flight_state.clear()


def _assert_admission_denied(app, *, user_id: str) -> None:
    message = "denied admission must not enter the request body"
    with (
        pytest.raises(AppError) as raised,
        admission.learner_profile_optimization_admission(
            app,
            user_id=user_id,
        ),
    ):
        raise AssertionError(message)
    assert raised.value.code == 1023


def test_admission_allows_only_one_in_flight_request_per_user(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake_redis)

    with admission.learner_profile_optimization_admission(
        app,
        user_id="concurrent-user",
    ):
        _assert_admission_denied(app, user_id="concurrent-user")

    with admission.learner_profile_optimization_admission(
        app,
        user_id="concurrent-user",
    ):
        pass

    assert fake_redis.acquire_ttls == [admission.IN_FLIGHT_TTL_SECONDS] * 3


def test_admission_does_not_group_different_users(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake_redis)

    with (
        admission.learner_profile_optimization_admission(app, user_id="user-one"),
        admission.learner_profile_optimization_admission(app, user_id="user-two"),
    ):
        pass


def test_admission_releases_slot_after_request_error(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake_redis)

    message = "provider failed"
    with (
        pytest.raises(RuntimeError, match="provider failed"),
        admission.learner_profile_optimization_admission(
            app,
            user_id="error-user",
        ),
    ):
        raise RuntimeError(message)

    with admission.learner_profile_optimization_admission(
        app,
        user_id="error-user",
    ):
        pass


def test_expired_lease_release_cannot_remove_replacement_redis_slot(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake_redis)

    first = admission._acquire_admission(app, user_id="ttl-race-user")
    fake_redis.expire_in_flight()
    replacement = admission._acquire_admission(app, user_id="ttl-race-user")

    admission._release_admission(app, first)
    _assert_admission_denied(app, user_id="ttl-race-user")

    admission._release_admission(app, replacement)


def test_configured_redis_failure_denies_request_without_logging_identity(
    app, monkeypatch, caplog
):
    sentinel_identity = "SENSITIVE_ADMISSION_IDENTITY"
    monkeypatch.setattr(dao._redis_state, "client", ExplodingRedis())

    app.logger.addHandler(caplog.handler)
    try:
        _assert_admission_denied(app, user_id=sentinel_identity)
    finally:
        app.logger.removeHandler(caplog.handler)

    assert "denying request" in caplog.text
    assert sentinel_identity not in caplog.text


def test_missing_redis_uses_process_local_user_slot(app, monkeypatch):
    monkeypatch.setattr(dao._redis_state, "client", None)

    with admission.learner_profile_optimization_admission(
        app,
        user_id="local-user",
    ):
        _assert_admission_denied(app, user_id="local-user")
        with admission.learner_profile_optimization_admission(
            app,
            user_id="another-local-user",
        ):
            pass

    with admission.learner_profile_optimization_admission(
        app,
        user_id="local-user",
    ):
        pass

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flaskr.service.common.models import AppException
from flaskr.service.profile import learner_profile_optimizer_admission as admission


class FakeRedis:
    def __init__(self):
        self.rate_counters: dict[str, int] = {}
        self.in_flight_tokens: dict[str, set[str]] = {}
        self.acquire_ttls: list[int] = []

    def eval(self, _script, numkeys, *args):
        keys = args[:numkeys]
        if numkeys == 4:
            limits = tuple(int(value) for value in args[4:8])
            token = str(args[10])
            self.acquire_ttls.append(int(args[9]))
            counts = (
                self.rate_counters.get(keys[0], 0),
                self.rate_counters.get(keys[1], 0),
                len(self.in_flight_tokens.get(keys[2], set())),
                len(self.in_flight_tokens.get(keys[3], set())),
            )
            for index, (count, limit) in enumerate(zip(counts, limits), start=1):
                if count >= limit:
                    return index
            for key in keys[:2]:
                self.rate_counters[key] = self.rate_counters.get(key, 0) + 1
            for key in keys[2:]:
                self.in_flight_tokens.setdefault(key, set()).add(token)
            return 0

        assert numkeys == 2
        token = str(args[2])
        for key in keys:
            tokens = self.in_flight_tokens.get(key)
            if tokens is None:
                continue
            tokens.discard(token)
            if not tokens:
                self.in_flight_tokens.pop(key, None)
        return 1

    def expire_in_flight(self) -> None:
        self.in_flight_tokens.clear()


class ExplodingRedis:
    def eval(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")


@pytest.fixture(autouse=True)
def reset_local_admission_state(app):
    with admission._local_lock:
        admission._local_rate_state.clear()
        admission._local_in_flight_state.clear()
    yield
    with admission._local_lock:
        admission._local_rate_state.clear()
        admission._local_in_flight_state.clear()
    for key in (
        "LEARNER_PROFILE_OPTIMIZE_USER_RATE_LIMIT",
        "LEARNER_PROFILE_OPTIMIZE_IP_RATE_LIMIT",
        "LEARNER_PROFILE_OPTIMIZE_USER_CONCURRENCY",
        "LEARNER_PROFILE_OPTIMIZE_IP_CONCURRENCY",
        "LEARNER_PROFILE_OPTIMIZE_IN_FLIGHT_TTL_SECONDS",
        "TRUSTED_REVERSE_PROXY_ADDRESSES",
    ):
        app.config.enhanced._cache.pop(key, None)


def _configure_limits(
    app,
    monkeypatch,
    *,
    user_rate: int = 10,
    ip_rate: int = 10,
    user_concurrency: int = 5,
    ip_concurrency: int = 5,
) -> None:
    values = {
        "LEARNER_PROFILE_OPTIMIZE_USER_RATE_LIMIT": user_rate,
        "LEARNER_PROFILE_OPTIMIZE_IP_RATE_LIMIT": ip_rate,
        "LEARNER_PROFILE_OPTIMIZE_USER_CONCURRENCY": user_concurrency,
        "LEARNER_PROFILE_OPTIMIZE_IP_CONCURRENCY": ip_concurrency,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
        app.config.enhanced._cache.pop(key, None)


def _assert_admission_denied(app, *, user_id: str, client_ip: str) -> None:
    with pytest.raises(AppException) as raised:
        with admission.learner_profile_optimization_admission(
            app,
            user_id=user_id,
            client_ip=client_ip,
        ):
            raise AssertionError("denied admission must not enter the request body")
    assert raised.value.code == 1023


def test_admission_enforces_per_user_rate_limit(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    _configure_limits(app, monkeypatch, user_rate=2)

    for _ in range(2):
        with admission.learner_profile_optimization_admission(
            app,
            user_id="rate-limited-user",
            client_ip="198.51.100.10",
        ):
            pass

    _assert_admission_denied(
        app,
        user_id="rate-limited-user",
        client_ip="198.51.100.10",
    )


def test_admission_enforces_per_ip_rate_limit_across_guest_users(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    _configure_limits(app, monkeypatch, ip_rate=2)

    for user_id in ("guest-one", "guest-two"):
        with admission.learner_profile_optimization_admission(
            app,
            user_id=user_id,
            client_ip="198.51.100.20",
        ):
            pass

    _assert_admission_denied(
        app,
        user_id="guest-three",
        client_ip="198.51.100.20",
    )


def test_admission_enforces_per_user_in_flight_cap_and_releases(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    _configure_limits(app, monkeypatch, user_concurrency=1)

    with admission.learner_profile_optimization_admission(
        app,
        user_id="concurrent-user",
        client_ip="198.51.100.30",
    ):
        _assert_admission_denied(
            app,
            user_id="concurrent-user",
            client_ip="198.51.100.31",
        )

    with admission.learner_profile_optimization_admission(
        app,
        user_id="concurrent-user",
        client_ip="198.51.100.31",
    ):
        pass

    assert fake_redis.acquire_ttls
    assert min(fake_redis.acquire_ttls) >= 360


def test_admission_enforces_per_ip_in_flight_cap_across_guest_users(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    _configure_limits(app, monkeypatch, ip_concurrency=2)

    with (
        admission.learner_profile_optimization_admission(
            app,
            user_id="guest-one",
            client_ip="198.51.100.40",
        ),
        admission.learner_profile_optimization_admission(
            app,
            user_id="guest-two",
            client_ip="198.51.100.40",
        ),
    ):
        _assert_admission_denied(
            app,
            user_id="guest-three",
            client_ip="198.51.100.40",
        )


def test_admission_releases_in_flight_slots_after_request_error(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    _configure_limits(app, monkeypatch, user_concurrency=1)

    with pytest.raises(RuntimeError, match="provider failed"):
        with admission.learner_profile_optimization_admission(
            app,
            user_id="error-user",
            client_ip="198.51.100.50",
        ):
            raise RuntimeError("provider failed")

    with admission.learner_profile_optimization_admission(
        app,
        user_id="error-user",
        client_ip="198.51.100.50",
    ):
        pass


def test_expired_lease_release_cannot_remove_replacement_redis_slot(app, monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    _configure_limits(app, monkeypatch, user_concurrency=1)

    first = admission._acquire_admission(
        app,
        user_id="ttl-race-user",
        client_ip="203.0.113.70",
    )
    fake_redis.expire_in_flight()
    replacement = admission._acquire_admission(
        app,
        user_id="ttl-race-user",
        client_ip="203.0.113.70",
    )

    admission._release_admission(app, first)
    _assert_admission_denied(
        app,
        user_id="ttl-race-user",
        client_ip="203.0.113.70",
    )

    admission._release_admission(app, replacement)


def test_configured_redis_failure_denies_request_without_logging_identity(
    app, monkeypatch, caplog
):
    sentinel_identity = "SENSITIVE_ADMISSION_IDENTITY"
    monkeypatch.setattr("flaskr.dao.redis_client", ExplodingRedis(), raising=False)
    _configure_limits(app, monkeypatch, user_rate=1)

    app.logger.addHandler(caplog.handler)
    try:
        _assert_admission_denied(
            app,
            user_id=sentinel_identity,
            client_ip=sentinel_identity,
        )
    finally:
        app.logger.removeHandler(caplog.handler)

    assert "denying request" in caplog.text
    assert sentinel_identity not in caplog.text


def test_missing_redis_uses_process_local_admission(app, monkeypatch):
    monkeypatch.setattr("flaskr.dao.redis_client", None, raising=False)
    _configure_limits(app, monkeypatch, user_rate=1)

    with admission.learner_profile_optimization_admission(
        app,
        user_id="local-user",
        client_ip="203.0.113.55",
    ):
        pass
    _assert_admission_denied(
        app,
        user_id="local-user",
        client_ip="203.0.113.55",
    )


def test_optimizer_route_ignores_spoofed_forwarded_ip_for_admission_scope(
    app, test_client, monkeypatch, caplog
):
    sensitive_profile = "SENSITIVE_RATE_LIMITED_PROFILE"
    fake_redis = FakeRedis()
    users = iter(
        [
            SimpleNamespace(user_id="route-rate-user-one", language="en-US"),
            SimpleNamespace(user_id="route-rate-user-two", language="en-US"),
        ]
    )
    calls: list[dict] = []
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: next(users),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.route.user.optimize_learner_profile",
        lambda _app, **kwargs: (
            calls.append(kwargs) or {"optimized_learner_profile": "optimized profile"}
        ),
    )
    _configure_limits(app, monkeypatch, ip_rate=1)

    app.logger.addHandler(caplog.handler)
    try:
        first = test_client.post(
            "/api/user/learner-profile/optimize",
            headers={"Token": "token", "X-Forwarded-For": "198.51.100.60"},
            environ_base={"REMOTE_ADDR": "203.0.113.60"},
            json={"learner_profile": sensitive_profile},
        )
        second = test_client.post(
            "/api/user/learner-profile/optimize",
            headers={"Token": "token", "X-Forwarded-For": "198.51.100.61"},
            environ_base={"REMOTE_ADDR": "203.0.113.60"},
            json={"learner_profile": sensitive_profile},
        )
    finally:
        app.logger.removeHandler(caplog.handler)

    assert first.get_json(force=True)["code"] == 0
    assert second.get_json(force=True)["code"] == 1023
    assert len(calls) == 1
    assert calls[0]["learner_profile"] == sensitive_profile
    assert calls[0]["output_language"] == "en-US"
    assert sensitive_profile not in caplog.text


def test_optimizer_route_uses_real_ip_only_from_configured_proxy(
    app, test_client, monkeypatch
):
    fake_redis = FakeRedis()
    users = iter(
        [
            SimpleNamespace(user_id="trusted-proxy-user-one", language="en-US"),
            SimpleNamespace(user_id="trusted-proxy-user-two", language="en-US"),
        ]
    )
    calls: list[dict] = []
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: next(users),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.route.user.optimize_learner_profile",
        lambda _app, **kwargs: (
            calls.append(kwargs) or {"optimized_learner_profile": "optimized profile"}
        ),
    )
    _configure_limits(app, monkeypatch, ip_rate=1)
    monkeypatch.setenv("TRUSTED_REVERSE_PROXY_ADDRESSES", "127.0.0.1")
    app.config.enhanced._cache.pop("TRUSTED_REVERSE_PROXY_ADDRESSES", None)

    for real_ip in ("198.51.100.80", "198.51.100.81"):
        response = test_client.post(
            "/api/user/learner-profile/optimize",
            headers={
                "Token": "token",
                "X-Real-IP": real_ip,
                "X-Forwarded-For": "203.0.113.250",
            },
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
            json={"learner_profile": "source profile"},
        )
        assert response.get_json(force=True)["code"] == 0

    assert len(calls) == 2


@pytest.mark.parametrize(
    ("first_ip", "second_ip", "second_code"),
    [
        ("2001:db8:1::10", "2001:db8:1::20", 1023),
        ("2001:db8:1::10", "2001:db8:2::10", 0),
    ],
)
def test_optimizer_route_groups_ipv6_clients_by_64_network(
    app,
    test_client,
    monkeypatch,
    first_ip,
    second_ip,
    second_code,
):
    fake_redis = FakeRedis()
    users = iter(
        [
            SimpleNamespace(user_id="ipv6-user-one", language="en-US"),
            SimpleNamespace(user_id="ipv6-user-two", language="en-US"),
        ]
    )
    monkeypatch.setattr("flaskr.dao.redis_client", fake_redis, raising=False)
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: next(users),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.route.user.optimize_learner_profile",
        lambda _app, **_kwargs: {"optimized_learner_profile": "optimized"},
    )
    _configure_limits(app, monkeypatch, ip_rate=1)

    first = test_client.post(
        "/api/user/learner-profile/optimize",
        headers={"Token": "token"},
        environ_base={"REMOTE_ADDR": first_ip},
        json={"learner_profile": "source profile"},
    )
    second = test_client.post(
        "/api/user/learner-profile/optimize",
        headers={"Token": "token"},
        environ_base={"REMOTE_ADDR": second_ip},
        json={"learner_profile": "source profile"},
    )

    assert first.get_json(force=True)["code"] == 0
    assert second.get_json(force=True)["code"] == second_code

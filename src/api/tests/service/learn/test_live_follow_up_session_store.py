"""Redis binding tests for browser-direct Gemini Live sessions."""

from __future__ import annotations

import time

import pytest
from flask import Flask
from flaskr.service.learn import live_follow_up_session_store as store
from flaskr.service.learn.live_follow_up_capacity import LiveFollowUpCapacityLease
from flaskr.service.learn.live_follow_up_session_store import (
    LiveFollowUpSessionBinding,
    LiveFollowUpSessionRejectedError,
    LiveFollowUpSessionStoreUnavailableError,
    StoredLiveFollowUpSession,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def set(
        self,
        key: str,
        value: str,
        *,
        ex: int,
        nx: bool,
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expirations[key] = ex
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def eval(
        self, script: str, _key_count: int, key: str, *args: str
    ) -> int | str | None:
        if "EXPIRE" in script:
            if key not in self.values:
                return 0
            self.expirations[key] = int(args[0])
            return 1
        value = self.values.pop(key, None)
        self.expirations.pop(key, None)
        return value


def _app() -> Flask:
    app = Flask("live-session-store-test")
    app.config["REDIS_KEY_PREFIX"] = "test-prefix:"
    return app


def _session(**overrides: object) -> StoredLiveFollowUpSession:
    binding_values: dict[str, object] = {
        "session_bid": "session-1",
        "user_bid": "user-1",
        "shifu_bid": "course-1",
        "outline_bid": "chapter-1",
        "anchor_element_bid": "element-1",
        "progress_record_bid": "progress-1",
        "preview_mode": False,
        "origin": "https://learn.example.com",
        "model": "gemini-3.1-flash-live-preview",
        "voice_name": "Kore",
        "language": "zh-CN",
        "learning_mode": "read",
        "expires_at_epoch": time.time() + 900,
    }
    binding_values.update(overrides)
    return StoredLiveFollowUpSession(
        binding=LiveFollowUpSessionBinding(**binding_values),  # type: ignore[arg-type]
        lease=LiveFollowUpCapacityLease(
            lease_id="lease-1",
            user_bid="user-1",
            worker_id="worker-1",
        ),
    )


def test_store_round_trip_uses_hashed_key_and_bounded_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()
    session = _session()

    store.store_live_follow_up_session(app, session=session)

    key = next(iter(redis.values))
    assert key.startswith("test-prefix:live-follow-up:session:")
    assert "session-1" not in key
    assert redis.expirations[key] == store.LIVE_FOLLOW_UP_SESSION_STORE_TTL_SECONDS
    assert store.load_live_follow_up_session(app, session_bid="session-1") == session


def test_touch_requires_an_existing_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()

    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.touch_live_follow_up_session(app, session_bid="missing")

    store.store_live_follow_up_session(app, session=_session())
    store.touch_live_follow_up_session(app, session_bid="session-1")


def test_consume_is_atomic_and_one_time(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()
    session = _session()
    store.store_live_follow_up_session(app, session=session)

    assert store.consume_live_follow_up_session(app, session_bid="session-1") == session
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.consume_live_follow_up_session(app, session_bid="session-1")


def test_expired_binding_is_rejected_without_extending_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()
    store.store_live_follow_up_session(
        app,
        session=_session(expires_at_epoch=100.0),
    )

    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.load_live_follow_up_session(
            app,
            session_bid="session-1",
            current_time=101.0,
        )


def test_non_finite_expiry_is_rejected_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)

    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.store_live_follow_up_session(
            _app(),
            session=_session(expires_at_epoch=float("nan")),
        )


def test_redis_unavailability_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_redis_client", lambda: None)

    with pytest.raises(LiveFollowUpSessionStoreUnavailableError):
        store.store_live_follow_up_session(_app(), session=_session())

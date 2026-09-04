"""Redis binding tests for browser-direct Gemini Live sessions."""

from __future__ import annotations

import json
import time
from dataclasses import replace

import pytest
from flask import Flask
from flaskr.service.learn import live_follow_up_session_store as store
from flaskr.service.learn.live_follow_up_capacity import LiveFollowUpCapacityLease
from flaskr.service.learn.live_follow_up_session_store import (
    LiveFollowUpSessionBinding,
    LiveFollowUpSessionRejectedError,
    LiveFollowUpSessionStoreUnavailableError,
    LiveFollowUpTurnState,
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
        if "live_follow_up_reserve_turn" in script:
            raw = self.values.get(key)
            if raw is None:
                return 0
            record = json.loads(raw)
            state = record["turn_state"]
            turn_index = int(args[0])
            if (
                (
                    state["pending_index"] is not None
                    and (args[3] != "1" or state["pending_index"] != turn_index)
                )
                or turn_index != state["last_committed_index"] + 1
                or turn_index > int(args[2])
            ):
                return -2
            state["pending_index"] = turn_index
            state["pending_claim"] = args[1]
            self.values[key] = json.dumps(record)
            return 1
        if "live_follow_up_commit_turn" in script:
            raw = self.values.get(key)
            if raw is None:
                return 0
            record = json.loads(raw)
            state = record["turn_state"]
            if (
                state["pending_index"] != int(args[0])
                or state["pending_claim"] != args[1]
            ):
                return -2
            state["last_committed_index"] = int(args[0])
            state["pending_index"] = None
            state["pending_claim"] = ""
            self.values[key] = json.dumps(record)
            return 1
        if "live_follow_up_release_turn" in script:
            raw = self.values.get(key)
            if raw is None:
                return 0
            record = json.loads(raw)
            state = record["turn_state"]
            if (
                state["pending_index"] != int(args[0])
                or state["pending_claim"] != args[1]
            ):
                return -2
            state["pending_index"] = None
            state["pending_claim"] = ""
            self.values[key] = json.dumps(record)
            return 1
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


def _session(
    *,
    turn_state: LiveFollowUpTurnState | None = None,
    **overrides: object,
) -> StoredLiveFollowUpSession:
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
        turn_state=turn_state or LiveFollowUpTurnState(),
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


def test_turn_reservations_are_ordered_and_one_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()
    store.store_live_follow_up_session(app, session=_session())

    first = store.reserve_live_follow_up_turn(
        app,
        session_bid="session-1",
        turn_index=1,
    )
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.reserve_live_follow_up_turn(
            app,
            session_bid="session-1",
            turn_index=1,
        )
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.reserve_live_follow_up_turn(
            app,
            session_bid="session-1",
            turn_index=2,
        )
    forged = replace(first, claim="different-claim")
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.commit_live_follow_up_turn_reservation(app, reservation=forged)
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.release_live_follow_up_turn_reservation(app, reservation=forged)

    store.commit_live_follow_up_turn_reservation(app, reservation=first)
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.reserve_live_follow_up_turn(
            app,
            session_bid="session-1",
            turn_index=1,
        )
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.reserve_live_follow_up_turn(
            app,
            session_bid="session-1",
            turn_index=3,
        )

    second = store.reserve_live_follow_up_turn(
        app,
        session_bid="session-1",
        turn_index=2,
    )
    store.commit_live_follow_up_turn_reservation(app, reservation=second)
    assert (
        store.load_live_follow_up_session(
            app,
            session_bid="session-1",
        ).turn_state.last_committed_index
        == 2
    )


def test_failed_turn_reservation_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()
    store.store_live_follow_up_session(app, session=_session())

    failed = store.reserve_live_follow_up_turn(
        app,
        session_bid="session-1",
        turn_index=1,
    )
    store.release_live_follow_up_turn_reservation(app, reservation=failed)

    retried = store.reserve_live_follow_up_turn(
        app,
        session_bid="session-1",
        turn_index=1,
    )
    assert retried.claim != failed.claim


def test_orphaned_claim_can_be_replaced_without_advancing_or_reviving_old_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()
    store.store_live_follow_up_session(app, session=_session())
    abandoned = store.reserve_live_follow_up_turn(
        app, session_bid="session-1", turn_index=1
    )
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.reserve_live_follow_up_turn(
            app, session_bid="session-1", turn_index=2, recover_pending=True
        )
    recovered = store.reserve_live_follow_up_turn(
        app, session_bid="session-1", turn_index=1, recover_pending=True
    )
    assert recovered.claim != abandoned.claim
    for action in (
        store.commit_live_follow_up_turn_reservation,
        store.release_live_follow_up_turn_reservation,
    ):
        with pytest.raises(LiveFollowUpSessionRejectedError):
            action(app, reservation=abandoned)
    state = store.load_live_follow_up_session(app, session_bid="session-1").turn_state
    assert state.last_committed_index == 0
    assert state.pending_claim == recovered.claim
    store.commit_live_follow_up_turn_reservation(app, reservation=recovered)
    next_turn = store.reserve_live_follow_up_turn(
        app, session_bid="session-1", turn_index=2
    )
    store.commit_live_follow_up_turn_reservation(app, reservation=next_turn)


def test_turn_reservations_stop_at_the_session_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()
    store.store_live_follow_up_session(
        app,
        session=_session(
            turn_state=LiveFollowUpTurnState(
                last_committed_index=store.LIVE_FOLLOW_UP_MAX_TURNS - 1,
            )
        ),
    )

    final = store.reserve_live_follow_up_turn(
        app,
        session_bid="session-1",
        turn_index=store.LIVE_FOLLOW_UP_MAX_TURNS,
    )
    store.commit_live_follow_up_turn_reservation(app, reservation=final)

    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.reserve_live_follow_up_turn(
            app,
            session_bid="session-1",
            turn_index=store.LIVE_FOLLOW_UP_MAX_TURNS + 1,
        )


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


def test_finalization_grace_does_not_extend_live_access_or_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    app = _app()
    session = _session(expires_at_epoch=100.0)
    store.store_live_follow_up_session(app, session=session)

    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.load_live_follow_up_session(
            app, session_bid="session-1", current_time=100.0
        )
    assert (
        store.load_live_follow_up_session(
            app,
            session_bid="session-1",
            current_time=129.9,
            allow_finalization=True,
        )
        == session
    )

    store.touch_live_follow_up_session(app, session_bid="session-1")
    with pytest.raises(LiveFollowUpSessionRejectedError):
        store.load_live_follow_up_session(
            app,
            session_bid="session-1",
            current_time=130.0,
            allow_finalization=True,
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

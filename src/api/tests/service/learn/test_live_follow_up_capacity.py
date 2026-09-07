"""Verify Redis-only capacity reservations for Gemini Live credentials."""

from __future__ import annotations

import pytest
from flaskr import dao
from flaskr.service.learn import live_follow_up_capacity as capacity


class FakeRedis:
    """Implement the capacity admission and rollback scripts in memory."""

    def __init__(self) -> None:
        """Initialize sorted-set leases and per-user ownership keys."""
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.users: dict[str, tuple[str, float]] = {}
        self.acquire_args: list[tuple[object, ...]] = []

    def _purge_zset(self, key: str, now: float) -> None:
        current = self.sorted_sets.setdefault(key, {})
        self.sorted_sets[key] = {
            member: expiry for member, expiry in current.items() if expiry > now
        }

    def _get_user(self, key: str, now: float) -> str | None:
        value = self.users.get(key)
        if value is None:
            return None
        token, expiry = value
        if expiry <= now:
            self.users.pop(key, None)
            return None
        return token

    def eval(self, script: object, numkeys: int, *args: object) -> int:
        assert numkeys == 3
        global_key, worker_key, user_key = map(str, args[:3])
        argv = args[3:]
        if script == capacity._ACQUIRE_LEASE_SCRIPT:
            self.acquire_args.append(args)
            now = float(argv[0])
            expiry = float(argv[1])
            lease_id = str(argv[2])
            global_limit = int(argv[3])
            worker_limit = int(argv[4])
            expires_at_ms = int(argv[5])
            self._purge_zset(global_key, now)
            self._purge_zset(worker_key, now)
            if self._get_user(user_key, now) is not None:
                return -3
            if len(self.sorted_sets[global_key]) >= global_limit:
                return -1
            if len(self.sorted_sets[worker_key]) >= worker_limit:
                return -2
            self.users[user_key] = (lease_id, expires_at_ms / 1000)
            self.sorted_sets[global_key][lease_id] = expiry
            self.sorted_sets[worker_key][lease_id] = expiry
            return 1

        assert script == capacity._RELEASE_LEASE_SCRIPT
        lease_id = str(argv[0])
        self.sorted_sets.get(global_key, {}).pop(lease_id, None)
        self.sorted_sets.get(worker_key, {}).pop(lease_id, None)
        current = self.users.get(user_key)
        if current is not None and current[0] == lease_id:
            self.users.pop(user_key, None)
            return 1
        return 0


class ExplodingRedis:
    """Simulate Redis failure for every capacity operation."""

    def eval(self, *_args: object, **_kwargs: object) -> None:
        message = "redis unavailable"
        raise RuntimeError(message)


def test_capacity_enforces_one_session_per_user_across_workers(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    capacity.acquire_live_follow_up_capacity(
        app,
        user_bid="user-1",
        worker_id="worker-1",
        now=100,
    )

    with pytest.raises(capacity.LiveFollowUpCapacityLimitError) as raised:
        capacity.acquire_live_follow_up_capacity(
            app,
            user_bid="user-1",
            worker_id="worker-2",
            now=100,
        )
    assert raised.value.scope == "user"


def test_capacity_enforces_six_sessions_per_worker(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    for index in range(capacity.LIVE_FOLLOW_UP_WORKER_LIMIT):
        capacity.acquire_live_follow_up_capacity(
            app,
            user_bid=f"user-{index}",
            worker_id="worker-1",
            now=100,
        )

    with pytest.raises(capacity.LiveFollowUpCapacityLimitError) as raised:
        capacity.acquire_live_follow_up_capacity(
            app,
            user_bid="overflow-user",
            worker_id="worker-1",
            now=100,
        )
    assert raised.value.scope == "worker"


def test_capacity_enforces_twenty_four_sessions_globally(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    for index in range(capacity.LIVE_FOLLOW_UP_GLOBAL_LIMIT):
        capacity.acquire_live_follow_up_capacity(
            app,
            user_bid=f"user-{index}",
            worker_id=f"worker-{index // capacity.LIVE_FOLLOW_UP_WORKER_LIMIT}",
            now=100,
        )

    with pytest.raises(capacity.LiveFollowUpCapacityLimitError) as raised:
        capacity.acquire_live_follow_up_capacity(
            app,
            user_bid="overflow-user",
            worker_id="worker-new",
            now=100,
        )
    assert raised.value.scope == "global"


def test_expired_lease_frees_all_capacity_scopes(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    capacity.acquire_live_follow_up_capacity(
        app,
        user_bid="user-1",
        worker_id="worker-1",
        now=100,
    )

    replacement = capacity.acquire_live_follow_up_capacity(
        app,
        user_bid="user-1",
        worker_id="worker-1",
        now=1_000,
    )

    assert replacement.user_bid == "user-1"


def test_reservation_covers_the_disclosed_token_lifetime(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    capacity.acquire_live_follow_up_capacity(
        app,
        user_bid="user-1",
        worker_id="worker-1",
        now=100,
    )

    with pytest.raises(capacity.LiveFollowUpCapacityLimitError):
        capacity.acquire_live_follow_up_capacity(
            app,
            user_bid="user-1",
            worker_id="worker-2",
            now=999.999,
        )

    replacement = capacity.acquire_live_follow_up_capacity(
        app,
        user_bid="user-1",
        worker_id="worker-2",
        now=1_000,
    )
    assert replacement.worker_id == "worker-2"


def test_old_release_cannot_remove_replacement_user_lease(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    old = capacity.acquire_live_follow_up_capacity(
        app,
        user_bid="user-1",
        worker_id="worker-1",
        now=100,
    )
    replacement = capacity.acquire_live_follow_up_capacity(
        app,
        user_bid="user-1",
        worker_id="worker-2",
        now=1_000,
    )

    assert capacity.release_live_follow_up_capacity(app, lease=old) is False
    with pytest.raises(capacity.LiveFollowUpCapacityLimitError):
        capacity.acquire_live_follow_up_capacity(
            app,
            user_bid="user-1",
            worker_id="worker-3",
            now=1_000,
        )
    assert capacity.release_live_follow_up_capacity(app, lease=replacement) is True


def test_capacity_reservation_matches_the_absolute_token_deadline(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    capacity.acquire_live_follow_up_capacity(
        app,
        user_bid="user-1",
        worker_id="worker-1",
        now=100,
    )
    argv = fake.acquire_args[0][3:]
    expected_expiry = 100 + capacity.LIVE_FOLLOW_UP_CAPACITY_RESERVATION_SECONDS
    assert float(argv[1]) == expected_expiry
    assert int(argv[5]) == expected_expiry * 1000
    assert capacity.LIVE_FOLLOW_UP_CAPACITY_RESERVATION_SECONDS == 15 * 60
    assert "'PXAT'" in capacity._ACQUIRE_LEASE_SCRIPT


def test_fractional_deadline_rounds_up_consistently_without_overlap(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    capacity.acquire_live_follow_up_capacity(
        app, user_bid="user-1", worker_id="worker-1", now=100.000123
    )
    argv = fake.acquire_args[0][3:]
    assert float(argv[1]) == 1_000.001
    assert int(argv[5]) == 1_000_001
    assert next(iter(fake.users.values()))[1] == 1_000.001
    assert all(
        set(leases.values()) == {1_000.001} for leases in fake.sorted_sets.values()
    )
    with pytest.raises(capacity.LiveFollowUpCapacityLimitError):
        capacity.acquire_live_follow_up_capacity(
            app, user_bid="user-1", worker_id="worker-2", now=1_000.000123
        )
    replacement = capacity.acquire_live_follow_up_capacity(
        app, user_bid="user-1", worker_id="worker-2", now=1_000.001
    )
    assert replacement.worker_id == "worker-2"


@pytest.mark.parametrize("redis_client", [None, ExplodingRedis()])
def test_capacity_acquire_fails_closed_without_redis(
    app: object, monkeypatch: object, redis_client: object
) -> None:
    monkeypatch.setattr(dao._redis_state, "client", redis_client)
    with pytest.raises(capacity.LiveFollowUpCapacityUnavailableError):
        capacity.acquire_live_follow_up_capacity(
            app,
            user_bid="user-1",
            worker_id="worker-1",
            now=100,
        )


def test_capacity_release_fails_closed_on_redis_error(
    app: object, monkeypatch: object
) -> None:
    lease = capacity.LiveFollowUpCapacityLease(
        lease_id="lease-1",
        user_bid="user-1",
        worker_id="worker-1",
    )
    monkeypatch.setattr(dao._redis_state, "client", ExplodingRedis())
    with pytest.raises(capacity.LiveFollowUpCapacityUnavailableError):
        capacity.release_live_follow_up_capacity(app, lease=lease)

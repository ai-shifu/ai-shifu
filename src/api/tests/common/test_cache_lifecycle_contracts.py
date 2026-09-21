"""Exercise cache expiration, conditional writes, fallback and lock ownership."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr import dao
from flaskr.common import cache_provider as cache


@pytest.fixture
def memory(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    provider = cache.InMemoryCacheProvider()
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(provider, "_now", lambda: clock.now)
    return SimpleNamespace(provider=provider, clock=clock)


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        (b"bytes", b"bytes"),
        (1, b"1"),
        (1.5, b"1.5"),
        (True, b"True"),
        (None, b""),
        ("你好", "你好".encode()),
        ([1], b"[1]"),
    ],
)
def test_memory_encodes_values_consistently_and_reports_persistent_ttl(
    memory: SimpleNamespace, value: object, encoded: bytes
) -> None:
    assert memory.provider.set("value", value)
    assert memory.provider.get("value") == encoded
    assert memory.provider.ttl("value") == -1
    assert memory.provider.getex("value") == encoded
    assert memory.provider.ttl("value") == -1


@pytest.mark.parametrize("unit", ["ex", "px"])
def test_getex_refreshes_expiration_and_expired_keys_cannot_be_revived(
    memory: SimpleNamespace, unit: str
) -> None:
    provider = memory.provider
    provider.setex("key", 2, "value")
    memory.clock.now += 1
    assert provider.ttl("key") == 1
    assert provider.getex("key", **{unit: 3 if unit == "ex" else 3000}) == b"value"
    memory.clock.now += 2.5
    assert provider.ttl("key") == 0
    assert provider.get("key") == b"value"
    memory.clock.now += 0.5
    assert provider.getex("key", ex=10) is None
    assert provider.ttl("key") == -2
    assert provider.delete("key") == 0


def test_conditional_writes_observe_expiration_and_do_not_overwrite_existing_value(
    memory: SimpleNamespace,
) -> None:
    provider = memory.provider
    assert not provider.set("key", "new", xx=True)
    assert provider.set("key", "first", px=1000, nx=True)
    assert not provider.set("key", "second", nx=True)
    assert provider.get("key") == b"first"
    assert provider.set("key", "updated", ex=1, xx=True)
    memory.clock.now += 1
    assert not provider.set("key", "missing", xx=True)
    assert provider.set("key", "fresh", nx=True)
    assert provider.get("key") == b"fresh"


def test_increment_preserves_expiry_and_restarts_after_expiration(
    memory: SimpleNamespace,
) -> None:
    provider = memory.provider
    provider.setex("counter", 2, 5)
    assert provider.incr("counter", 3) == 8
    assert provider.ttl("counter") == 2
    memory.clock.now += 2
    assert provider.incr("counter", 2) == 2
    assert provider.ttl("counter") == -1
    provider.set("other", 1)
    assert provider.delete("counter", "counter", "absent", "other") == 2


def test_increment_is_atomic_across_threads(memory: SimpleNamespace) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        values = list(
            executor.map(lambda _: memory.provider.incr("counter"), range(200))
        )
    assert sorted(values) == list(range(1, 201))
    assert memory.provider.get("counter") == b"200"


def test_named_locks_prevent_competing_acquisition_and_release_only_owned_lock(
    memory: SimpleNamespace,
) -> None:
    first = memory.provider.lock("same")
    second = memory.provider.lock("same")
    assert first.acquire()
    assert first.extend(10, replace_ttl=True)
    assert not second.acquire(blocking=False)
    assert not second.extend(10)
    second.release()
    assert not second.acquire(blocking=True, blocking_timeout=0)
    first.release()
    first.release()
    assert not first.extend(10)
    assert second.acquire(blocking=True, blocking_timeout=0)
    second.release()


@pytest.mark.parametrize(
    "error", [cache.CacheUnavailableError("not configured"), ConnectionError("offline")]
)
def test_fallback_uses_process_cache_when_primary_operations_are_unavailable(
    memory: SimpleNamespace, error: Exception
) -> None:
    primary = Mock()
    for method in ("get", "getex", "set", "setex", "incr", "delete", "ttl", "lock"):
        getattr(primary, method).side_effect = error
    provider = cache.FallbackCacheProvider(primary, memory.provider)
    assert provider.set("key", "value", ex=10)
    assert provider.get("key") == b"value"
    assert provider.getex("key", px=2000) == b"value"
    assert provider.ttl("key") == 2
    assert provider.setex("counter", 5, 0)
    assert provider.incr("counter", 2) == 2
    assert provider.delete("key", "counter") == 2
    lock = provider.lock("lock", timeout=3, blocking_timeout=0, thread_local=False)
    assert lock.acquire(blocking=False)
    lock.release()
    primary.lock.assert_called_once_with(
        "lock", timeout=3, blocking_timeout=0, thread_local=False
    )


def test_primary_missing_value_does_not_resurrect_stale_fallback_data(
    memory: SimpleNamespace,
) -> None:
    memory.provider.set("key", "stale")
    primary = Mock()
    primary.get.return_value = None
    provider = cache.FallbackCacheProvider(primary, memory.provider)
    assert provider.get("key") is None
    assert memory.provider.get("key") == b"stale"


def test_dynamic_redis_resolves_current_client_and_converts_numeric_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = Mock()
    second = Mock()
    first.incr.return_value = "4"
    first.delete.return_value = "2"
    first.ttl.return_value = "12"
    clients = [first]
    monkeypatch.setattr(dao, "get_redis_client", lambda: clients[0])
    provider = cache._DynamicRedisCacheProvider()
    assert provider.incr("counter", 3) == 4
    assert provider.delete("one", "two") == 2
    assert provider.ttl("counter") == 12
    provider.set("legacy", b"value", None, None, False, False, 7)  # noqa: FBT003 - Exercise the legacy positional TTL call contract.
    first.set.assert_called_once_with(
        "legacy", b"value", ex=7, px=None, nx=False, xx=False
    )
    clients[0] = second
    provider.get("key")
    second.get.assert_called_once_with("key")
    first.get.assert_not_called()


def test_unconfigured_dynamic_redis_fails_with_explicit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dao, "get_redis_client", lambda: None)
    with pytest.raises(cache.CacheUnavailableError, match="Redis is not configured"):
        cache._DynamicRedisCacheProvider().get("key")

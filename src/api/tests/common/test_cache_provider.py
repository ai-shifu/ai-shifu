"""Verify shared cache provider fallback behavior."""

import pytest
from flaskr.common.cache_provider import FallbackCacheProvider, InMemoryCacheProvider


class _UnavailableLock:
    def acquire(
        self,
        blocking: bool = True,
        blocking_timeout: int | None = None,
    ) -> bool:
        _ = (blocking, blocking_timeout)
        raise ConnectionError

    def release(self) -> None:
        return None

    def extend(self, additional_time: int, replace_ttl: bool = False) -> bool:
        _ = (additional_time, replace_ttl)
        return False


class _UnavailableLockProvider:
    def lock(
        self,
        key: str,
        timeout: int | None = None,
        blocking_timeout: int | None = None,
        thread_local: bool = True,
    ) -> _UnavailableLock:
        _ = (key, timeout, blocking_timeout, thread_local)
        return _UnavailableLock()


def test_fallback_cache_lock_keeps_primary_acquire_failure_fail_closed() -> None:
    fallback = InMemoryCacheProvider()
    provider = FallbackCacheProvider(_UnavailableLockProvider(), fallback)  # type: ignore[arg-type]

    lock = provider.lock("shared-distributed-lock")
    with pytest.raises(ConnectionError):
        lock.acquire(blocking=True, blocking_timeout=1)

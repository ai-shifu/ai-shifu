"""Verify shared cache provider fallback behavior."""

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


def test_fallback_cache_lock_handles_primary_acquire_failure() -> None:
    fallback = InMemoryCacheProvider()
    provider = FallbackCacheProvider(_UnavailableLockProvider(), fallback)  # type: ignore[arg-type]

    first_lock = provider.lock("verification-lock")
    assert first_lock.acquire(blocking=True, blocking_timeout=1)
    assert first_lock.extend(10, replace_ttl=True)

    competing_lock = provider.lock("verification-lock")
    assert not competing_lock.acquire(blocking=False)

    first_lock.release()
    assert competing_lock.acquire(blocking=False)
    competing_lock.release()

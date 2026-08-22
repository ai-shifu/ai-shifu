"""Cover the shared cache-provider protocol contracts."""

from flaskr.common.cache_provider import CacheLock, InMemoryCacheProvider


def test_in_memory_lock_exposes_cache_lock_operations() -> None:
    """Return a lock that satisfies the public cache-lock protocol."""
    lock: CacheLock = InMemoryCacheProvider().lock("test-cache-lock")

    assert isinstance(lock, CacheLock)
    assert lock.acquire() is True
    lock.release()

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class CacheLock(Protocol):
    def acquire(self, blocking: bool = True, blocking_timeout: Optional[int] = None):
        raise NotImplementedError

    def release(self) -> None:
        raise NotImplementedError


@runtime_checkable
class CacheProvider(Protocol):
    def get(self, key: str):
        raise NotImplementedError

    def getex(self, key: str, ex: Optional[int] = None, px: Optional[int] = None):
        raise NotImplementedError

    def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
        *args,
        **kwargs,
    ):
        raise NotImplementedError

    def setex(self, key: str, time_in_seconds: int, value: Any):
        raise NotImplementedError

    def delete(self, *keys: str) -> int:
        raise NotImplementedError

    def incr(self, key: str, amount: int = 1):
        raise NotImplementedError

    def ttl(self, key: str) -> int:
        raise NotImplementedError

    def lock(
        self,
        key: str,
        timeout: Optional[int] = None,
        blocking_timeout: Optional[int] = None,
    ):
        raise NotImplementedError


class CacheUnavailableError(RuntimeError):
    pass


class _DynamicRedisCacheProvider:
    def _client(self):
        try:
            from flaskr.dao import redis_client
        except Exception as exc:  # pragma: no cover - defensive
            raise CacheUnavailableError("Redis client import failed") from exc

        if redis_client is None:
            raise CacheUnavailableError("Redis is not configured")
        return redis_client

    def get(self, key: str):
        return self._client().get(key)

    def getex(self, key: str, ex: Optional[int] = None, px: Optional[int] = None):
        return self._client().getex(key, ex=ex, px=px)

    def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
        *args,
        **kwargs,
    ):
        if ex is None and args:
            ex = args[0]
            args = ()
        return self._client().set(key, value, ex=ex, px=px, nx=nx, xx=xx, **kwargs)

    def setex(self, key: str, time_in_seconds: int, value: Any):
        return self._client().setex(key, time_in_seconds, value)

    def delete(self, *keys: str) -> int:
        return int(self._client().delete(*keys))

    def incr(self, key: str, amount: int = 1):
        return self._client().incr(key, amount)

    def ttl(self, key: str) -> int:
        return int(self._client().ttl(key))

    def lock(
        self,
        key: str,
        timeout: Optional[int] = None,
        blocking_timeout: Optional[int] = None,
    ):
        return self._client().lock(
            key, timeout=timeout, blocking_timeout=blocking_timeout
        )


@dataclass
class _InMemoryEntry:
    value: bytes
    expires_at: Optional[float]


class _InMemoryLock:
    def __init__(self, lock: threading.Lock):
        self._lock = lock
        self._held = False

    def acquire(self, blocking: bool = True, blocking_timeout: Optional[int] = None):
        if not blocking:
            acquired = self._lock.acquire(blocking=False)
        elif blocking_timeout is None:
            acquired = self._lock.acquire()
        else:
            acquired = self._lock.acquire(timeout=blocking_timeout)
        self._held = bool(acquired)
        return acquired

    def release(self) -> None:
        if self._held:
            self._lock.release()
            self._held = False


class InMemoryCacheProvider:
    def __init__(self):
        self._store: dict[str, _InMemoryEntry] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._mu = threading.RLock()

    def _now(self) -> float:
        return time.time()

    def _encode(self, value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value).encode("utf-8")
        if value is None:
            return b""
        if isinstance(value, str):
            return value.encode("utf-8")
        return str(value).encode("utf-8")

    def _purge_if_expired(self, key: str) -> None:
        entry = self._store.get(key)
        if entry is None:
            return
        if entry.expires_at is None:
            return
        if entry.expires_at <= self._now():
            self._store.pop(key, None)

    def get(self, key: str):
        with self._mu:
            self._purge_if_expired(key)
            entry = self._store.get(key)
            return entry.value if entry is not None else None

    def getex(self, key: str, ex: Optional[int] = None, px: Optional[int] = None):
        with self._mu:
            self._purge_if_expired(key)
            entry = self._store.get(key)
            if entry is None:
                return None
            if ex is not None:
                entry.expires_at = self._now() + ex
            elif px is not None:
                entry.expires_at = self._now() + (px / 1000.0)
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
        *args,
        **kwargs,
    ):
        with self._mu:
            self._purge_if_expired(key)
            if nx and key in self._store:
                return False
            if xx and key not in self._store:
                return False
            expires_at: Optional[float] = None
            if ex is None and args:
                ex = args[0]
            if ex is not None:
                expires_at = self._now() + ex
            elif px is not None:
                expires_at = self._now() + (px / 1000.0)
            self._store[key] = _InMemoryEntry(
                value=self._encode(value), expires_at=expires_at
            )
            return True

    def setex(self, key: str, time_in_seconds: int, value: Any):
        return self.set(key, value, ex=time_in_seconds)

    def delete(self, *keys: str) -> int:
        deleted = 0
        with self._mu:
            for key in keys:
                self._purge_if_expired(key)
                if key in self._store:
                    deleted += 1
                    self._store.pop(key, None)
        return deleted

    def incr(self, key: str, amount: int = 1):
        with self._mu:
            self._purge_if_expired(key)
            entry = self._store.get(key)
            current_value = int(entry.value) if entry is not None else 0
            expires_at = entry.expires_at if entry is not None else None
            new_value = current_value + amount
            self._store[key] = _InMemoryEntry(
                value=self._encode(new_value), expires_at=expires_at
            )
            return new_value

    def ttl(self, key: str) -> int:
        with self._mu:
            self._purge_if_expired(key)
            entry = self._store.get(key)
            if entry is None:
                return -2
            if entry.expires_at is None:
                return -1
            remaining = int(entry.expires_at - self._now())
            return remaining if remaining > 0 else 0

    def lock(
        self,
        key: str,
        timeout: Optional[int] = None,
        blocking_timeout: Optional[int] = None,
    ):
        with self._mu:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
        return _InMemoryLock(lock)


class FallbackCacheProvider:
    """
    Cache provider that prefers Redis when configured, and falls back to a
    process-local in-memory cache when Redis is unavailable.
    """

    def __init__(self, primary: CacheProvider, fallback: CacheProvider):
        self._primary = primary
        self._fallback = fallback

    def _call(self, method: str, *args, **kwargs):
        primary_fn = getattr(self._primary, method)
        fallback_fn = getattr(self._fallback, method)
        try:
            return primary_fn(*args, **kwargs)
        except CacheUnavailableError:
            return fallback_fn(*args, **kwargs)
        except Exception:
            # Redis connectivity errors should not break core flows.
            return fallback_fn(*args, **kwargs)

    def get(self, key: str):
        return self._call("get", key)

    def getex(self, key: str, ex: Optional[int] = None, px: Optional[int] = None):
        return self._call("getex", key, ex=ex, px=px)

    def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
        *args,
        **kwargs,
    ):
        return self._call(
            "set",
            key,
            value,
            ex=ex,
            px=px,
            nx=nx,
            xx=xx,
            *args,
            **kwargs,
        )

    def setex(self, key: str, time_in_seconds: int, value: Any):
        return self._call("setex", key, time_in_seconds, value)

    def delete(self, *keys: str) -> int:
        return int(self._call("delete", *keys))

    def incr(self, key: str, amount: int = 1):
        return self._call("incr", key, amount)

    def ttl(self, key: str) -> int:
        return int(self._call("ttl", key))

    def lock(
        self,
        key: str,
        timeout: Optional[int] = None,
        blocking_timeout: Optional[int] = None,
    ):
        return self._call(
            "lock", key, timeout=timeout, blocking_timeout=blocking_timeout
        )


_in_memory_cache = InMemoryCacheProvider()
cache: CacheProvider = FallbackCacheProvider(
    _DynamicRedisCacheProvider(), _in_memory_cache
)

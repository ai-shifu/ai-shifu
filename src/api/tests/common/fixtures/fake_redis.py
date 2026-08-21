"""Provide fake Redis support for common fixtures tests."""

import time
from typing import Any


class FakeRedisLock:
    """Simulate Redis lock behavior for tests."""

    def __init__(self, locks: dict[str, bool], key: str) -> None:
        """Initialize the fake Redis lock test double."""
        self._locks = locks
        self._key = key
        self._held = False

    def acquire(
        self, blocking: bool = True, blocking_timeout: int | None = None
    ) -> bool:
        _ = (blocking, blocking_timeout)
        if self._locks.get(self._key, False):
            return False
        self._locks[self._key] = True
        self._held = True
        return True

    def release(self) -> None:
        if self._held:
            self._locks.pop(self._key, None)
            self._held = False


class FakeRedis:
    """Simulate Redis behavior for tests."""

    def __init__(self) -> None:
        """Initialize the fake Redis test double."""
        self._store: dict[str, Any] = {}
        self._expires: dict[str, float] = {}
        self._locks: dict[str, bool] = {}

    def _now(self) -> float:
        return time.time()

    def _encode(self, value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value).encode("utf-8")
        if value is None:
            return b""
        return str(value).encode("utf-8")

    def _is_expired(self, key: str) -> bool:
        expires_at = self._expires.get(key)
        if expires_at is None:
            return False
        if expires_at <= self._now():
            self._store.pop(key, None)
            self._expires.pop(key, None)
            return True
        return False

    def get(self, key: str) -> bytes | None:
        if key not in self._store or self._is_expired(key):
            return None
        return self._store.get(key)

    def stored_keys(self) -> list[str]:
        """Return active keys for assertions without exposing storage internals."""
        for key in list(self._store):
            self._is_expired(key)
        return list(self._store)

    def getex(
        self, key: str, ex: int | None = None, px: int | None = None
    ) -> bytes | None:
        value = self.get(key)
        if value is None:
            return None
        if ex is not None:
            self._expires[key] = self._now() + ex
        elif px is not None:
            self._expires[key] = self._now() + (px / 1000.0)
        return value

    def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
        *args: object,
        **kwargs: object,
    ) -> bool:
        _ = kwargs
        if ex is None and args:
            ex = args[0]
        if nx and self.get(key) is not None:
            return False
        if xx and self.get(key) is None:
            return False
        self._store[key] = self._encode(value)
        if ex is not None:
            self._expires[key] = self._now() + ex
        elif px is not None:
            self._expires[key] = self._now() + (px / 1000.0)
        else:
            self._expires.pop(key, None)
        return True

    def setex(self, key: str, time_in_seconds: int, value: Any) -> bool:
        return self.set(key, value, ex=time_in_seconds)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._store:
                deleted += 1
                self._store.pop(key, None)
                self._expires.pop(key, None)
        return deleted

    def incr(self, key: str, amount: int = 1) -> int:
        current = self.get(key)
        current_value = 0 if current is None else int(current)
        new_value = current_value + amount
        self._store[key] = self._encode(new_value)
        ttl = self._expires.get(key)
        if ttl is not None:
            self._expires[key] = ttl
        return new_value

    def ttl(self, key: str) -> int:
        if key not in self._store:
            return -2
        if self._is_expired(key):
            return -2
        expires_at = self._expires.get(key)
        if expires_at is None:
            return -1
        remaining = int(expires_at - self._now())
        return max(0, remaining)

    def lock(
        self,
        key: str,
        timeout: int | None = None,
        blocking_timeout: int | None = None,
    ) -> FakeRedisLock:
        _ = (timeout, blocking_timeout)
        return FakeRedisLock(self._locks, key)

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None

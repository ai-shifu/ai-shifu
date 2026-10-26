"""Provide fake Redis support for common fixtures tests."""

import time
from typing import Any


class FakeRedisLock:
    """Simulate Redis lock behavior for tests."""

    def __init__(self, locks: dict[str, object], key: str) -> None:
        """Bind a shared lock registry and key with an unheld state."""
        self._locks = locks
        self._key = key
        self._held = False
        self._token: object | None = None

    def acquire(
        self,
        blocking: bool = True,
        blocking_timeout: int | None = None,
        token: str | None = None,
    ) -> object:
        _ = (blocking, blocking_timeout)
        if self._locks.get(self._key, False):
            return False
        self._token = token or True
        self._locks[self._key] = self._token
        self._held = True
        return True

    def release(self) -> None:
        if self._held and self._locks.get(self._key) == self._token:
            self._locks.pop(self._key, None)
            self._held = False

    def extend(self, additional_time: int, replace_ttl: bool = False) -> bool:
        _ = (additional_time, replace_ttl)
        return self._held and self._locks.get(self._key) == self._token


class FakeRedis:
    """Simulate Redis behavior for tests."""

    def __init__(self) -> None:
        """Initialize value, expiration, and lock registries for Redis tests."""
        self._store: dict[str, Any] = {}
        self._expires: dict[str, float] = {}
        self._locks: dict[str, object] = {}

    def _now(self) -> float:
        return time.time()

    def _encode(self, value: object) -> bytes:
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

    def get(self, key: str) -> object:
        if key not in self._store or self._is_expired(key):
            return None
        return self._store.get(key)

    def exists(self, key: str) -> int:
        """Return whether an unexpired key exists."""
        return int(self.get(key) is not None)

    def getex(self, key: str, ex: int | None = None, px: int | None = None) -> object:
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
        value: object,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
        *args: object,
        **kwargs: object,
    ) -> object:
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

    def setex(self, key: str, time_in_seconds: int, value: object) -> object:
        return self.set(key, value, ex=time_in_seconds)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._store:
                deleted += 1
                self._store.pop(key, None)
                self._expires.pop(key, None)
        return deleted

    def incr(self, key: str, amount: int = 1) -> object:
        current = self.get(key)
        current_value = 0 if current is None else int(current)
        new_value = current_value + amount
        self._store[key] = self._encode(new_value)
        ttl = self._expires.get(key)
        if ttl is not None:
            self._expires[key] = ttl
        return new_value

    def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        """Execute the password failure counter script used by authentication."""
        if numkeys != 3 or "password_login" not in str(keys_and_args[0]):
            message = "FakeRedis only supports the password login counter script"
            raise NotImplementedError(message)
        _ = script
        failure_key = str(keys_and_args[0])
        cooldown_key = str(keys_and_args[1])
        lock_key = str(keys_and_args[2])
        if self._locks.get(lock_key) != keys_and_args[-1]:
            return 0 if len(keys_and_args) == 4 else -1
        if len(keys_and_args) == 4:
            return self.delete(failure_key, cooldown_key) >= 0
        window_seconds = int(keys_and_args[3])
        max_failures = int(keys_and_args[4])
        cooldown_seconds = int(keys_and_args[5])
        failures = int(self.incr(failure_key))
        if failures == 1:
            self._expires[failure_key] = self._now() + window_seconds
        if failures >= max_failures:
            started = self.set(cooldown_key, "1", ex=cooldown_seconds, nx=True)
            if started:
                self.delete(failure_key)
        return failures

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
        thread_local: bool = True,
    ) -> object:
        _ = (timeout, blocking_timeout, thread_local)
        return FakeRedisLock(self._locks, key)

    def ping(self) -> object:
        return True

    def close(self) -> None:
        return None

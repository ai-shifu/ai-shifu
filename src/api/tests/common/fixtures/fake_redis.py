import time
from typing import Any, Dict, Optional


class FakeRedisLock:
    def __init__(self, locks: Dict[str, bool], key: str):
        self._locks = locks
        self._key = key
        self._held = False

    def acquire(self, blocking: bool = True, blocking_timeout: Optional[int] = None):
        if self._locks.get(self._key, False):
            return False
        self._locks[self._key] = True
        self._held = True
        return True

    def release(self):
        if self._held:
            self._locks.pop(self._key, None)
            self._held = False


class FakeRedis:
    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._expires: Dict[str, float] = {}
        self._locks: Dict[str, bool] = {}

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

    def get(self, key: str):
        if key not in self._store or self._is_expired(key):
            return None
        return self._store.get(key)

    def getex(self, key: str, ex: Optional[int] = None, px: Optional[int] = None):
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
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
        *args,
        **kwargs,
    ):
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

    def setex(self, key: str, time_in_seconds: int, value: Any):
        return self.set(key, value, ex=time_in_seconds)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._store:
                deleted += 1
                self._store.pop(key, None)
                self._expires.pop(key, None)
        return deleted

    def incr(self, key: str, amount: int = 1):
        current = self.get(key)
        if current is None:
            current_value = 0
        else:
            current_value = int(current)
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
        return remaining if remaining > 0 else 0

    def lock(
        self,
        key: str,
        timeout: Optional[int] = None,
        blocking_timeout: Optional[int] = None,
    ):
        return FakeRedisLock(self._locks, key)

    def ping(self):
        return True

    def close(self):
        return None

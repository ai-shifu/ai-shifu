from __future__ import annotations

import contextlib
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
class CachePubSub(Protocol):
    def subscribe(self, channel: str) -> None:
        raise NotImplementedError

    def get_message(self, timeout: Optional[float] = None) -> Optional[bytes]:
        raise NotImplementedError

    def close(self) -> None:
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

    def publish(self, channel: str, message: Any) -> int:
        raise NotImplementedError

    def pubsub(self) -> CachePubSub:
        raise NotImplementedError


class CacheUnavailableError(RuntimeError):
    pass


class _RedisPubSubAdapter:
    """Adapt redis-py PubSub to the CachePubSub protocol.

    Drains subscribe-acks so callers only see real messages, and converts
    redis's dict-shaped messages into raw byte payloads.
    """

    def __init__(self, redis_pubsub):
        self._ps = redis_pubsub

    def subscribe(self, channel: str) -> None:
        self._ps.subscribe(channel)
        # Drain the subscribe ack so subsequent get_message() returns real data.
        with contextlib.suppress(Exception):
            self._ps.get_message(timeout=0.05)

    def get_message(self, timeout: Optional[float] = None) -> Optional[bytes]:
        deadline: Optional[float]
        if timeout is None:
            deadline = None
            remaining: Optional[float] = None
        else:
            deadline = time.time() + timeout
            remaining = timeout
        while True:
            msg = self._ps.get_message(timeout=remaining)
            if msg is None:
                return None
            if msg.get("type") == "message":
                data = msg.get("data")
                if isinstance(data, bytes):
                    return data
                if data is None:
                    return None
                return str(data).encode("utf-8")
            if deadline is not None:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._ps.close()


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

    def publish(self, channel: str, message: Any) -> int:
        return int(self._client().publish(channel, message))

    def pubsub(self) -> CachePubSub:
        return _RedisPubSubAdapter(self._client().pubsub())


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


class _InMemoryPubSubSession:
    """Process-local PubSub session backed by ``_PubSubBus``.

    Subscribers buffer their own queue; publishers fan out to every active
    session listening on the channel. The semantics mirror ``CachePubSub``
    closely enough for tests and single-worker fallbacks.
    """

    def __init__(self, bus: "_PubSubBus"):
        self._bus = bus
        self._channels: list[str] = []
        self._cond = threading.Condition()
        self._queue: list[bytes] = []
        self._closed = False

    def subscribe(self, channel: str) -> None:
        if self._closed:
            return
        self._bus._add_subscriber(channel, self)
        if channel not in self._channels:
            self._channels.append(channel)

    def deliver(self, message: bytes) -> None:
        with self._cond:
            self._queue.append(message)
            self._cond.notify()

    def get_message(self, timeout: Optional[float] = None) -> Optional[bytes]:
        with self._cond:
            if not self._queue:
                self._cond.wait(timeout=timeout)
            if not self._queue:
                return None
            return self._queue.pop(0)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for channel in list(self._channels):
            self._bus._remove_subscriber(channel, self)
        self._channels.clear()


class _PubSubBus:
    def __init__(self):
        self._mu = threading.RLock()
        self._subscribers: dict[str, list[_InMemoryPubSubSession]] = {}

    def _add_subscriber(self, channel: str, session: _InMemoryPubSubSession) -> None:
        with self._mu:
            self._subscribers.setdefault(channel, []).append(session)

    def _remove_subscriber(self, channel: str, session: _InMemoryPubSubSession) -> None:
        with self._mu:
            subs = self._subscribers.get(channel)
            if not subs:
                return
            try:
                subs.remove(session)
            except ValueError:
                return
            if not subs:
                self._subscribers.pop(channel, None)

    def publish(self, channel: str, message: bytes) -> int:
        with self._mu:
            sessions = list(self._subscribers.get(channel, []))
        for session in sessions:
            session.deliver(message)
        return len(sessions)


class InMemoryCacheProvider:
    def __init__(self):
        self._store: dict[str, _InMemoryEntry] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._mu = threading.RLock()
        self._pubsub_bus = _PubSubBus()

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

    def publish(self, channel: str, message: Any) -> int:
        return self._pubsub_bus.publish(channel, self._encode(message))

    def pubsub(self) -> CachePubSub:
        return _InMemoryPubSubSession(self._pubsub_bus)


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

    def publish(self, channel: str, message: Any) -> int:
        return int(self._call("publish", channel, message))

    def pubsub(self) -> CachePubSub:
        # PubSub session establishment cannot transparently fail over
        # mid-wait, so pick a side at construction time. If Redis is
        # unreachable, fall back to the in-memory bus (single-worker only).
        try:
            return self._primary.pubsub()
        except CacheUnavailableError:
            return self._fallback.pubsub()
        except Exception:
            return self._fallback.pubsub()


_in_memory_cache = InMemoryCacheProvider()
cache: CacheProvider = FallbackCacheProvider(
    _DynamicRedisCacheProvider(), _in_memory_cache
)

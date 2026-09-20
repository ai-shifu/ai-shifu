"""Account-scoped protection for password authentication attempts."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import threading
import time
from typing import TYPE_CHECKING, Protocol, Self

from flaskr.dao import get_redis_client

if TYPE_CHECKING:
    from types import TracebackType

    from flask import Flask


class _RedisLock(Protocol):
    def acquire(
        self, blocking: bool = True, blocking_timeout: float | None = None
    ) -> bool: ...

    def release(self) -> None: ...


class _RedisClient(Protocol):
    def delete(self, *keys: str) -> int: ...

    def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...

    def exists(self, key: str) -> int: ...

    def lock(
        self,
        name: str,
        timeout: float | None = None,
        blocking_timeout: float | None = None,
        thread_local: bool = True,
    ) -> _RedisLock: ...


_RECORD_FAILURE_SCRIPT = """
local failures = redis.call('INCR', KEYS[1])
if failures == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if failures >= tonumber(ARGV[2]) then
    redis.call('SET', KEYS[2], '1', 'EX', ARGV[3], 'NX')
end
return failures
"""

_warning_lock = threading.Lock()
_warning_state = {"last_at": 0.0}
_WARNING_INTERVAL_SECONDS = 60.0


def _warn_unavailable(app: Flask, reason: str) -> None:
    """Emit a bounded warning when password protection cannot reach Redis."""
    now = time.monotonic()
    with _warning_lock:
        if now - _warning_state["last_at"] < _WARNING_INTERVAL_SECONDS:
            return
        _warning_state["last_at"] = now
    app.logger.warning(
        "security_event=password_login_rate_limit_unavailable reason=%s", reason
    )


def account_digest(app: Flask, identity: str) -> str:
    """Return an opaque, purpose-bound digest for a login identity."""
    secret = str(app.config["SECRET_KEY"]).encode("utf-8")
    message = f"password-login:{identity}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


class PasswordLoginAttempt:
    """Serialize and account for one password verification attempt."""

    def __init__(self, app: Flask, identity: str) -> None:
        """Bind the request to opaque account-scoped Redis keys."""
        self._app = app
        self.digest = account_digest(app, identity)
        prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu:"))
        base_key = f"{prefix}password_login:{self.digest}"
        self._failure_key = f"{base_key}:failures"
        self._cooldown_key = f"{base_key}:cooldown"
        self._lock_key = f"{base_key}:lock"
        self._redis: _RedisClient | None = None
        self._lock: _RedisLock | None = None
        self._enabled = False
        self.blocked = False

    def __enter__(self) -> Self:
        """Acquire the account guard and load its cooldown state."""
        redis_client = get_redis_client()
        if redis_client is None:
            _warn_unavailable(self._app, "not_configured")
            return self

        self._redis = redis_client
        lock_timeout = float(
            self._app.config.get("PASSWORD_LOGIN_LOCK_TIMEOUT_SECONDS", 5)
        )
        try:
            self._lock = redis_client.lock(
                self._lock_key,
                timeout=lock_timeout,
                blocking_timeout=lock_timeout,
                thread_local=False,
            )
            if not self._lock.acquire(blocking=True, blocking_timeout=lock_timeout):
                self.blocked = True
                self._app.logger.info(
                    "security_event=password_login_rate_limited account=%s reason=concurrent",
                    self.digest,
                )
                return self
            self._enabled = True
            self.blocked = bool(redis_client.exists(self._cooldown_key))
            if self.blocked:
                self._app.logger.info(
                    "security_event=password_login_rate_limited account=%s reason=cooldown",
                    self.digest,
                )
        except Exception as exc:
            self._enabled = False
            self.blocked = False
            self._release()
            _warn_unavailable(self._app, type(exc).__name__)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the account guard after verification finishes."""
        _ = (exc_type, exc_value, traceback)
        self._release()

    def _release(self) -> None:
        lock, self._lock = self._lock, None
        if lock is not None:
            with contextlib.suppress(Exception):
                lock.release()

    def record_failure(self) -> int | None:
        """Atomically count a failure and begin cooldown at the threshold."""
        if not self._enabled or self._redis is None:
            return None
        window_seconds = int(
            self._app.config.get("PASSWORD_LOGIN_FAILURE_WINDOW_SECONDS", 900)
        )
        max_failures = int(self._app.config.get("PASSWORD_LOGIN_MAX_FAILURES", 10))
        cooldown_seconds = int(
            self._app.config.get("PASSWORD_LOGIN_COOLDOWN_SECONDS", 600)
        )
        try:
            result = self._redis.eval(
                _RECORD_FAILURE_SCRIPT,
                2,
                self._failure_key,
                self._cooldown_key,
                window_seconds,
                max_failures,
                cooldown_seconds,
            )
            failures = int(result)
        except Exception as exc:
            self._enabled = False
            _warn_unavailable(self._app, type(exc).__name__)
            return None
        if failures >= max_failures:
            self.blocked = True
            self._app.logger.info(
                "security_event=password_login_cooldown_started account=%s",
                self.digest,
            )
        return failures

    def clear(self) -> None:
        """Clear only this account's password failure state after success."""
        if not self._enabled or self._redis is None:
            return
        try:
            self._redis.delete(self._failure_key, self._cooldown_key)
        except Exception as exc:
            self._enabled = False
            _warn_unavailable(self._app, type(exc).__name__)

"""Keep analytics-only Skill identity beside one device-issued session token."""

from __future__ import annotations

import contextlib
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import TYPE_CHECKING

from flaskr.common.cache_provider import cache
from flaskr.service.common.skill_attribution import (
    SkillIdentityInput,
    parse_skill_identity,
)

if TYPE_CHECKING:
    from flask import Flask


_TOUCH_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="session-attribution",
)
_TOUCH_CAPACITY = BoundedSemaphore(32)


def _cache_key(app: Flask, token: str) -> str:
    prefix = app.config.get("REDIS_KEY_PREFIX_USER", "ai-shifu:user:")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{prefix}analytics-attribution:{digest}"


def save_session_skill_attribution(
    app: Flask,
    *,
    token: str,
    attribution: SkillIdentityInput | None,
) -> None:
    """Save validated identity for no longer than the session lifetime."""
    if not token or attribution is None:
        return
    payload = json.dumps(
        {
            "host_platform": attribution.host_platform,
            "skill_id": attribution.skill_id,
            "skill_version": attribution.skill_version,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        cache.set(
            _cache_key(app, token),
            payload,
            ex=int(app.config["TOKEN_EXPIRE_TIME"]),
        )
    except Exception:
        return


def get_session_skill_attribution(
    app: Flask, *, token: str
) -> SkillIdentityInput | None:
    """Read and renew analytics context without affecting token validation."""
    if not token:
        return None
    key = _cache_key(app, token)
    try:
        raw = cache.getex(key, ex=int(app.config["TOKEN_EXPIRE_TIME"]))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(str(raw))
        return parse_skill_identity(value, field_name="session_attribution")
    except Exception:
        with contextlib.suppress(Exception):
            cache.delete(key)
        return None


def discard_session_skill_attribution(app: Flask, *, token: str) -> None:
    """Best-effort cleanup when the owning session is revoked."""
    if not token:
        return
    try:
        cache.delete(_cache_key(app, token))
    except Exception:
        return


def _renew_session_skill_attribution(app: Flask, token: str) -> None:
    try:
        cache.getex(
            _cache_key(app, token),
            ex=int(app.config["TOKEN_EXPIRE_TIME"]),
        )
    except Exception:
        return


def touch_session_skill_attribution(app: Flask, *, token: str) -> None:
    """Queue attribution renewal without putting Redis on the auth path."""
    if not token or not _TOUCH_CAPACITY.acquire(blocking=False):
        return
    try:
        future = _TOUCH_EXECUTOR.submit(
            _renew_session_skill_attribution,
            app,
            token,
        )
    except Exception:
        _TOUCH_CAPACITY.release()
        return
    future.add_done_callback(lambda _future: _TOUCH_CAPACITY.release())

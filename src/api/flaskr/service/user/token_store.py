"""Define token lookup and persistence provider contracts."""

from __future__ import annotations

import contextlib
import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.common.cache_provider import cache
from flaskr.dao import db
from flaskr.service.user.models import UserToken as UserTokenModel
from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    from flask import Flask


@dataclass(frozen=True)
class TokenLookupResult:
    """Capture a stored token and its expiration state."""

    user_id: str


@dataclass(frozen=True)
class SessionMetadata:
    """Describe where a session came from, so its owner can recognise it.

    Every field is display-only and recorded once, when the session is created.
    None of it takes part in deciding whether a token is valid.
    """

    session_bid: str = ""
    source: str = ""
    device_name: str = ""
    device_os: str = ""
    created_ip: str = ""


class TokenStoreProvider:
    """Cache-backed token store.

    - Always persists tokens to the database so the system can run without Redis.
    - Uses the configured cache provider (Redis when available, otherwise in-memory)
      as an accelerator for token lookups and sliding expiration.
    """

    def __init__(self) -> None:
        """Bind the shared cache provider used for token lookup acceleration."""
        self._cache = cache

    def _cache_key(self, app: Flask, token: str) -> str:
        prefix = app.config.get("REDIS_KEY_PREFIX_USER", "ai-shifu:user:")
        return f"{prefix}{token}"

    def save(
        self,
        app: Flask,
        *,
        user_id: str,
        token: str,
        ttl_seconds: int,
        metadata: SessionMetadata | None = None,
    ) -> None:
        """Persist the current token value and how its session began."""
        if not user_id or not token:
            return

        ttl_seconds = int(ttl_seconds)
        now = now_utc()
        expires_at = now + datetime.timedelta(seconds=ttl_seconds)

        with db.session.begin_nested():
            record = (
                UserTokenModel.query.filter(UserTokenModel.token == token)
                .order_by(UserTokenModel.id.desc())
                .first()
            )
            if record is None:
                record = UserTokenModel(
                    user_id=user_id,
                    token=token,
                    token_type=0,
                    token_expired_at=expires_at,
                )
                db.session.add(record)
            else:
                record.user_id = user_id
                record.token_expired_at = expires_at

            if metadata is not None:
                # Recorded once, at creation: these describe where the session
                # started, not where it was last used.
                record.session_bid = metadata.session_bid
                record.source = metadata.source
                record.device_name = metadata.device_name
                record.device_os = metadata.device_os
                record.created_ip = metadata.created_ip

        try:
            self._cache.set(self._cache_key(app, token), user_id, ex=ttl_seconds)
        except Exception:
            # Cache failures should not block login flows.
            return

    def _refresh_marker_key(self, app: Flask, token: str) -> str:
        return f"{self._cache_key(app, token)}:row"

    def _refresh_row_periodically(
        self, app: Flask, *, token: str, user_id: str, ttl_seconds: int
    ) -> None:
        """Keep the stored expiry from falling behind a cache-served session.

        A cache hit renews only the cache entry, so a session in constant use
        would keep working while its row aged out. Anything reading the rows --
        the session list, and revoking every other session -- would then miss
        exactly the sessions that are most active.

        Writing the row on every hit would undo the point of the cache, so a
        marker with half the lifetime bounds this to one write per half-window.
        """
        marker = self._refresh_marker_key(app, token)
        with contextlib.suppress(Exception):
            if self._cache.get(marker):
                return

        expires_at = now_utc() + datetime.timedelta(seconds=ttl_seconds)
        try:
            with db.session.begin_nested():
                record = (
                    UserTokenModel.query.filter(
                        UserTokenModel.token == token,
                        UserTokenModel.user_id == user_id,
                    )
                    .order_by(UserTokenModel.id.desc())
                    .first()
                )
                if record is None:
                    return
                record.token_expired_at = expires_at
        except Exception:
            app.logger.warning("could not refresh token row expiry")
            return

        with contextlib.suppress(Exception):
            self._cache.set(marker, "1", ex=max(1, ttl_seconds // 2))

    def get_and_refresh(
        self, app: Flask, *, token: str, expected_user_id: str, ttl_seconds: int
    ) -> TokenLookupResult | None:
        """Validate a token and return its user lookup result.

        Cache hits renew only the cache TTL. Database hits extend the persisted expiry
        and repopulate the cache.
        """
        if not token or not expected_user_id:
            return None

        ttl_seconds = int(ttl_seconds)
        cache_key = self._cache_key(app, token)

        # A cache outage must fall through to the database lookup below.
        with contextlib.suppress(Exception):
            cached_user_id = self._cache.getex(cache_key, ex=ttl_seconds)
            if isinstance(cached_user_id, bytes):
                cached_user_id = cached_user_id.decode("utf-8")
            if cached_user_id:
                if str(cached_user_id) == expected_user_id:
                    self._refresh_row_periodically(
                        app,
                        token=token,
                        user_id=expected_user_id,
                        ttl_seconds=ttl_seconds,
                    )
                    return TokenLookupResult(user_id=expected_user_id)
                # Defensive: token should never map to a different user id.
                self._cache.delete(cache_key)

        now = now_utc()
        record = (
            UserTokenModel.query.filter(
                UserTokenModel.token == token,
                UserTokenModel.user_id == expected_user_id,
            )
            .order_by(UserTokenModel.id.desc())
            .first()
        )
        if record is None:
            return None

        expires_at = getattr(record, "token_expired_at", None)
        if expires_at is None or expires_at <= now:
            return None

        new_expires_at = now + datetime.timedelta(seconds=ttl_seconds)
        with db.session.begin_nested():
            record.token_expired_at = new_expires_at

        with contextlib.suppress(Exception):
            self._cache.set(cache_key, expected_user_id, ex=ttl_seconds)

        return TokenLookupResult(user_id=expected_user_id)


token_store = TokenStoreProvider()

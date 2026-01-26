from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from flask import Flask

from flaskr.common.cache_provider import cache
from flaskr.dao import db
from flaskr.service.user.models import UserToken as UserTokenModel


@dataclass(frozen=True)
class TokenLookupResult:
    user_id: str


class TokenStoreProvider:
    """
    Cache-backed token store.

    - Always persists tokens to the database so the system can run without Redis.
    - Uses the configured cache provider (Redis when available, otherwise in-memory)
      as an accelerator for token lookups and sliding expiration.
    """

    def __init__(self):
        self._cache = cache

    def _cache_key(self, app: Flask, token: str) -> str:
        prefix = app.config.get("REDIS_KEY_PREFIX_USER", "ai-shifu:user:")
        return f"{prefix}{token}"

    def save(self, app: Flask, *, user_id: str, token: str, ttl_seconds: int) -> None:
        if not user_id or not token:
            return

        ttl_seconds = int(ttl_seconds)
        now = datetime.datetime.utcnow()
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

        try:
            self._cache.set(self._cache_key(app, token), user_id, ex=ttl_seconds)
        except Exception:
            # Cache failures should not block login flows.
            return

    def get_and_refresh(
        self, app: Flask, *, token: str, expected_user_id: str, ttl_seconds: int
    ) -> Optional[TokenLookupResult]:
        if not token or not expected_user_id:
            return None

        ttl_seconds = int(ttl_seconds)
        cache_key = self._cache_key(app, token)

        try:
            cached_user_id = self._cache.getex(cache_key, ex=ttl_seconds)
            if isinstance(cached_user_id, bytes):
                cached_user_id = cached_user_id.decode("utf-8")
            if cached_user_id:
                if str(cached_user_id) == expected_user_id:
                    return TokenLookupResult(user_id=expected_user_id)
                # Defensive: token should never map to a different user id.
                self._cache.delete(cache_key)
        except Exception:
            pass

        now = datetime.datetime.utcnow()
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

        try:
            self._cache.set(cache_key, expected_user_id, ex=ttl_seconds)
        except Exception:
            pass

        return TokenLookupResult(user_id=expected_user_id)


token_store = TokenStoreProvider()

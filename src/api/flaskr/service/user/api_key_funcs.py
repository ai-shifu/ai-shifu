"""Service functions for API key CRUD and validation."""

import hashlib
import logging
import secrets
from datetime import datetime

from flask import Flask

from flaskr.common.cache_provider import cache
from flaskr.common.config import get_config
from flaskr.dao import db
from flaskr.service.common.dtos import UserInfo
from flaskr.service.common.models import raise_error
from flaskr.service.user.api_key_models import UserApiKey
from flaskr.service.user.repository import load_user_aggregate
from flaskr.util.uuid import generate_id

logger = logging.getLogger(__name__)

API_KEY_PREFIX = "sk-"
MAX_API_KEYS_PER_USER = 10
CACHE_KEY_PREFIX = "api_key:"


def _hash_key(raw_key: str) -> str:
    """Compute SHA-256 hash of an API key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _cache_ttl() -> int:
    """Return the API key cache TTL in seconds."""
    return int(get_config("API_KEY_CACHE_TTL", 300))


def _cache_key(key_hash: str) -> str:
    return f"{CACHE_KEY_PREFIX}{key_hash}"


def create_api_key(app: Flask, user_bid: str, name: str) -> dict:
    """Create a new API key for a user.

    Returns a dict containing the full raw key (shown only once) and metadata.
    """
    name = (name or "").strip()
    if len(name) > 100:
        raise_error("server.user.apiKeyNameTooLong")

    # Enforce per-user limit
    existing_count = UserApiKey.query.filter(
        UserApiKey.user_bid == user_bid,
        UserApiKey.deleted == 0,
    ).count()
    if existing_count >= MAX_API_KEYS_PER_USER:
        raise_error("server.user.apiKeyLimitExceeded")

    raw_key = API_KEY_PREFIX + secrets.token_hex(16)
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:8]

    api_key = UserApiKey(
        api_key_bid=generate_id(app),
        user_bid=user_bid,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=name,
        revoked=0,
        deleted=0,
    )
    db.session.add(api_key)
    db.session.commit()

    return {
        "api_key_bid": api_key.api_key_bid,
        "name": api_key.name,
        "key": raw_key,
        "key_prefix": key_prefix,
        "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
    }


def list_api_keys(app: Flask, user_bid: str) -> list[dict]:
    """List all API keys for a user (never returns the full key)."""
    keys = (
        UserApiKey.query.filter(
            UserApiKey.user_bid == user_bid,
            UserApiKey.deleted == 0,
        )
        .order_by(UserApiKey.created_at.desc())
        .all()
    )
    return [
        {
            "api_key_bid": k.api_key_bid,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "revoked": bool(k.revoked),
        }
        for k in keys
    ]


def revoke_api_key(app: Flask, user_bid: str, api_key_bid: str) -> None:
    """Revoke an API key and clear its cache."""
    api_key = UserApiKey.query.filter(
        UserApiKey.api_key_bid == api_key_bid,
        UserApiKey.user_bid == user_bid,
        UserApiKey.deleted == 0,
    ).first()

    if not api_key:
        raise_error("server.user.apiKeyNotFound")

    api_key.revoked = 1
    api_key.deleted = 1
    db.session.commit()

    # Clear cache so the revocation takes effect immediately
    cache.delete(_cache_key(api_key.key_hash))


def validate_api_key(app: Flask, raw_key: str) -> UserInfo:
    """Validate an API key and return the associated UserInfo.

    Uses a cache layer (Redis / in-memory) to avoid hitting the database on
    every request.  On cache miss, queries the ``user_api_keys`` table and
    populates the cache entry with a configurable TTL.

    Raises an application error if the key is invalid or revoked.
    """
    key_hash = _hash_key(raw_key)
    ck = _cache_key(key_hash)

    # 1. Try cache
    cached_user_bid = cache.get(ck)
    if cached_user_bid is not None:
        user_bid = (
            cached_user_bid.decode("utf-8")
            if isinstance(cached_user_bid, bytes)
            else str(cached_user_bid)
        )
    else:
        # 2. Cache miss — query database
        api_key = UserApiKey.query.filter(
            UserApiKey.key_hash == key_hash,
            UserApiKey.revoked == 0,
            UserApiKey.deleted == 0,
        ).first()

        if not api_key:
            raise_error("server.user.apiKeyInvalid")

        user_bid = api_key.user_bid

        # Populate cache
        cache.set(ck, user_bid, ex=_cache_ttl())

        # Update last_used_at on cache miss (acceptable overhead since we
        # already hit the DB for the key lookup in this code path).
        try:
            api_key.last_used_at = datetime.utcnow()
            db.session.commit()
        except Exception:
            logger.debug("Failed to update API key last_used_at", exc_info=True)
            db.session.rollback()

    # 3. Load user aggregate
    aggregate = load_user_aggregate(user_bid)
    if not aggregate:
        raise_error("server.user.userNotFound")

    return aggregate.to_user_info()

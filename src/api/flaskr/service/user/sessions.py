"""Listing and revoking a user's own login sessions.

A session is one row in ``user_token``: every sign-in path issues a token
through ``generate_token`` and records where it came from. This module lets the
person who owns those sessions see them and end any of them.

Sessions are addressed by ``session_bid``, never by the token. The token is the
credential itself, so handing it to a client that only needs to name a session
would defeat the point of the feature.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from flaskr.common.cache_provider import cache as redis
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_error
from flaskr.service.user.models import UserToken
from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    from flask import Flask


def _cache_key(app: Flask, token: str) -> str:
    prefix = app.config.get("REDIS_KEY_PREFIX_USER", "ai-shifu:user:")
    return f"{prefix}{token}"


def _active_sessions(user_id: str) -> list[UserToken]:
    """Return the user's unexpired sessions, most recently used first."""
    return (
        UserToken.query.filter(
            UserToken.user_id == user_id,
            UserToken.token_expired_at > now_utc(),
        )
        .order_by(UserToken.updated.desc())
        .all()
    )


def _to_dto(record: UserToken, *, current_token: str) -> dict[str, Any]:
    return {
        "session_bid": record.session_bid or "",
        "source": record.source or "",
        "device_name": record.device_name or "",
        "device_os": record.device_os or "",
        "created_ip": record.created_ip or "",
        "created_at": record.created,
        # `updated` is refreshed by the sliding-expiry write on every
        # authenticated call, so it already means "last used".
        "last_seen_at": record.updated,
        "expires_at": record.token_expired_at,
        "is_current": bool(current_token) and record.token == current_token,
    }


def _ensure_public_ids(records: list[UserToken]) -> None:
    """Give any session without a public id one before it is listed.

    Sessions issued before this feature existed have an empty id, and a session
    without one can be shown but never revoked, since the id is how a client
    names it. The migration backfills live sessions; this covers anything it
    could not reach and makes the listing self-healing.
    """
    missing = [record for record in records if not record.session_bid]
    if not missing:
        return
    with unit_of_work():
        for record in missing:
            record.session_bid = str(uuid.uuid4())


def list_user_sessions(
    *, user_id: str, current_token: str = ""
) -> list[dict[str, Any]]:
    """List the sessions this user can currently sign in with."""
    if not user_id:
        raise_error("server.user.userNotLogin")
    records = _active_sessions(user_id)
    _ensure_public_ids(records)
    return [_to_dto(record, current_token=current_token) for record in records]


def _forget(app: Flask, records: list[UserToken]) -> int:
    """Delete sessions and drop their cached lookups.

    The cache entry has to go too: token validation consults it first, so a row
    deleted from the database would otherwise keep working until the cached
    copy expired.
    """
    if not records:
        return 0
    with unit_of_work():
        for record in records:
            token = record.token
            db.session.delete(record)
            if token:
                try:
                    redis.delete(_cache_key(app, token))
                except Exception:
                    app.logger.warning("could not drop cached token on revoke")
    return len(records)


def revoke_user_session(
    app: Flask, *, user_id: str, session_bid: str
) -> dict[str, Any]:
    """End one session belonging to this user."""
    if not user_id:
        raise_error("server.user.userNotLogin")
    normalized = str(session_bid or "").strip()
    if not normalized:
        raise_error("server.user.sessionNotFound")

    # Scoped by user_id as well as session id: a session id from someone else's
    # account must not be revocable here.
    records = UserToken.query.filter(
        UserToken.user_id == user_id,
        UserToken.session_bid == normalized,
    ).all()
    if not records:
        raise_error("server.user.sessionNotFound")

    return {"revoked": _forget(app, records)}


def revoke_other_user_sessions(
    app: Flask, *, user_id: str, current_token: str
) -> dict[str, Any]:
    """End every session except the one making this request."""
    if not user_id:
        raise_error("server.user.userNotLogin")

    records = [
        record
        for record in _active_sessions(user_id)
        if not (current_token and record.token == current_token)
    ]
    return {"revoked": _forget(app, records)}

"""Verify durable sessions remain authoritative through cache failures."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import sessions
from flaskr.service.user.models import UserToken
from flaskr.service.user.token_store import TokenStoreProvider
from flaskr.util.datetime import now_utc

from tests.common.fixtures.fake_redis import FakeRedis


@pytest.fixture
def store_context(app: object) -> Iterator[tuple[TokenStoreProvider, str, str]]:
    with app.app_context():
        provider = TokenStoreProvider()
        provider._cache = FakeRedis()
        user_id = uuid.uuid4().hex
        token = uuid.uuid4().hex
        yield provider, user_id, token
        db.session.rollback()
        UserToken.query.filter_by(user_id=user_id).delete()
        db.session.commit()


@pytest.mark.parametrize(("user_id", "token"), [("", "token"), ("account", "")])
def test_empty_token_store_inputs_never_touch_persistence(
    app: object, user_id: str, token: str
) -> None:
    provider = TokenStoreProvider()
    with app.app_context():
        provider.save(app, user_id=user_id, token=token, ttl_seconds=60)
        assert (
            provider.get_and_refresh(
                app, token=token, expected_user_id=user_id, ttl_seconds=60
            )
            is None
        )


def test_token_save_survives_cache_write_failure_after_commit(
    app: object, store_context: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, user_id, token = store_context
    monkeypatch.setattr(
        provider._cache, "set", Mock(side_effect=RuntimeError("cache unavailable"))
    )
    with unit_of_work():
        provider.save(app, user_id=user_id, token=token, ttl_seconds=60)
    row = UserToken.query.filter_by(token=token).one()
    assert row.user_id == user_id
    assert row.token_expired_at > now_utc()


@pytest.mark.parametrize("cached_identity", ["another-account", None])
def test_database_fallback_repairs_missing_or_inconsistent_cache(
    app: object, store_context: tuple, cached_identity: str | None
) -> None:
    provider, user_id, token = store_context
    original_expiry = now_utc() + timedelta(seconds=10)
    db.session.add(
        UserToken(user_id=user_id, token=token, token_expired_at=original_expiry)
    )
    db.session.commit()
    if cached_identity:
        provider._cache.set(provider._cache_key(app, token), cached_identity, ex=60)
    result = provider.get_and_refresh(
        app, token=token, expected_user_id=user_id, ttl_seconds=120
    )
    assert result.user_id == user_id
    assert provider._cache.get(provider._cache_key(app, token)) == user_id.encode()
    assert (
        UserToken.query.filter_by(token=token).one().token_expired_at > original_expiry
    )


def test_cache_read_failure_falls_back_to_valid_database_session(
    app: object, store_context: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, user_id, token = store_context
    db.session.add(
        UserToken(
            user_id=user_id,
            token=token,
            token_expired_at=now_utc() + timedelta(seconds=60),
        )
    )
    db.session.commit()
    monkeypatch.setattr(
        provider._cache, "getex", Mock(side_effect=RuntimeError("cache unavailable"))
    )
    assert (
        provider.get_and_refresh(
            app, token=token, expected_user_id=user_id, ttl_seconds=120
        ).user_id
        == user_id
    )


@pytest.mark.parametrize("expired", [False, True])
def test_database_fallback_never_revives_missing_or_expired_sessions(
    app: object, store_context: tuple, expired: bool
) -> None:
    provider, user_id, token = store_context
    if expired:
        db.session.add(
            UserToken(
                user_id=user_id,
                token=token,
                token_expired_at=now_utc() - timedelta(seconds=1),
            )
        )
        db.session.commit()
    assert (
        provider.get_and_refresh(
            app, token=token, expected_user_id=user_id, ttl_seconds=120
        )
        is None
    )
    assert provider._cache.get(provider._cache_key(app, token)) is None


@pytest.mark.parametrize("operation", ["list", "revoke", "others"])
def test_session_management_requires_an_authenticated_account(
    app: object, operation: str
) -> None:
    calls = {
        "list": lambda: sessions.list_user_sessions(user_id=""),
        "revoke": lambda: sessions.revoke_user_session(
            app, user_id="", session_bid="session"
        ),
        "others": lambda: sessions.revoke_other_user_sessions(
            app, user_id="", current_token="token"
        ),
    }
    with app.app_context(), pytest.raises(AppError) as error:
        calls[operation]()
    assert error.value.code == ERROR_CODE["server.user.userNotLogin"]


def test_empty_session_id_is_rejected_and_revoking_no_other_sessions_is_a_noop(
    app: object, store_context: tuple
) -> None:
    _provider, user_id, token = store_context
    with pytest.raises(AppError) as error:
        sessions.revoke_user_session(app, user_id=user_id, session_bid=" ")
    assert error.value.code == ERROR_CODE["server.user.sessionNotFound"]
    assert sessions.revoke_other_user_sessions(
        app, user_id=user_id, current_token=token
    ) == {"revoked": 0}

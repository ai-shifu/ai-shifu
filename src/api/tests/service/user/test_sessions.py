"""Verify a user can see and end their own sign-in sessions."""

import uuid

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user.models import UserToken
from flaskr.service.user.sessions import (
    list_user_sessions,
    revoke_other_user_sessions,
    revoke_user_session,
)
from flaskr.service.user.token_store import SessionMetadata, token_store
from flaskr.service.user.utils import describe_user_agent, generate_token


@pytest.fixture
def user_id() -> str:
    """Give each test its own user: the test database is shared."""
    return f"session-owner-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def other_user_id() -> str:
    return f"session-stranger-{uuid.uuid4().hex[:12]}"


def _sign_in(app: object, user_id: str, **kwargs: object) -> str:
    token = generate_token(app, user_id, **kwargs)
    db.session.commit()
    return token


def test_a_failed_login_transaction_does_not_expose_its_token(
    app: object, user_id: str
) -> None:
    token = f"rolled-back-{uuid.uuid4().hex}"

    def fail_login_transaction() -> None:
        with unit_of_work():
            token_store.save(
                app,
                user_id=user_id,
                token=token,
                ttl_seconds=60,
            )
            message = "simulate a later login failure"
            raise RuntimeError(message)

    with app.test_request_context():
        with pytest.raises(RuntimeError):
            fail_login_transaction()

        assert UserToken.query.filter_by(token=token).count() == 0
        assert token_store._cache.get(token_store._cache_key(app, token)) is None


def test_resaving_a_token_preserves_where_the_session_started(
    app: object, user_id: str
) -> None:
    token = f"resaved-{uuid.uuid4().hex}"
    original = SessionMetadata(
        session_bid=uuid.uuid4().hex,
        source="web",
        device_name="Original device",
        device_os="Original OS",
        created_ip="203.0.113.8",
    )
    replacement = SessionMetadata(
        session_bid=uuid.uuid4().hex,
        source="cli",
        device_name="Replacement device",
        device_os="Replacement OS",
        created_ip="203.0.113.9",
    )

    with app.test_request_context():
        token_store.save(
            app,
            user_id=user_id,
            token=token,
            ttl_seconds=60,
            metadata=original,
        )
        db.session.commit()
        token_store.save(
            app,
            user_id=user_id,
            token=token,
            ttl_seconds=120,
            metadata=replacement,
        )
        db.session.commit()

        record = UserToken.query.filter_by(token=token).one()
        assert record.session_bid == original.session_bid
        assert record.source == original.source
        assert record.device_name == original.device_name
        assert record.device_os == original.device_os
        assert record.created_ip == original.created_ip


def test_a_session_is_recorded_for_every_sign_in(app: object, user_id: str) -> None:
    with app.test_request_context(
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
            "X-Forwarded-For": "203.0.113.9",
        }
    ):
        _sign_in(app, user_id)

        sessions = list_user_sessions(user_id=user_id)
        assert len(sessions) == 1
        assert sessions[0]["source"] == "web"
        assert sessions[0]["device_name"] == "Chrome"
        assert sessions[0]["device_os"] == "macOS"
        assert sessions[0]["created_ip"] == "203.0.113.9"
        assert sessions[0]["session_bid"]


def test_the_session_list_never_exposes_the_token(app: object, user_id: str) -> None:
    """The token is the credential; naming a session must not reveal it."""
    with app.test_request_context():
        token = _sign_in(app, user_id)

        sessions = list_user_sessions(user_id=user_id)
        assert token not in str(sessions)
        assert all("token" not in key for key in sessions[0])


def test_the_requesting_session_is_marked(app: object, user_id: str) -> None:
    with app.test_request_context():
        token = _sign_in(app, user_id)
        _sign_in(app, user_id)

        sessions = list_user_sessions(user_id=user_id, current_token=token)
        assert sum(1 for item in sessions if item["is_current"]) == 1


def test_a_cli_session_is_named_after_the_approved_device(
    app: object, user_id: str
) -> None:
    with app.test_request_context(headers={"User-Agent": "python-requests/2.32"}):
        _sign_in(
            app, user_id, source="cli", device_name="MacBook-Pro", device_os="macOS 15"
        )

        session = list_user_sessions(user_id=user_id)[0]
        assert session["source"] == "cli"
        assert session["device_name"] == "MacBook-Pro"
        assert session["device_os"] == "macOS 15"


def test_revoking_a_session_removes_it(app: object, user_id: str) -> None:
    with app.test_request_context():
        _sign_in(app, user_id)
        kept = _sign_in(app, user_id)

        target = next(
            item
            for item in list_user_sessions(user_id=user_id, current_token=kept)
            if not item["is_current"]
        )
        revoke_user_session(app, user_id=user_id, session_bid=target["session_bid"])
        db.session.commit()

        remaining = list_user_sessions(user_id=user_id)
        assert target["session_bid"] not in {i["session_bid"] for i in remaining}


def test_a_session_cannot_be_revoked_from_another_account(
    app: object, user_id: str, other_user_id: str
) -> None:
    """A session id alone must not let a stranger end someone else's session."""
    with app.test_request_context():
        _sign_in(app, user_id)
        victim_session = list_user_sessions(user_id=user_id)[0]

        with pytest.raises(AppError):
            revoke_user_session(
                app,
                user_id=other_user_id,
                session_bid=victim_session["session_bid"],
            )

        assert len(list_user_sessions(user_id=user_id)) == 1


def test_revoking_others_keeps_the_current_session(app: object, user_id: str) -> None:
    with app.test_request_context():
        _sign_in(app, user_id)
        _sign_in(app, user_id)
        current = _sign_in(app, user_id)

        result = revoke_other_user_sessions(app, user_id=user_id, current_token=current)
        db.session.commit()

        assert result["revoked"] == 2
        remaining = list_user_sessions(user_id=user_id, current_token=current)
        assert len(remaining) == 1
        assert remaining[0]["is_current"] is True


def test_a_session_without_a_public_id_gets_one(app: object, user_id: str) -> None:
    """Sessions predating this feature must still be revocable."""
    with app.test_request_context():
        _sign_in(app, user_id)
        record = UserToken.query.filter(UserToken.user_id == user_id).first()
        record.session_bid = ""
        db.session.commit()

        listed = list_user_sessions(user_id=user_id)

        assert listed[0]["session_bid"]
        # And it is genuinely usable, not just present in the response.
        revoke_user_session(app, user_id=user_id, session_bid=listed[0]["session_bid"])
        db.session.commit()
        assert list_user_sessions(user_id=user_id) == []


def test_an_unknown_session_is_rejected(app: object, user_id: str) -> None:
    with app.test_request_context(), pytest.raises(AppError):
        revoke_user_session(app, user_id=user_id, session_bid="does-not-exist")


def test_expired_sessions_are_not_listed(app: object, user_id: str) -> None:
    import datetime

    from flaskr.util.datetime import now_utc

    with app.test_request_context():
        _sign_in(app, user_id)
        record = UserToken.query.filter(UserToken.user_id == user_id).first()
        record.token_expired_at = now_utc() - datetime.timedelta(days=1)
        db.session.commit()

        assert list_user_sessions(user_id=user_id) == []


def test_revocation_says_so_when_the_cache_cannot_be_cleared(
    app: object, user_id: str
) -> None:
    """A cached token outlives its row, so a failed eviction is not a success."""
    import flaskr.service.user.sessions as sessions_module

    with app.test_request_context():
        _sign_in(app, user_id)
        target = list_user_sessions(user_id=user_id)[0]

        class ExplodingCache:
            def delete(self, *_args: object) -> None:
                message = "redis is unreachable"
                raise RuntimeError(message)

        original = sessions_module.redis
        sessions_module.redis = ExplodingCache()
        try:
            with pytest.raises(AppError) as refused:
                revoke_user_session(
                    app, user_id=user_id, session_bid=target["session_bid"]
                )
        finally:
            sessions_module.redis = original

        assert refused.value.code == ERROR_CODE["server.user.sessionRevokeIncomplete"]


def test_a_session_served_from_cache_keeps_its_row_alive(
    app: object, user_id: str
) -> None:
    """Keep the row's expiry in step with a cache-served session.

    A cache hit renews only the cache entry, so without this the row ages out
    and the session vanishes from the list while still perfectly usable.
    """
    import datetime

    from flaskr.util.datetime import now_utc

    with app.test_request_context():
        token = _sign_in(app, user_id)
        record = UserToken.query.filter(UserToken.token == token).first()
        # Simulate a row that has aged while the cache kept being renewed.
        record.token_expired_at = now_utc() + datetime.timedelta(minutes=1)
        db.session.commit()

    # Authentication happens in a later read-only request. Nothing outside the
    # token store commits this request's scoped ORM session.
    with app.test_request_context():
        ttl = int(app.config.get("TOKEN_EXPIRE_TIME", 604800))
        result = token_store.get_and_refresh(
            app, token=token, expected_user_id=user_id, ttl_seconds=ttl
        )
        assert result is not None

    # A fresh request proves teardown did not roll the sliding renewal back.
    with app.test_request_context():
        refreshed = UserToken.query.filter(UserToken.token == token).first()
        assert refreshed.token_expired_at > now_utc() + datetime.timedelta(days=1)
        # And it is therefore still listed.
        assert len(list_user_sessions(user_id=user_id)) == 1


def test_a_valid_cached_session_survives_a_transient_row_refresh_failure(
    app: object, user_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed sliding-expiry write must not sign out a valid session."""
    with app.test_request_context():
        token = _sign_in(app, user_id)

    def fail_to_refresh(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(token_store, "_refresh_row_periodically", fail_to_refresh)

    with app.test_request_context():
        ttl = int(app.config.get("TOKEN_EXPIRE_TIME", 604800))
        result = token_store.get_and_refresh(
            app, token=token, expected_user_id=user_id, ttl_seconds=ttl
        )

    assert result is not None
    assert result.user_id == user_id


def test_a_session_revoked_during_its_cached_refresh_is_rejected(
    app: object, user_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not revive a row deleted between validation and expiry renewal."""
    with app.test_request_context():
        token = _sign_in(app, user_id)

    def report_missing_row(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(token_store, "_refresh_row_periodically", report_missing_row)

    with app.test_request_context():
        ttl = int(app.config.get("TOKEN_EXPIRE_TIME", 604800))
        result = token_store.get_and_refresh(
            app, token=token, expected_user_id=user_id, ttl_seconds=ttl
        )

    assert result is None


def test_a_cached_session_without_its_durable_row_is_rejected(
    app: object, user_id: str
) -> None:
    """Deleting the durable row must still revoke a cache-resident session."""
    with app.test_request_context():
        token = _sign_in(app, user_id)
        UserToken.query.filter(UserToken.token == token).delete()
        db.session.commit()

    with app.test_request_context():
        ttl = int(app.config.get("TOKEN_EXPIRE_TIME", 604800))
        result = token_store.get_and_refresh(
            app, token=token, expected_user_id=user_id, ttl_seconds=ttl
        )

    assert result is None


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        (
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/140.0 Safari/537.36 Edg/140.0",
            ("Edge", "Windows"),
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
            ("Safari", "macOS"),
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
            ("Safari", "iOS"),
        ),
        ("python-requests/2.32.3", ("", "")),
    ],
)
def test_user_agents_are_summarized_specifically(
    user_agent: str, expected: tuple[str, str]
) -> None:
    """Edge also says Chrome and Chrome also says Safari, so order matters."""
    assert describe_user_agent(user_agent) == expected

"""Verify a user can see and end their own sign-in sessions."""

import uuid

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.user.models import UserToken
from flaskr.service.user.sessions import (
    list_user_sessions,
    revoke_other_user_sessions,
    revoke_user_session,
)
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

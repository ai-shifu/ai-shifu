import uuid

from flaskr.dao import db
from flaskr.service.user.auth.base import OAuthCallbackRequest
from flaskr.service.user.auth.providers.google import GoogleAuthProvider, _encode_state
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
    UserToken as UserTokenModel,
)


class _FakeGoogleResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeGoogleSession:
    def __init__(self, profile):
        self._profile = profile

    def fetch_token(self, *_args, **_kwargs):
        return {"access_token": "fake-access-token"}

    def get(self, *_args, **_kwargs):
        return _FakeGoogleResponse(self._profile)


def _reset_user_auth_tables():
    UserTokenModel.query.delete()
    AuthCredential.query.delete()
    UserEntity.query.delete()
    db.session.commit()


def _run_google_callback(app, monkeypatch, profile):
    provider = GoogleAuthProvider()
    fake_session = _FakeGoogleSession(profile)
    monkeypatch.setattr(
        provider,
        "_create_session",
        lambda _app, _redirect_uri: fake_session,
    )
    state = _encode_state(
        app,
        {"redirect_uri": "http://localhost/login/google-callback"},
    )
    callback = OAuthCallbackRequest(code="fake-google-code", state=state)

    with app.test_request_context("/login/google-callback"):
        return provider.handle_oauth_callback(app, callback)


def test_google_unverified_email_does_not_consume_first_account_bootstrap(
    app, monkeypatch
):
    first_email = f"{uuid.uuid4().hex[:10]}@example.com"
    second_email = f"{uuid.uuid4().hex[:10]}@example.com"

    with app.app_context():
        _reset_user_auth_tables()
        try:
            first_result = _run_google_callback(
                app,
                monkeypatch,
                {
                    "sub": uuid.uuid4().hex,
                    "email": first_email,
                    "email_verified": False,
                    "name": "First Google User",
                },
            )
            first_user = UserEntity.query.filter_by(
                user_bid=first_result.user.user_id
            ).first()
            assert first_user is not None
            assert first_user.state == USER_STATE_UNREGISTERED
            assert first_user.is_creator == 0
            assert first_user.is_operator == 0

            second_result = _run_google_callback(
                app,
                monkeypatch,
                {
                    "sub": uuid.uuid4().hex,
                    "email": second_email,
                    "email_verified": True,
                    "name": "Verified Google User",
                },
            )
            second_user = UserEntity.query.filter_by(
                user_bid=second_result.user.user_id
            ).first()
            assert second_user is not None
            assert second_user.state == USER_STATE_REGISTERED
            assert second_user.is_creator == 1
            assert second_user.is_operator == 1

            first_user = UserEntity.query.filter_by(
                user_bid=first_result.user.user_id
            ).first()
            assert first_user is not None
            assert first_user.is_creator == 0
            assert first_user.is_operator == 0
        finally:
            _reset_user_auth_tables()

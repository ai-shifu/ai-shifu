"""Verify Google sign-in preserves account trust and paid state."""

import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import flaskr.common.config as common_config
import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.user.auth.base import OAuthCallbackRequest
from flaskr.service.user.auth.providers.google import GoogleAuthProvider, _encode_state
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import (
    AuthCredential,
)
from flaskr.service.user.models import (
    UserInfo as UserEntity,
)
from flaskr.service.user.models import (
    UserToken as UserTokenModel,
)
from flaskr.service.user.password_flow import write_password_credential
from flaskr.service.user.repository import create_user_entity, get_password_hash
from flaskr.service.user.token_store import token_store
from sqlalchemy import Text


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)


@pytest.fixture(autouse=True)
def clear_google_public_url_config_cache() -> Iterator[None]:
    _reset_config_cache("HOST_URL")
    yield
    _reset_config_cache("HOST_URL")


class _FakeGoogleResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _FakeGoogleSession:
    def __init__(self, profile: object, *, fetch_token_error: object = None) -> None:
        self._profile = profile
        self._fetch_token_error = fetch_token_error

    def fetch_token(self, *_args: object, **_kwargs: object) -> object:
        if self._fetch_token_error is not None:
            raise self._fetch_token_error
        return {"access_token": "fake-access-token"}

    def get(self, *_args: object, **_kwargs: object) -> object:
        return _FakeGoogleResponse(self._profile)


def _reset_user_auth_tables(*, allow_legacy_bootstrap: bool = False) -> None:
    from flaskr.service.user.installation_models import InstallationState
    from flaskr.util.datetime import now_utc

    UserTokenModel.query.delete()
    AuthCredential.query.delete()
    UserEntity.query.delete()
    InstallationState.query.delete()
    db.session.add(
        InstallationState(
            id=1,
            mode="legacy",
            initialized_at=None if allow_legacy_bootstrap else now_utc(),
        )
    )
    db.session.commit()


def _run_google_callback(
    app: object,
    monkeypatch: object,
    profile: object,
    *,
    fetch_token_error: object = None,
) -> object:
    monkeypatch.setenv("HOST_URL", "http://localhost")
    _reset_config_cache("HOST_URL")
    provider = GoogleAuthProvider()
    fake_session = _FakeGoogleSession(
        profile,
        fetch_token_error=fetch_token_error,
    )
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


def test_google_callback_commit_failure_does_not_populate_token_cache(
    app: object, test_client: object, monkeypatch: object
) -> None:
    import flaskr.route.user as user_route

    token = f"google-failed-{uuid.uuid4().hex}"
    user_id = uuid.uuid4().hex

    class FailingCommitProvider:
        def handle_oauth_callback(self, route_app: object, _request: object) -> object:
            token_store.save(
                route_app,
                user_id=user_id,
                token=token,
                ttl_seconds=60,
            )
            return SimpleNamespace(
                user=SimpleNamespace(user_id=user_id, language="en-US"),
                token=SimpleNamespace(token=token),
                is_new_user=False,
                metadata={},
            )

    def fail_commit() -> None:
        message = "simulated Google login commit failure"
        raise RuntimeError(message)

    monkeypatch.setattr(
        user_route, "get_provider", lambda _name: FailingCommitProvider()
    )
    monkeypatch.setattr(db.session, "commit", fail_commit)

    response = test_client.get(
        "/api/user/oauth/google/callback",
        query_string={"state": "state", "code": "code"},
    )
    assert response.get_json(force=True)["code"] == -1

    with app.app_context():
        assert UserTokenModel.query.filter_by(token=token).count() == 0
        assert token_store._cache.get(token_store._cache_key(app, token)) is None


def test_google_unverified_email_does_not_consume_first_account_bootstrap(
    app: object, monkeypatch: object
) -> None:
    first_email = f"{uuid.uuid4().hex[:10]}@example.com"
    second_email = f"{uuid.uuid4().hex[:10]}@example.com"

    with app.app_context():
        _reset_user_auth_tables(allow_legacy_bootstrap=True)
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


def test_google_verified_login_does_not_downgrade_paid_user(
    app: object, monkeypatch: object
) -> None:
    email = f"{uuid.uuid4().hex[:10]}@example.com"

    with app.app_context():
        _reset_user_auth_tables()
        try:
            existing_user = UserEntity(
                user_bid=uuid.uuid4().hex[:32],
                user_identify=email,
                nickname="PaidUser",
                language="en-US",
                state=USER_STATE_PAID,
                is_creator=1,
                is_operator=1,
            )
            db.session.add(existing_user)
            db.session.commit()

            result = _run_google_callback(
                app,
                monkeypatch,
                {
                    "sub": uuid.uuid4().hex,
                    "email": email,
                    "email_verified": True,
                    "name": "Paid User",
                },
            )

            stored = UserEntity.query.filter_by(user_bid=result.user.user_id).first()
            assert stored is not None
            assert stored.state == USER_STATE_PAID
            assert stored.is_creator == 1
            assert stored.is_operator == 1
        finally:
            _reset_user_auth_tables()


def test_google_existing_account_keeps_pre_profile_display_name_behavior(
    app: object,
    monkeypatch: object,
) -> None:
    email = f"{uuid.uuid4().hex[:10]}@example.com"

    with app.app_context():
        _reset_user_auth_tables()
        try:
            existing_user = UserEntity(
                user_bid=uuid.uuid4().hex[:32],
                user_identify=email,
                nickname="Canonical Name",
                learner_profile="Please call me Canonical Name.",
                language="en-US",
                state=USER_STATE_UNREGISTERED,
            )
            db.session.add(existing_user)
            db.session.commit()

            query_type = type(UserEntity.query)
            original_first = query_type.first
            reads: list[tuple[str, str, bool, bool]] = []

            def track_first(query: object) -> object:
                statement = str(query.statement)
                parameters = query.statement.compile().params
                table = (
                    "user_onboarding_states"
                    if "user_onboarding_states" in statement
                    else "user_users"
                    if "user_users" in statement
                    else "other"
                )
                reads.append(
                    (
                        table,
                        str(parameters.get("user_bid_1", "")),
                        query._for_update_arg is not None,
                        bool(query.load_options._populate_existing),
                    )
                )
                return original_first(query)

            monkeypatch.setattr(query_type, "first", track_first)
            result = _run_google_callback(
                app,
                monkeypatch,
                {
                    "sub": uuid.uuid4().hex,
                    "email": email,
                    "email_verified": True,
                    "name": "Current Google Name",
                },
            )

            assert not any(read[0] == "user_onboarding_states" for read in reads)
            assert result.user.name == "Current Google Name"
            db.session.expire_all()
            stored = UserEntity.query.filter_by(user_bid=existing_user.user_bid).one()
            assert stored.nickname == "Current Google Name"
        finally:
            _reset_user_auth_tables()


def test_google_existing_account_accepts_long_avatar_url(
    app: object,
    monkeypatch: object,
) -> None:
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    avatar_url = f"https://lh3.googleusercontent.com/a-/{'a' * 512}=s96-c"

    assert len(avatar_url) > 255
    assert isinstance(UserEntity.__table__.c.avatar.type, Text)

    with app.app_context():
        _reset_user_auth_tables()
        try:
            existing_user = UserEntity(
                user_bid=uuid.uuid4().hex[:32],
                user_identify=email,
                nickname="Existing User",
                avatar="",
                language="en-US",
                state=USER_STATE_UNREGISTERED,
            )
            db.session.add(existing_user)
            db.session.commit()

            result = _run_google_callback(
                app,
                monkeypatch,
                {
                    "sub": uuid.uuid4().hex,
                    "email": email,
                    "email_verified": True,
                    "name": "Existing User",
                    "picture": avatar_url,
                },
            )

            stored = UserEntity.query.filter_by(user_bid=result.user.user_id).one()
            assert stored.avatar == avatar_url
        finally:
            _reset_user_auth_tables()


def test_google_oauth_token_fetch_failure_propagates(
    app: object, monkeypatch: object
) -> None:
    with app.app_context():
        _reset_user_auth_tables()
        try:
            with pytest.raises(RuntimeError, match="token fetch failed"):
                _run_google_callback(
                    app,
                    monkeypatch,
                    {
                        "sub": uuid.uuid4().hex,
                        "email": f"{uuid.uuid4().hex[:10]}@example.com",
                        "email_verified": True,
                        "name": "Failure Path",
                    },
                    fetch_token_error=RuntimeError("token fetch failed"),
                )
        finally:
            _reset_user_auth_tables()


@pytest.mark.parametrize("email_verified", [False, None, "false", "true", 1])
@pytest.mark.parametrize("operator", [False, True])
def test_unverified_google_email_cannot_claim_an_existing_password_account(
    app: object, monkeypatch: object, email_verified: object, operator: bool
) -> None:
    identifier = "owner-password@example.com"
    with app.app_context():
        _reset_user_auth_tables()
        try:
            administrator = create_user_entity(
                user_bid="password-installation-owner",
                identify=identifier,
                nickname="Unchanged owner",
                state=USER_STATE_REGISTERED,
            )
            administrator.is_operator = int(operator)
            credential = write_password_credential(
                app,
                user_bid=administrator.user_bid,
                identifier=identifier,
                new_password="OwnerPassword123",
            )
            original_hash = get_password_hash(credential)
            with pytest.raises(AppError):
                _run_google_callback(
                    app,
                    monkeypatch,
                    {
                        "sub": "unrelated-unverified-subject",
                        "email": identifier,
                        "email_verified": email_verified,
                        "name": "Untrusted replacement",
                    },
                )
            db.session.expire_all()
            assert administrator.nickname == "Unchanged owner"
            assert administrator.is_operator == int(operator)
            assert get_password_hash(credential) == original_hash
            assert AuthCredential.query.filter_by(provider_name="google").count() == 0
            assert UserTokenModel.query.count() == 0
        finally:
            _reset_user_auth_tables()


def test_verified_google_email_can_use_the_existing_password_account(
    app: object, monkeypatch: object
) -> None:
    identifier = "verified-owner@example.com"
    with app.app_context():
        _reset_user_auth_tables()
        try:
            administrator = create_user_entity(
                user_bid="verified-password-owner",
                identify=identifier,
                state=USER_STATE_REGISTERED,
            )
            administrator.is_operator = 1
            write_password_credential(
                app,
                user_bid=administrator.user_bid,
                identifier=identifier,
                new_password="OwnerPassword123",
            )
            result = _run_google_callback(
                app,
                monkeypatch,
                {
                    "sub": "verified-google-owner",
                    "email": identifier,
                    "email_verified": True,
                },
            )
            assert result.user.user_id == administrator.user_bid
            assert result.user.is_operator is True
        finally:
            _reset_user_auth_tables()


@pytest.mark.parametrize("same_subject", [False, True])
def test_unverified_google_callback_requires_the_previously_bound_subject(
    app: object, monkeypatch: object, same_subject: bool
) -> None:
    with app.app_context():
        _reset_user_auth_tables()
        try:
            profile = {
                "sub": "original-google-subject",
                "email": "unverified-new-google@example.com",
                "email_verified": False,
            }
            original = _run_google_callback(app, monkeypatch, profile)
            callback_profile = {
                **profile,
                "sub": profile["sub"] if same_subject else "unrelated-google-subject",
            }
            if same_subject:
                result = _run_google_callback(app, monkeypatch, callback_profile)
                assert result.user.user_id == original.user.user_id
            else:
                with pytest.raises(AppError):
                    _run_google_callback(app, monkeypatch, callback_profile)
            assert UserEntity.query.count() == 1
            assert (
                AuthCredential.query.filter_by(provider_name="google").one().subject_id
                == profile["sub"]
            )
        finally:
            _reset_user_auth_tables()

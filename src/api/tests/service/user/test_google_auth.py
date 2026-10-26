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
    from flaskr.service.user.installation_models import (
        InstallationState,
        LocalAdminAccount,
    )
    from flaskr.util.datetime import now_utc

    UserTokenModel.query.delete()
    LocalAdminAccount.query.delete()
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
    current_user_id: str | None = None,
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
    callback = OAuthCallbackRequest(
        code="fake-google-code", state=state, current_user_id=current_user_id
    )

    with app.test_request_context("/login/google-callback"):
        return provider.handle_oauth_callback(app, callback)


@pytest.mark.parametrize("registered_origin", [False, True])
@pytest.mark.parametrize(
    "ownership_evidence",
    ["unverified", "verified_google", "verified_email", "password"],
)
def test_google_canonical_evidence_controls_retained_password_label_ownership(
    app: object,
    monkeypatch: object,
    registered_origin: bool,
    ownership_evidence: str,
) -> None:
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.user import email_flow, local_accounts
    from flaskr.service.user.consts import (
        CREDENTIAL_STATE_UNVERIFIED,
        CREDENTIAL_STATE_VERIFIED,
    )
    from flaskr.service.user.models import UserVerifyCode
    from flaskr.service.user.repository import (
        find_password_identity_user_bids,
        upsert_credential,
    )

    identifier = "retained-owner@example.com"
    second_email = "second-owner@example.com"
    password = "OwnerPassword123"
    paths = ("/api/user/login_password", "/api/installation/login")

    def login(path: str, label: str, supplied_password: str) -> dict:
        return (
            app.test_client()
            .post(
                path,
                json={"identifier": label, "password": supplied_password},
                headers={"Origin": "http://localhost:8080"},
            )
            .get_json(force=True)
        )

    with app.app_context():
        _reset_user_auth_tables()
        try:
            with unit_of_work():
                owner_bid = local_accounts.provision_local_admin_account(
                    app, identifier=identifier, password=password
                )
                record = UserVerifyCode(
                    mail=second_email,
                    verify_code="5678",
                    verify_code_type=2,
                    verify_code_send=1,
                    verify_code_used=0,
                )
                db.session.add(record)
            token, created, _context = email_flow.verify_email_code(
                app, user_id=owner_bid, email=second_email, code="5678"
            )
            assert token.userInfo.user_id == owner_bid
            assert not created
            assert record.verify_code_used == 1
            with unit_of_work():
                db.session.delete(record)
            owner = UserEntity.query.filter_by(user_bid=owner_bid).one()
            owner_credential = AuthCredential.query.filter_by(
                user_bid=owner_bid, provider_name="password"
            ).one()
            original_hash = get_password_hash(owner_credential)
            assert owner.user_identify == second_email
            assert owner_credential.identifier == identifier
            for path in paths:
                initial = login(path, identifier, password)
                assert initial["code"] == 0
                assert initial["data"]["userInfo"]["user_id"] == owner_bid

            origin_bid = None
            if registered_origin:
                with unit_of_work():
                    origin_bid = "registered-google-origin"
                    create_user_entity(
                        user_bid=origin_bid,
                        identify="registered-origin@example.com",
                        state=USER_STATE_REGISTERED,
                    )
                    write_password_credential(
                        app,
                        user_bid=origin_bid,
                        identifier="registered-origin@example.com",
                        new_password="OriginPassword123",
                    )
            google_profile = {
                "sub": "unverified-retained-password-label-subject",
                "email": identifier,
                "email_verified": False,
            }
            google = _run_google_callback(
                app, monkeypatch, google_profile, current_user_id=origin_bid
            )
            claimant_bid = google.user.user_id
            assert claimant_bid != owner_bid
            if registered_origin:
                assert claimant_bid == origin_bid
            claimant = UserEntity.query.filter_by(user_bid=claimant_bid).one()
            assert claimant.user_identify == identifier
            assert claimant.state == (
                USER_STATE_REGISTERED if registered_origin else USER_STATE_UNREGISTERED
            )
            google_credential = AuthCredential.query.filter_by(
                user_bid=claimant_bid, provider_name="google", identifier=identifier
            ).one()
            assert google_credential.state == CREDENTIAL_STATE_UNVERIFIED
            assert get_password_hash(owner_credential) == original_hash
            if registered_origin:
                repeated = _run_google_callback(app, monkeypatch, google_profile)
                assert repeated.user.user_id == claimant_bid
                assert google_credential.state == CREDENTIAL_STATE_UNVERIFIED

            with unit_of_work():
                if ownership_evidence == "verified_google":
                    google_credential.state = CREDENTIAL_STATE_VERIFIED
                elif ownership_evidence == "verified_email":
                    upsert_credential(
                        app,
                        user_bid=claimant_bid,
                        provider_name="email",
                        subject_id=identifier,
                        subject_format="email",
                        identifier=identifier,
                        metadata={},
                        verified=True,
                    )
                elif ownership_evidence == "password":
                    write_password_credential(
                        app,
                        user_bid=claimant_bid,
                        identifier=identifier,
                        new_password="OriginPassword123",
                    )

            candidates = find_password_identity_user_bids(identifier)
            results = {path: login(path, identifier, password) for path in paths}
            expected = (
                {owner_bid}
                if ownership_evidence == "unverified"
                else {owner_bid, claimant_bid}
            )
            assert candidates == expected, {
                "candidates": candidates,
                "login_codes": {
                    path: result["code"] for path, result in results.items()
                },
            }
            for path, result in results.items():
                if ownership_evidence == "unverified":
                    assert result["code"] == 0
                    assert result["data"]["userInfo"]["user_id"] == owner_bid
                else:
                    assert result["code"] != 0
                assert login(path, identifier, "OriginPassword123")["code"] != 0
            with unit_of_work():
                assert (
                    find_password_identity_user_bids(identifier, for_update=True)
                    == expected
                )
            if registered_origin:
                origin_login = login(
                    "/api/user/login_password",
                    "registered-origin@example.com",
                    "OriginPassword123",
                )
                assert origin_login["code"] == 0
                assert origin_login["data"]["userInfo"]["user_id"] == origin_bid
        finally:
            _reset_user_auth_tables()


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

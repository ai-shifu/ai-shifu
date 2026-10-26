"""Verify authentication provider dispatch and credential result contracts."""

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from flaskr.service.common.dtos import UserInfo, UserToken
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user.auth import factory
from flaskr.service.user.auth.base import (
    ChallengeRequest,
    OAuthCallbackRequest,
    VerificationRequest,
)
from flaskr.service.user.auth.providers import email, password, phone
from flaskr.service.user.models import AuthCredential


@pytest.fixture
def user_token() -> UserToken:
    return UserToken(
        UserInfo(
            user_id="account-1",
            username="teacher",
            name="Teacher",
            email="learner@example.com",
            mobile="13800138000",
            user_state=1,
            wx_openid="",
            language="en-US",
        ),
        "login-token",
    )


def test_provider_registry_is_case_insensitive_and_returns_fresh_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(factory, "_REGISTRY", {})
    factory.register_provider(phone.PhoneAuthProvider)
    assert factory.has_provider("PHONE")
    assert tuple(factory.registered_providers()) == ("phone",)
    assert isinstance(factory.get_provider("Phone"), phone.PhoneAuthProvider)
    assert factory.get_provider("phone") is not factory.get_provider("phone")
    with pytest.raises(
        factory.ProviderAlreadyRegisteredError, match="already registered"
    ):
        factory.register_provider(phone.PhoneAuthProvider)
    factory.clear_providers()
    assert not factory.has_provider("phone")
    with pytest.raises(factory.ProviderNotFoundError, match="not registered"):
        factory.get_provider("phone")


@pytest.mark.parametrize(
    "provider",
    [type("MissingName", (), {}), type("EmptyName", (), {"provider_name": ""})],
)
def test_registry_rejects_nameless_providers(
    monkeypatch: pytest.MonkeyPatch, provider: type
) -> None:
    monkeypatch.setattr(factory, "_REGISTRY", {})
    with pytest.raises(ValueError, match="non-empty provider_name"):
        factory.register_provider(provider)
    assert tuple(factory.registered_providers()) == ()


@pytest.mark.parametrize("operation", ["challenge", "begin", "callback"])
def test_unsupported_provider_operations_have_explicit_failures(
    app: object, operation: str
) -> None:
    provider = password.PasswordAuthProvider()
    methods = {
        "challenge": (
            provider.send_challenge,
            ChallengeRequest(identifier="person@example.com"),
        ),
        "begin": (provider.begin_oauth, {}),
        "callback": (provider.handle_oauth_callback, OAuthCallbackRequest()),
    }
    method, payload = methods[operation]
    with pytest.raises(NotImplementedError, match="password"):
        method(app, payload)


def test_email_challenge_normalizes_identifier_and_preserves_delivery_metadata(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    sender = Mock(return_value={"expire_in": 90})
    monkeypatch.setattr(email, "send_email_code", sender)
    response = email.EmailAuthProvider().send_challenge(
        app,
        ChallengeRequest(
            identifier="  Person@Example.com  ",
            metadata={"ip": "203.0.113.8", "language": "fr-FR"},
        ),
    )
    sender.assert_called_once_with(
        app, "person@example.com", ip="203.0.113.8", language="fr-FR"
    )
    assert response.identifier == "person@example.com"
    assert response.expire_in == 90
    assert response.metadata == {"ip": "203.0.113.8", "language": "fr-FR"}


@pytest.mark.parametrize(
    ("metadata", "required"), [({}, True), ({"require_captcha": False}, False)]
)
def test_phone_challenge_normalizes_number_and_requires_captcha_by_default(
    app: object, monkeypatch: pytest.MonkeyPatch, metadata: dict, required: bool
) -> None:
    sender = Mock(return_value={})
    monkeypatch.setattr(phone, "send_sms_code", sender)
    response = phone.PhoneAuthProvider().send_challenge(
        app, ChallengeRequest(identifier="+86 13800138000", metadata=metadata)
    )
    sender.assert_called_once_with(
        app, "13800138000", None, None, require_captcha=required
    )
    assert response.identifier == "13800138000"
    assert response.expire_in == 0
    assert response.metadata == {"ip": None}


@pytest.mark.parametrize("provider_name", ["email", "phone"])
def test_code_provider_preserves_account_and_login_context_in_result(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    user_token: UserToken,
    provider_name: str,
) -> None:
    module = email if provider_name == "email" else phone
    provider = (
        email.EmailAuthProvider()
        if provider_name == "email"
        else phone.PhoneAuthProvider()
    )
    identifier = "PERSON@EXAMPLE.COM" if provider_name == "email" else "+8613800138000"
    normalized = "person@example.com" if provider_name == "email" else "13800138000"
    verify = Mock(
        return_value=(
            user_token,
            True,
            {"language": "en-US", "empty": None, "creator_granted_now": False},
        )
    )
    credential = AuthCredential(user_bid="account-1", provider_name=provider_name)
    finder = Mock(return_value=credential)
    monkeypatch.setattr(module, f"verify_{provider_name}_code", verify)
    monkeypatch.setattr(
        module,
        "load_user_aggregate",
        Mock(return_value=SimpleNamespace(user_bid="account-1")),
    )
    monkeypatch.setattr(module, "find_credential", finder)
    result = provider.verify(
        app,
        VerificationRequest(
            identifier=identifier,
            code="2468",
            metadata={
                "user_id": "temporary",
                "course_id": "course",
                "language": "en-US",
                "login_context": "admin",
            },
        ),
    )
    verify.assert_called_once_with(
        app,
        "temporary",
        normalized,
        "2468",
        course_id="course",
        language="en-US",
        login_context="admin",
    )
    finder.assert_called_once_with(
        provider_name=provider_name, identifier=normalized, user_bid="account-1"
    )
    assert result.user is user_token.userInfo
    assert result.token is user_token
    assert result.credential is credential
    assert result.is_new_user is True
    assert result.metadata == {
        "user_bid": "account-1",
        "language": "en-US",
        "creator_granted_now": False,
    }


@pytest.mark.parametrize("provider_name", ["email", "phone"])
def test_code_provider_does_not_issue_a_result_for_a_missing_account(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    user_token: UserToken,
    provider_name: str,
) -> None:
    module = email if provider_name == "email" else phone
    provider = (
        email.EmailAuthProvider()
        if provider_name == "email"
        else phone.PhoneAuthProvider()
    )
    monkeypatch.setattr(
        module,
        f"verify_{provider_name}_code",
        Mock(return_value=(user_token, False, {})),
    )
    monkeypatch.setattr(module, "load_user_aggregate", Mock(return_value=None))
    with pytest.raises(
        RuntimeError, match=f"missing after {provider_name} verification"
    ):
        provider.verify(
            app, VerificationRequest(identifier="person@example.com", code="2468")
        )


@pytest.mark.parametrize(
    ("identifier", "secret"),
    [("", "password"), ("+86", "password"), ("person@example.com", "")],
)
def test_password_provider_rejects_empty_credentials_before_account_lookup(
    app: object, monkeypatch: pytest.MonkeyPatch, identifier: str, secret: str
) -> None:
    lookup = Mock()
    monkeypatch.setattr(password, "load_user_aggregate_by_identifier", lookup)
    with app.app_context(), pytest.raises(AppError) as error:
        password.PasswordAuthProvider().verify(
            app, VerificationRequest(identifier=identifier, code=secret)
        )
    assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]
    lookup.assert_not_called()


@pytest.mark.parametrize(
    "failure", ["missing_account", "missing_credential", "empty_hash", "wrong_password"]
)
def test_password_failures_share_one_public_error_and_never_mint_tokens(
    app: object, monkeypatch: pytest.MonkeyPatch, user_token: UserToken, failure: str
) -> None:
    aggregate = (
        None if failure == "missing_account" else SimpleNamespace(user_bid="account-1")
    )
    credential = AuthCredential(user_bid="account-1", provider_name="password")
    monkeypatch.setattr(
        password, "load_user_aggregate_by_identifier", Mock(return_value=aggregate)
    )
    monkeypatch.setattr(
        password,
        "list_credentials",
        Mock(return_value=[] if failure == "missing_credential" else [credential]),
    )
    monkeypatch.setattr(
        password,
        "get_password_hash",
        Mock(return_value="" if failure == "empty_hash" else "stored-hash"),
    )
    monkeypatch.setattr(password, "verify_password", Mock(return_value=False))
    mint = Mock()
    monkeypatch.setattr(password, "create_token_value", mint)
    monkeypatch.setattr(
        password,
        "build_user_info_from_aggregate",
        Mock(return_value=user_token.userInfo),
    )
    with app.app_context(), pytest.raises(AppError) as error:
        password.PasswordAuthProvider().verify(
            app, VerificationRequest(identifier="person@example.com", code="wrong")
        )
    assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]
    mint.assert_not_called()


@pytest.mark.parametrize(
    ("identifier", "normalized"),
    [
        ("  PERSON@EXAMPLE.COM  ", "person@example.com"),
        ("+86 13800138000", "13800138000"),
    ],
)
def test_password_login_finds_password_by_account_across_identifier_types(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    user_token: UserToken,
    identifier: str,
    normalized: str,
) -> None:
    aggregate = SimpleNamespace(user_bid="account-1")
    credential = AuthCredential(
        credential_bid="password-credential-1",
        user_bid="account-1",
        provider_name="password",
        identifier="another-login@example.com",
    )
    lookup = Mock(return_value=aggregate)
    credentials = Mock(return_value=[credential])
    monkeypatch.setattr(password, "load_user_aggregate_by_identifier", lookup)
    monkeypatch.setattr(password, "list_credentials", credentials)
    monkeypatch.setattr(password, "get_password_hash", Mock(return_value="stored-hash"))
    verifier = Mock(return_value=True)
    monkeypatch.setattr(password, "verify_password", verifier)
    monkeypatch.setattr(
        password,
        "build_user_info_from_aggregate",
        Mock(return_value=user_token.userInfo),
    )
    mint = Mock(return_value="issued-token")
    monkeypatch.setattr(password, "create_token_value", mint)
    with app.app_context():
        result = password.PasswordAuthProvider().verify(
            app, VerificationRequest(identifier=identifier, code="correct")
        )
    # Resolve the alias again under the account guard before checking credentials.
    assert lookup.call_args_list == [
        call(normalized, providers=["phone", "email"]),
        call(normalized, providers=["phone", "email"]),
    ]
    mint.assert_called_once_with(app, "account-1")
    credentials.assert_called_once_with(user_bid="account-1", provider_name="password")
    verifier.assert_called_once_with("correct", "stored-hash")
    assert result.user is user_token.userInfo
    assert result.token.token == "issued-token"
    assert result.credential is credential
    assert result.is_new_user is False
    assert result.metadata == {
        "user_bid": "account-1",
        "verified_identifier": normalized,
        "password_credential_bid": "password-credential-1",
        "password_credential_identifier": "another-login@example.com",
    }

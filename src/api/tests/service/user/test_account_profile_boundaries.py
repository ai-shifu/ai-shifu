"""Protect profile updates and post-auth extension failure boundaries."""

import uuid
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import common, post_auth, repository
from flaskr.service.user.auth.base import AuthResult
from flaskr.service.user.consts import CREDENTIAL_STATE_UNVERIFIED
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity


@pytest.fixture
def account(app: object) -> object:
    account_id = uuid.uuid4().hex
    with app.app_context():
        repository.create_user_entity(
            user_bid=account_id,
            identify=account_id,
            nickname="Before",
            language="en-US",
        )
        db.session.commit()
        aggregate = repository.load_user_aggregate(account_id)
        yield repository.build_user_info_from_aggregate(aggregate)
        db.session.rollback()
        AuthCredential.query.filter_by(user_bid=account_id).delete()
        UserEntity.query.filter_by(user_bid=account_id).delete()
        db.session.commit()


def test_profile_update_normalizes_contact_credentials_without_verifying_them(
    app: object, account: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_profiles = Mock()
    monkeypatch.setattr(common, "save_user_profiles", save_profiles)
    result = common.update_user_info(
        app,
        account,
        "After",
        email="PERSON@EXAMPLE.COM",
        mobile="+86 13800138000",
        language="fr-FR",
        avatar="https://example.com/avatar.png",
    )
    assert result.name == "After"
    assert result.language == "fr-FR"
    assert result.user_avatar == "https://example.com/avatar.png"
    credentials = repository.list_credentials(user_bid=account.user_id)
    assert {
        (credential.provider_name, credential.identifier, credential.state)
        for credential in credentials
    } == {
        ("email", "person@example.com", CREDENTIAL_STATE_UNVERIFIED),
        ("phone", "13800138000", CREDENTIAL_STATE_UNVERIFIED),
    }
    args = save_profiles.call_args.args
    assert args[:3] == (app, account.user_id, "")
    assert {profile.key: profile.value for profile in args[3]} == {
        "sys_user_nickname": "After",
        "sys_user_language": "fr-FR",
    }


def test_avatar_only_update_does_not_rewrite_profile_or_create_empty_credentials(
    app: object, account: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_profiles = Mock()
    monkeypatch.setattr(common, "save_user_profiles", save_profiles)
    result = common.update_user_info(
        app, account, None, email="", mobile="", avatar="https://example.com/new.png"
    )
    assert result.name == "Before"
    assert result.user_avatar == "https://example.com/new.png"
    save_profiles.assert_not_called()
    assert repository.list_credentials(user_bid=account.user_id) == []


def test_invalid_profile_language_preserves_existing_account(
    app: object, account: object
) -> None:
    with pytest.raises(AppError):
        common.update_user_info(
            app, account, "Cannot persist", language="unsupported-language"
        )
    db.session.expire_all()
    entity = repository.get_user_entity_by_bid(account.user_id)
    assert entity.nickname == "Before"
    assert entity.language == "en-US"


@pytest.mark.parametrize("user", [None, SimpleNamespace(user_id="missing-account")])
def test_update_missing_account_has_a_stable_error(app: object, user: object) -> None:
    with app.app_context(), pytest.raises(AppError) as error:
        common.update_user_info(app, user, "After")
    assert error.value.code == ERROR_CODE["server.user.userNotFound"]


def test_sms_compatibility_entry_point_forwards_full_login_context(
    app: object, account: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.common.dtos import UserToken

    token = UserToken(account, "issued-token")
    provider = Mock()
    provider.verify.return_value = AuthResult(user=account, token=token)
    resolver = Mock(return_value=provider)
    monkeypatch.setattr(common, "get_provider", resolver)
    result = common.verify_sms_code(
        app,
        "temporary",
        "13800138000",
        "2468",
        course_id="course",
        language="fr-FR",
        login_context="admin",
    )
    resolver.assert_called_once_with("phone")
    assert result is token
    args = provider.verify.call_args.args
    assert args[0] is app
    assert args[1].identifier == "13800138000"
    assert args[1].code == "2468"
    assert args[1].metadata == {
        "user_id": "temporary",
        "course_id": "course",
        "language": "fr-FR",
        "login_context": "admin",
    }


@pytest.mark.parametrize(
    "manager", [None, SimpleNamespace(), SimpleNamespace(extension_functions=None)]
)
def test_post_auth_without_handlers_preserves_the_original_context(
    app: object, monkeypatch: pytest.MonkeyPatch, manager: object
) -> None:
    monkeypatch.setattr(post_auth, "get_plugin_manager", lambda: manager)
    context = post_auth.PostAuthContext(user_id="account", source="password")
    assert post_auth.run_post_auth_extensions(app, context) is context


def test_post_auth_handlers_chain_valid_contexts_and_isolate_failures(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = post_auth.PostAuthContext(user_id="account", source="email")
    updated = replace(initial, creator_granted_now=True)
    first = Mock(return_value=updated)
    invalid = Mock(return_value={"user_id": "cannot-replace"})
    failed = Mock(side_effect=RuntimeError("extension unavailable"))
    final = Mock(return_value=None)
    monkeypatch.setattr(
        post_auth,
        "get_plugin_manager",
        lambda: SimpleNamespace(
            extension_functions={
                "run_post_auth_extensions": [first, invalid, failed, final]
            }
        ),
    )
    assert post_auth.run_post_auth_extensions(app, initial) is updated
    first.assert_called_once_with(initial, app=app)
    invalid.assert_called_once_with(updated, app=app)
    failed.assert_called_once_with(updated, app=app)
    final.assert_called_once_with(updated, app=app)

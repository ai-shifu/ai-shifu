"""Verify guest-account reuse, WeChat binding, and avatar storage cleanup."""

import uuid
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.user import repository, user
from flaskr.service.user.models import AuthCredential, UserConversion, UserToken
from flaskr.service.user.models import UserInfo as UserEntity


@pytest.fixture
def identity(app: object) -> Iterator[SimpleNamespace]:
    with app.test_request_context():
        context = SimpleNamespace(user_bid=uuid.uuid4().hex, temp_id=uuid.uuid4().hex)
        repository.create_user_entity(
            user_bid=context.user_bid, identify=context.user_bid
        )
        db.session.commit()
        yield context
        db.session.rollback()
        guest_ids = [
            row.user_id
            for row in UserConversion.query.filter_by(
                conversion_id=context.temp_id
            ).all()
        ]
        account_ids = [context.user_bid, *guest_ids]
        UserToken.query.filter(UserToken.user_id.in_(account_ids)).delete(
            synchronize_session=False
        )
        AuthCredential.query.filter(AuthCredential.user_bid.in_(account_ids)).delete(
            synchronize_session=False
        )
        UserConversion.query.filter_by(conversion_id=context.temp_id).delete()
        UserEntity.query.filter(UserEntity.user_bid.in_(account_ids)).delete(
            synchronize_session=False
        )
        db.session.commit()


def test_guest_identifier_reuses_account_and_issues_a_distinct_session(
    app: object, identity: SimpleNamespace
) -> None:
    first = user.generate_temp_user(app, identity.temp_id, language="fr-FR")
    second = user.generate_temp_user(app, identity.temp_id, language="en-US")
    assert first.userInfo.user_id == second.userInfo.user_id
    assert first.token != second.token
    assert second.userInfo.language == "fr-FR"
    assert UserConversion.query.filter_by(conversion_id=identity.temp_id).count() == 1
    assert UserToken.query.filter_by(user_id=first.userInfo.user_id).count() == 2


@pytest.mark.parametrize("existing_conversion", [False, True])
def test_wechat_login_reuses_bound_account_even_when_guest_conversion_differs(
    app: object,
    identity: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    existing_conversion: bool,
) -> None:
    repository.upsert_wechat_credentials(
        app,
        user_bid=identity.user_bid,
        open_id="bound-open-id",
        union_id="bound-union-id",
        open_identifier="creator-app:bound-open-id",
        union_identifier="creator-app:bound-union-id",
    )
    db.session.commit()
    if existing_conversion:
        user.generate_temp_user(app, identity.temp_id)
    monkeypatch.setattr(
        user,
        "get_wechat_access_token",
        Mock(return_value={"openid": "bound-open-id", "unionid": "bound-union-id"}),
    )
    monkeypatch.setattr(user, "_context_wechat_app_id", lambda _app: "creator-app")
    result = user.generate_temp_user(
        app, identity.temp_id, wx_code="authorization-code"
    )
    assert result.userInfo.user_id == identity.user_bid
    assert result.userInfo.wx_openid == "bound-open-id"
    assert result.token


@pytest.mark.parametrize("existing_conversion", [False, True])
def test_wechat_login_binds_a_new_subject_to_the_guest_account(
    app: object,
    identity: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    existing_conversion: bool,
) -> None:
    previous = (
        user.generate_temp_user(app, identity.temp_id) if existing_conversion else None
    )
    monkeypatch.setattr(
        user,
        "get_wechat_access_token",
        Mock(return_value={"openid": "fresh-open", "unionid": "fresh-union"}),
    )
    monkeypatch.setattr(user, "_context_wechat_app_id", lambda _app: "creator-app")
    result = user.generate_temp_user(
        app, identity.temp_id, wx_code="authorization-code"
    )
    if previous:
        assert result.userInfo.user_id == previous.userInfo.user_id
    credentials = repository.list_credentials(
        user_bid=result.userInfo.user_id, provider_name="wechat"
    )
    assert {credential.identifier for credential in credentials} == {
        "creator-app:fresh-open",
        "creator-app:fresh-union",
    }
    assert (
        repository.load_user_aggregate(result.userInfo.user_id).wechat_union_id_for_app(
            "creator-app"
        )
        == "fresh-union"
    )


@pytest.mark.parametrize("provider_result", [None, {}])
def test_guest_creation_survives_wechat_response_without_subjects(
    app: object,
    identity: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    provider_result: object,
) -> None:
    monkeypatch.setattr(
        user, "get_wechat_access_token", Mock(return_value=provider_result)
    )
    result = user.generate_temp_user(
        app, identity.temp_id, wx_code="authorization-code"
    )
    assert result.token
    assert repository.list_credentials(user_bid=result.userInfo.user_id) == []


def test_update_wechat_binding_requires_existing_account(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    exchange = Mock()
    monkeypatch.setattr(user, "get_wechat_access_token", exchange)
    assert user.update_user_open_id(app, "missing-account", "authorization-code") == ""
    exchange.assert_not_called()


@pytest.mark.parametrize("provider_result", [None, {}, {"openid": ""}])
def test_update_wechat_binding_does_not_create_empty_credentials(
    app: object,
    identity: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    provider_result: object,
) -> None:
    monkeypatch.setattr(
        user, "get_wechat_access_token", Mock(return_value=provider_result)
    )
    assert user.update_user_open_id(app, identity.user_bid, "authorization-code") == ""
    assert repository.list_credentials(user_bid=identity.user_bid) == []


def test_update_wechat_binding_is_idempotent_and_scoped_to_creator_app(
    app: object, identity: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        user,
        "get_wechat_access_token",
        Mock(return_value={"openid": "updated-open", "unionid": "updated-union"}),
    )
    monkeypatch.setattr(user, "_context_wechat_app_id", lambda _app: "creator-app")
    assert (
        user.update_user_open_id(app, identity.user_bid, "authorization-code")
        == "updated-open"
    )
    first_ids = [
        credential.credential_bid
        for credential in repository.list_credentials(user_bid=identity.user_bid)
    ]
    assert (
        user.update_user_open_id(app, identity.user_bid, "authorization-code")
        == "updated-open"
    )
    assert [
        credential.credential_bid
        for credential in repository.list_credentials(user_bid=identity.user_bid)
    ] == first_ids
    assert (
        repository.load_user_aggregate(identity.user_bid).wechat_open_id_for_app(
            "creator-app"
        )
        == "updated-open"
    )


def test_wechat_configuration_errors_are_not_silently_replaced_by_platform_app(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(user, "get_context_creator_bid", lambda: " teacher ")
    resolver = Mock(side_effect=RuntimeError("integration unavailable"))
    monkeypatch.setattr(user, "resolve_creator_wechat_oauth_app_id", resolver)
    with pytest.raises(RuntimeError, match="integration unavailable"):
        user._context_wechat_app_id(app)
    resolver.assert_called_once_with("teacher")


@pytest.mark.parametrize(
    "url", ["", "https://example.com/avatar.png", "https://example.com/storage/default"]
)
def test_non_storage_avatar_urls_never_trigger_local_deletion(
    app: object, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    resolver = Mock()
    monkeypatch.setattr(user, "get_local_storage_path", resolver)
    user._try_delete_local_file_by_url(app, url)
    resolver.assert_not_called()


def test_local_avatar_cleanup_removes_only_the_resolved_file(
    app: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    avatar = tmp_path / "avatar.png"
    avatar.write_bytes(b"image")
    resolver = Mock(return_value=avatar)
    monkeypatch.setattr(user, "get_local_storage_path", resolver)
    user._try_delete_local_file_by_url(
        app, "https://example.com/storage/default/nested/avatar.png?version=1"
    )
    assert not avatar.exists()
    resolver.assert_called_once_with("default", "nested/avatar.png")
    user._try_delete_local_file_by_url(
        app, "https://example.com/storage/default/nested/avatar.png"
    )


def test_avatar_cleanup_errors_do_not_mask_the_original_upload_failure(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        user,
        "get_local_storage_path",
        Mock(side_effect=ValueError("invalid storage key")),
    )
    user._try_delete_local_file_by_url(
        app, "https://example.com/storage/default/avatar.png"
    )
    monkeypatch.setattr(
        user, "get_oss_config", Mock(side_effect=RuntimeError("storage unavailable"))
    )
    user._delete_uploaded_avatar(
        app, SimpleNamespace(url="", provider="oss", object_key="orphan")
    )


@pytest.mark.parametrize("exists", [False, True])
def test_orphaned_oss_avatar_is_removed_when_the_object_exists(
    app: object, monkeypatch: pytest.MonkeyPatch, exists: bool
) -> None:
    bucket = Mock()
    bucket.object_exists.return_value = exists
    monkeypatch.setattr(user, "get_oss_config", Mock(return_value=object()))
    monkeypatch.setattr(user, "create_oss_bucket", Mock(return_value=bucket))
    user._delete_uploaded_avatar(
        app, SimpleNamespace(url="", provider="oss", object_key="orphan")
    )
    if exists:
        bucket.delete_object.assert_called_once_with("orphan")
    else:
        bucket.delete_object.assert_not_called()

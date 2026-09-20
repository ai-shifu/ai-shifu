"""Verify user route envelopes, identity forwarding, and validation contracts."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.route import user as routes
from flaskr.service.common.dtos import UserInfo, UserToken
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.user.auth.base import AuthResult
from flaskr.service.user.dtos import UserProfileLabelDTO


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch) -> UserInfo:
    user = UserInfo(
        "account",
        "teacher",
        "Teacher",
        "person@example.com",
        "13800138000",
        1,
        "",
        "en-US",
    )
    monkeypatch.setattr(routes, "validate_user", Mock(return_value=user))
    return user


@pytest.mark.parametrize(
    ("path", "payload", "field"),
    [
        ("login_password", {}, "identifier"),
        ("login_password", {"identifier": "person@example.com"}, "password"),
        ("set_password", {}, "code"),
        ("set_password", {"code": "2468"}, "new_password"),
        ("change_password", {}, "old_password"),
        ("change_password", {"old_password": "Oldpass1"}, "new_password"),
        ("reset_password", {}, "identifier"),
        ("reset_password", {"identifier": "person@example.com"}, "code"),
        (
            "reset_password",
            {"identifier": "person@example.com", "code": "2468"},
            "new_password",
        ),
        ("update_profile", {}, "profiles"),
        ("update_openid", {}, "wxcode"),
        ("submit-feedback", {}, "feedback"),
    ],
)
@pytest.mark.usefixtures("signed_in")
def test_required_user_route_fields_have_the_shared_parameter_error(
    test_client: object, path: str, payload: dict, field: str
) -> None:
    result = test_client.post(f"/api/user/{path}", json=payload).get_json(force=True)
    assert result["code"] == ERROR_CODE["server.common.paramsError"]
    assert field in result["message"]


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("Ab1", "passwordTooShort"),
        ("12345678", "passwordNeedsLetter"),
        ("abcdefgh", "passwordNeedsDigit"),
    ],
)
@pytest.mark.usefixtures("signed_in")
def test_password_strength_errors_do_not_reach_credential_writes(
    test_client: object, monkeypatch: pytest.MonkeyPatch, password: str, code: str
) -> None:
    change = Mock()
    monkeypatch.setattr(routes.password_flow, "change_password", change)
    result = test_client.post(
        "/api/user/change_password",
        json={"old_password": "Oldpass1", "new_password": password},
    ).get_json(force=True)
    assert result["code"] == ERROR_CODE[f"server.user.{code}"]
    change.assert_not_called()


@pytest.mark.usefixtures("signed_in")
def test_password_change_passes_authenticated_account_and_returns_success(
    app: object, test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    change = Mock()
    monkeypatch.setattr(routes.password_flow, "change_password", change)
    result = test_client.post(
        "/api/user/change_password",
        json={"old_password": "Oldpass1", "new_password": "Newpass2"},
    ).get_json(force=True)
    assert result == {"code": 0, "message": "success", "data": {"success": True}}
    change.assert_called_once_with(
        app, user_bid="account", old_password="Oldpass1", new_password="Newpass2"
    )


@pytest.mark.usefixtures("signed_in")
def test_session_routes_forward_the_same_current_token_used_for_authentication(
    app: object, test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = Mock(return_value=[])
    revoke = Mock(return_value={"revoked": 1})
    others = Mock(return_value={"revoked": 2})
    monkeypatch.setattr(routes, "list_user_sessions", listing)
    monkeypatch.setattr(routes, "revoke_user_session", revoke)
    monkeypatch.setattr(routes, "revoke_other_user_sessions", others)
    assert (
        test_client.get(
            "/api/user/sessions", headers={"Token": "header-token"}
        ).get_json(force=True)["data"]
        == []
    )
    listing.assert_called_once_with(user_id="account", current_token="header-token")
    assert test_client.post(
        "/api/user/sessions/revoke", json={"session_bid": "public-session"}
    ).get_json(force=True)["data"] == {"revoked": 1}
    revoke.assert_called_once_with(app, user_id="account", session_bid="public-session")
    assert test_client.post(
        "/api/user/sessions/revoke-others", json={"token": "body-token"}
    ).get_json(force=True)["data"] == {"revoked": 2}
    others.assert_called_once_with(app, user_id="account", current_token="body-token")


@pytest.mark.usefixtures("signed_in")
def test_device_routes_use_authenticated_account_and_forwarded_client_ip(
    app: object, test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    pending = Mock(return_value={"device_name": "Laptop"})
    approve = Mock(return_value={"status": "approved"})
    deny = Mock(return_value={"status": "denied"})
    monkeypatch.setattr(routes, "get_device_authorization", pending)
    monkeypatch.setattr(routes, "approve_device_authorization", approve)
    monkeypatch.setattr(routes, "deny_device_authorization", deny)
    headers = {"X-Forwarded-For": "203.0.113.6, 198.51.100.2"}
    assert test_client.get(
        "/api/user/device/pending?user_code=ABC-DEF", headers=headers
    ).get_json(force=True)["data"] == {"device_name": "Laptop"}
    pending.assert_called_once_with(app, user_code="ABC-DEF", client_ip="203.0.113.6")
    assert test_client.post(
        "/api/user/device/approve",
        json={"user_code": "ABC-DEF", "user_id": "cannot-override"},
        headers=headers,
    ).get_json(force=True)["data"] == {"status": "approved"}
    approve.assert_called_once_with(
        app, user_code="ABC-DEF", user_id="account", client_ip="203.0.113.6"
    )
    assert test_client.post(
        "/api/user/device/deny", json={"user_code": "ABC-DEF"}, headers=headers
    ).get_json(force=True)["data"] == {"status": "denied"}
    deny.assert_called_once_with(app, user_code="ABC-DEF", client_ip="203.0.113.6")


@pytest.mark.usefixtures("signed_in")
def test_profile_routes_require_course_and_forward_label_updates(
    app: object, test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    getter = Mock(return_value=UserProfileLabelDTO(profiles=[], language="en-US"))
    updater = Mock()
    monkeypatch.setattr(routes, "get_user_profile_labels", getter)
    monkeypatch.setattr(routes, "update_user_profile_with_lable", updater)
    result = test_client.get("/api/user/get_profile").get_json(force=True)
    assert result["code"] == ERROR_CODE["server.common.paramsError"]
    profiles = [{"key": "experience", "value": "beginner"}]
    updated = test_client.post(
        "/api/user/update_profile", json={"course_id": "course", "profiles": profiles}
    ).get_json(force=True)
    assert updated["data"] == {"profiles": [], "language": "en-US"}
    updater.assert_called_once_with(
        app, "account", profiles, update_all=True, course_id="course"
    )
    getter.assert_called_once_with(app, "account", "course")


@pytest.mark.usefixtures("signed_in")
def test_avatar_and_wechat_routes_validate_and_forward_uploaded_input(
    app: object, test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload = Mock(return_value="https://example.com/avatar.png")
    binding = Mock(return_value="open-id")
    monkeypatch.setattr(routes, "upload_user_avatar", upload)
    monkeypatch.setattr(routes, "update_user_open_id", binding)
    missing = test_client.post("/api/user/upload_avatar").get_json(force=True)
    assert missing["code"] == ERROR_CODE["server.common.paramsError"]
    result = test_client.post(
        "/api/user/upload_avatar",
        data={"avatar": (BytesIO(b"image-data"), "avatar.png")},
    ).get_json(force=True)
    assert result["data"] == "https://example.com/avatar.png"
    assert upload.call_args.args[:2] == (app, "account")
    assert upload.call_args.args[2].filename == "avatar.png"
    assert (
        test_client.post(
            "/api/user/update_openid", json={"wxcode": "authorization-code"}
        ).get_json(force=True)["data"]
        == "open-id"
    )
    binding.assert_called_once_with(app, "account", "authorization-code")


def test_google_oauth_routes_preserve_initiator_and_post_auth_result(
    app: object,
    test_client: object,
    signed_in: UserInfo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Mock()
    provider.begin_oauth.return_value = {
        "authorization_url": "https://accounts.google.com/authorize",
        "state": "signed-state",
    }
    provider.handle_oauth_callback.return_value = AuthResult(
        user=signed_in,
        token=UserToken(signed_in, "login-token"),
        is_new_user=True,
        metadata={
            "creator_granted_now": True,
            "login_context": "admin",
            "language": "fr-FR",
        },
    )
    monkeypatch.setattr(routes, "get_provider", Mock(return_value=provider))
    monkeypatch.setattr(
        routes, "resolve_request_origin", lambda: "https://course.example.com"
    )
    extensions = Mock()
    monkeypatch.setattr(routes, "run_post_auth_extensions", extensions)
    result = test_client.get(
        "/api/user/oauth/google?redirect_uri=https://login.example.com&login_context=admin&language=fr-FR",
        headers={"Token": "existing-token"},
    ).get_json(force=True)
    assert result["data"]["state"] == "signed-state"
    provider.begin_oauth.assert_called_once_with(
        app,
        {
            "redirect_uri": "https://login.example.com",
            "login_context": "admin",
            "language": "fr-FR",
            "origin": "https://course.example.com",
            "initiator_user_id": "account",
        },
    )
    callback = test_client.get(
        "/api/user/oauth/google/callback?state=signed-state&code=authorization-code",
        headers={"Token": "existing-token"},
    ).get_json(force=True)
    assert callback["data"]["token"] == "login-token"
    callback_request = provider.handle_oauth_callback.call_args.args[1]
    assert callback_request.current_user_id == "account"
    assert callback_request.raw_request_args == {
        "state": "signed-state",
        "code": "authorization-code",
    }
    context = extensions.call_args.args[1]
    assert context.source == "google"
    assert context.created_new_user is True
    assert context.creator_granted_now is True
    assert context.language == "fr-FR"


def test_google_return_origin_route_only_returns_validated_origin(
    app: object, test_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver = Mock(return_value="https://course.example.com")
    monkeypatch.setattr(routes, "resolve_state_return_origin", resolver)
    result = test_client.get(
        "/api/user/oauth/google/callback-origin?state=signed-state"
    ).get_json(force=True)
    assert result["data"] == {"origin": "https://course.example.com"}
    resolver.assert_called_once_with(app, "signed-state")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("zh_hant_tw", "zh-Hant-TW"), ("en_419", "en-419"), ("en__us", "en-US"), ("", "")],
)
def test_language_normalization_preserves_scripts_and_numeric_regions(
    raw: str, expected: str
) -> None:
    assert routes._normalize_runtime_language_code(raw) == expected


def test_profile_language_falls_back_to_first_available_translation(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "_translations", {"fr-FR": {}})
    with app.test_request_context(headers={"Accept-Language": ",en-US"}):
        assert (
            routes._resolve_profile_onboarding_runtime_language(
                SimpleNamespace(language="unknown"), None
            )
            == "fr-FR"
        )

"""Keep authentication secrets and identity fields out of application logs."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.user.auth.base import OAuthCallbackRequest
from flaskr.service.user.auth.providers.google import GoogleAuthProvider
from flaskr.service.user.common import update_user_info
from flaskr.service.user.user import update_user_open_id


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/user/info"),
        ("POST", "/api/user/update_info"),
        ("POST", "/api/user/require_tmp"),
        ("POST", "/api/user/captcha/verify"),
        ("POST", "/api/user/send_sms_code"),
        ("POST", "/api/user/console_send_sms_code"),
        ("POST", "/api/user/send_email_code"),
        ("POST", "/api/user/login_sms"),
        ("POST", "/api/user/login_email"),
        ("POST", "/api/user/device/authorize"),
        ("POST", "/api/user/device/token"),
        ("GET", "/api/user/device/pending"),
        ("POST", "/api/user/device/approve"),
        ("POST", "/api/user/device/deny"),
        ("GET", "/api/user/sessions"),
        ("POST", "/api/user/sessions/revoke"),
        ("POST", "/api/user/sessions/revoke-others"),
        ("GET", "/api/user/get_profile"),
        ("POST", "/api/user/update_profile"),
        ("POST", "/api/user/update_openid"),
        ("GET", "/api/user/oauth/google"),
        ("GET", "/api/user/oauth/google/callback-origin"),
        ("GET", "/api/user/oauth/google/callback"),
        ("POST", "/api/user/login_password"),
        ("POST", "/api/user/set_password"),
        ("POST", "/api/user/change_password"),
        ("POST", "/api/user/reset_password"),
    ],
)
def test_auth_routes_omit_request_and_response_bodies_from_logs(
    app: object, method: str, path: str
) -> None:
    adapter = app.url_map.bind("localhost")
    endpoint, _values = adapter.match(path, method=method)
    view = app.view_functions[endpoint]

    assert getattr(view, "_sensitive_body_max_bytes", None) == 32 * 1024


def test_wechat_exchange_logs_no_authorization_code_or_openid(
    app: object, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.user import user as user_service

    authorization_code = "wechat-code-must-not-appear"
    openid = "wechat-openid-must-not-appear"
    monkeypatch.setattr(
        user_service,
        "get_wechat_access_token",
        lambda _app, _code: {"openid": openid},
    )

    app.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO):
            assert update_user_open_id(app, "missing-user", authorization_code) == ""
    finally:
        app.logger.removeHandler(caplog.handler)

    assert "auth_event=wechat_openid_exchange_started" in caplog.text
    assert authorization_code not in caplog.text
    assert openid not in caplog.text


def test_user_info_log_records_only_field_presence(
    app: object, caplog: pytest.LogCaptureFixture
) -> None:
    name = "Private Name"
    email = "private-log@example.com"
    mobile = "15500007999"
    user = SimpleNamespace(user_id="missing-user")

    app.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO), pytest.raises(AppError):
            update_user_info(
                app,
                user,
                name=name,
                email=email,
                mobile=mobile,
                language="en-US",
            )
    finally:
        app.logger.removeHandler(caplog.handler)

    assert "auth_event=user_info_update_requested" in caplog.text
    assert name not in caplog.text
    assert email not in caplog.text
    assert mobile not in caplog.text


def test_google_callback_log_does_not_include_state(
    app: object, caplog: pytest.LogCaptureFixture
) -> None:
    state = "google-oauth-state-must-not-appear"

    app.logger.addHandler(caplog.handler)
    try:
        with (
            app.test_request_context("/api/user/oauth/google/callback"),
            caplog.at_level(logging.INFO),
            pytest.raises(AppError),
        ):
            GoogleAuthProvider().handle_oauth_callback(
                app,
                OAuthCallbackRequest(code="invalid-code", state=state),
            )
    finally:
        app.logger.removeHandler(caplog.handler)

    assert "auth_event=google_oauth_callback_received" in caplog.text
    assert state not in caplog.text

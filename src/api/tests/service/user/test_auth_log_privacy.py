"""Keep authentication secrets and identity fields out of application logs."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
import requests
from flask import Flask
from flaskr.api import wechat as wechat_api
from flaskr.api.sms import aliyun as sms_aliyun
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.user.auth.base import OAuthCallbackRequest
from flaskr.service.user.auth.providers.google import GoogleAuthProvider
from flaskr.service.user.common import update_user_info
from flaskr.service.user.repository import create_user_entity
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


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/user/captcha"),
        ("GET", "/api/user/profile-onboarding"),
        ("POST", "/api/user/profile-onboarding/session"),
        ("POST", "/api/user/profile-onboarding/session/session-id/run"),
        (
            "POST",
            "/api/user/profile-onboarding/session/session-id/assistant-answers",
        ),
        ("POST", "/api/user/profile-onboarding/complete"),
        ("POST", "/api/user/profile-onboarding/skip"),
        ("GET", "/api/user/learner-profile"),
        ("PUT", "/api/user/learner-profile"),
        ("DELETE", "/api/user/learner-profile"),
        ("POST", "/api/user/learner-profile/optimize"),
        ("POST", "/api/user/update_profile"),
        ("POST", "/api/user/upload_avatar"),
        ("POST", "/api/user/submit-feedback"),
    ],
)
def test_profile_routes_suppress_bodies_without_a_new_transport_limit(
    app: object, method: str, path: str
) -> None:
    adapter = app.url_map.bind("localhost")
    endpoint, _values = adapter.match(path, method=method)
    view = app.view_functions[endpoint]

    assert getattr(view, "_sensitive_body", False) is True
    assert getattr(view, "_sensitive_body_max_bytes", None) is None


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


def test_successful_wechat_exchange_does_not_log_provider_credentials(
    app: object, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    authorization_code = "wechat-code-must-not-appear"
    provider_credentials = {
        "access_token": "access-token-must-not-appear",
        "refresh_token": "refresh-token-must-not-appear",
        "openid": "openid-must-not-appear",
        "unionid": "unionid-must-not-appear",
    }

    class SuccessfulResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, str]:
            return provider_credentials

    monkeypatch.setattr(
        wechat_api.requests, "get", lambda *_args, **_kwargs: SuccessfulResponse()
    )

    with app.app_context():
        create_user_entity(
            user_bid="wechat-log-success-user",
            identify="wechat-log-success@example.com",
        )
        db.session.commit()

    app.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO):
            assert (
                update_user_open_id(app, "wechat-log-success-user", authorization_code)
                == provider_credentials["openid"]
            )
    finally:
        app.logger.removeHandler(caplog.handler)

    assert "auth_event=wechat_access_token_exchange_succeeded" in caplog.text
    assert authorization_code not in caplog.text
    for secret in provider_credentials.values():
        assert secret not in caplog.text


def test_wechat_transport_error_does_not_log_request_secrets(
    app: object,
    test_client: object,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization_code = "wechat-code-must-not-appear"
    app_secret = "wechat-app-secret-must-not-appear"
    monkeypatch.setitem(app.config, "WECHAT_APP_SECRET", app_secret)

    def raise_connection_error(url: str, **_kwargs: object) -> None:
        error_message = f"connection failed for {url}"
        raise requests.ConnectionError(error_message)

    monkeypatch.setattr(wechat_api.requests, "get", raise_connection_error)

    app.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR):
            response = test_client.post(
                "/api/user/require_tmp",
                json={
                    "temp_id": "wechat-log-error-user",
                    "wxcode": authorization_code,
                },
            )
    finally:
        app.logger.removeHandler(caplog.handler)

    assert response.status_code == 200
    assert response.get_json()["code"] == -1
    assert "WeChatAPIError: WeChat OAuth request failed" in caplog.text
    assert authorization_code not in caplog.text
    assert app_secret not in caplog.text


def test_aliyun_recipient_rejection_does_not_log_mobile_or_provider_details(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    mobile = "13800000000"
    provider_message = "daily limit for 13800000000"
    request_id = "request-id-must-not-appear"

    class FakeClient:
        def __init__(self, _config: object) -> None:
            pass

        def send_sms_with_options(self, request: object, runtime: object) -> object:
            del request, runtime
            return SimpleNamespace(
                body=SimpleNamespace(
                    code="isv.BUSINESS_LIMIT_CONTROL",
                    message=provider_message,
                    request_id=request_id,
                    biz_id="biz-id-must-not-appear",
                )
            )

    monkeypatch.setattr(sms_aliyun, "Dysmsapi20170525Client", FakeClient)
    sms_app = Flask("auth-log-privacy-sms")
    sms_app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="key",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
    )

    sms_app.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING):
            result = sms_aliyun.send_sms_ali(
                sms_app,
                mobile,
                template_code="TPL-VERIFY-001",
                template_params={"code": "1234"},
            )
    finally:
        sms_app.logger.removeHandler(caplog.handler)

    assert result is None
    assert "sms_event=aliyun_send_rejected" in caplog.text
    assert "isv.BUSINESS_LIMIT_CONTROL" in caplog.text
    assert mobile not in caplog.text
    assert provider_message not in caplog.text
    assert request_id not in caplog.text


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


def test_temp_user_log_does_not_include_client_controlled_source(
    app: object,
    test_client: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = "private-source\nforged-log-entry"
    app.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO):
            response = test_client.post(
                "/api/user/require_tmp",
                json={"source": source},
            )
    finally:
        app.logger.removeHandler(caplog.handler)

    assert response.status_code == 200
    assert "auth_event=temp_user_requested" in caplog.text
    assert "has_source=True" in caplog.text
    assert source not in caplog.text
    assert "forged-log-entry" not in caplog.text

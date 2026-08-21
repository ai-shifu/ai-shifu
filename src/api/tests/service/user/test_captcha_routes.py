"""Verify captcha HTTP route behavior."""

import base64
import json
from io import BytesIO

from flasgger.utils import parse_docstring
from PIL import Image
from werkzeug.test import TestResponse


def _post_json(client, path: str, payload: dict) -> tuple[TestResponse, object]:
    resp = client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
    )
    return resp, resp.get_json(force=True)


def _get_captcha(client, app) -> object:
    app.config["ENV"] = "development"
    app.config["CAPTCHA_CODE_OVERRIDE"] = "0000"
    response = client.get("/api/user/captcha")
    body = response.get_json(force=True)
    assert response.status_code == 200
    assert body["code"] == 0
    return body["data"]


def _get_ticket(client, app) -> object:
    captcha = _get_captcha(client, app)
    response, body = _post_json(
        client,
        "/api/user/captcha/verify",
        {
            "captcha_id": captcha["captcha_id"],
            "captcha_code": "0000",
        },
    )
    assert response.status_code == 200
    assert body["code"] == 0
    return body["data"]["captcha_ticket"]


def test_get_captcha_returns_image_payload(test_client, app) -> None:
    captcha = _get_captcha(test_client, app)

    assert captcha["captcha_id"]
    assert captcha["image"].startswith("data:image/png;base64,")
    with Image.open(
        BytesIO(base64.b64decode(captcha["image"].split(",", maxsplit=1)[1]))
    ) as image:
        assert image.size == (160, 48)
    assert captcha["expires_in"] == app.config["CAPTCHA_EXPIRE_TIME"]


def test_captcha_verify_rejects_wrong_code(test_client, app) -> None:
    captcha = _get_captcha(test_client, app)

    response, body = _post_json(
        test_client,
        "/api/user/captcha/verify",
        {
            "captcha_id": captcha["captcha_id"],
            "captcha_code": "9999",
        },
    )

    assert response.status_code == 200
    assert body["code"] == 1009


def test_captcha_verify_localizes_wrong_code_message(test_client, app) -> None:
    captcha = _get_captcha(test_client, app)

    response = test_client.post(
        "/api/user/captcha/verify",
        data=json.dumps(
            {
                "captcha_id": captcha["captcha_id"],
                "captcha_code": "9999",
                "language": "zh-CN",
            }
        ),
        content_type="application/json",
    )
    body = response.get_json(force=True)

    assert response.status_code == 200
    assert body["code"] == 1009
    assert body["message"] == "图形验证码错误"


def test_captcha_verify_deletes_after_attempt_limit(test_client, app) -> None:
    original_attempts = app.config.get("CAPTCHA_MAX_VERIFY_ATTEMPTS")
    app.config["CAPTCHA_MAX_VERIFY_ATTEMPTS"] = 1
    try:
        captcha = _get_captcha(test_client, app)

        response, body = _post_json(
            test_client,
            "/api/user/captcha/verify",
            {
                "captcha_id": captcha["captcha_id"],
                "captcha_code": "9999",
            },
        )
        assert response.status_code == 200
        assert body["code"] == 1009

        response, body = _post_json(
            test_client,
            "/api/user/captcha/verify",
            {
                "captcha_id": captcha["captcha_id"],
                "captcha_code": "0000",
            },
        )
        assert response.status_code == 200
        assert body["code"] == 1010
    finally:
        app.config["CAPTCHA_MAX_VERIFY_ATTEMPTS"] = original_attempts


def test_send_sms_code_requires_captcha_ticket(test_client, app) -> None:
    _ = app
    response, body = _post_json(
        test_client,
        "/api/user/send_sms_code",
        {"mobile": "13800138000"},
    )

    assert response.status_code == 200
    assert body["code"] == 1009


def test_send_sms_code_swagger_parameters_stay_valid_yaml(app) -> None:
    view = app.view_functions["send_sms_code_api"]

    _summary, _description, specification = parse_docstring(
        view,
        process_doc=lambda text: text,
    )

    assert specification["parameters"][0]["in"] == "body"
    assert specification["parameters"][0]["required"] is True
    assert specification["parameters"][0]["schema"]["required"] == [
        "mobile",
        "captcha_ticket",
    ]


def test_send_sms_code_localizes_missing_captcha_ticket_message(
    test_client, app
) -> None:
    _ = app
    response, body = _post_json(
        test_client,
        "/api/user/send_sms_code",
        {"mobile": "13800138000", "language": "zh-CN"},
    )

    assert response.status_code == 200
    assert body["code"] == 1009
    assert body["message"] == "图形验证码错误"


def test_send_sms_code_consumes_ticket_once(test_client, app, monkeypatch) -> None:
    import flaskr.service.user.utils as user_utils

    monkeypatch.setattr(
        user_utils,
        "send_sms_code_ali",
        lambda _app, _mobile, _code: True,
    )
    ticket = _get_ticket(test_client, app)

    response, body = _post_json(
        test_client,
        "/api/user/send_sms_code",
        {
            "mobile": "13800138000",
            "captcha_ticket": ticket,
        },
    )
    assert response.status_code == 200
    assert body["code"] == 0
    assert body["data"]["expire_in"] == app.config["PHONE_CODE_EXPIRE_TIME"]

    response, body = _post_json(
        test_client,
        "/api/user/send_sms_code",
        {
            "mobile": "13800138001",
            "captcha_ticket": ticket,
        },
    )
    assert response.status_code == 200
    assert body["code"] == 1010


def test_console_send_sms_code_does_not_require_captcha_ticket(
    test_client, monkeypatch
) -> None:
    import flaskr.service.user.utils as user_utils

    monkeypatch.setattr(
        user_utils,
        "send_sms_code_ali",
        lambda _app, _mobile, _code: True,
    )

    response, body = _post_json(
        test_client,
        "/api/user/console_send_sms_code",
        {"mobile": "13800138002"},
    )

    assert response.status_code == 200
    assert body["code"] == 0
    assert body["data"]["expire_in"] > 0


def test_console_send_sms_code_normalizes_cn_prefix(
    test_client, app, monkeypatch
) -> None:
    import flaskr.service.user.utils as user_utils
    from flaskr.service.user.models import UserVerifyCode

    captured = []
    monkeypatch.setattr(
        user_utils,
        "send_sms_code_ali",
        lambda _app, _mobile, _code: captured.append(_mobile) or True,
    )

    response, body = _post_json(
        test_client,
        "/api/user/console_send_sms_code",
        {"mobile": "+8613800138003"},
    )

    assert response.status_code == 200
    assert body["code"] == 0
    assert captured == ["13800138003"]

    with app.app_context():
        record = (
            UserVerifyCode.query.filter_by(phone="13800138003")
            .order_by(UserVerifyCode.id.desc())
            .first()
        )
        assert record is not None

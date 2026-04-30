import json


def _post_json(client, path: str, payload: dict):
    resp = client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
    )
    return resp, resp.get_json(force=True)


def _get_captcha(client, app):
    app.config["ENV"] = "development"
    app.config["CAPTCHA_CODE_OVERRIDE"] = "0000"
    response = client.get("/api/user/captcha")
    body = response.get_json(force=True)
    assert response.status_code == 200
    assert body["code"] == 0
    return body["data"]


def _get_ticket(client, app):
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


def test_get_captcha_returns_image_payload(test_client, app):
    captcha = _get_captcha(test_client, app)

    assert captcha["captcha_id"]
    assert captcha["image"].startswith("data:image/png;base64,")
    assert captcha["expires_in"] == app.config["CAPTCHA_EXPIRE_TIME"]


def test_captcha_verify_rejects_wrong_code(test_client, app):
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


def test_captcha_verify_deletes_after_attempt_limit(test_client, app):
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


def test_send_sms_code_requires_captcha_ticket(test_client, app):
    response, body = _post_json(
        test_client,
        "/api/user/send_sms_code",
        {"mobile": "13800138000"},
    )

    assert response.status_code == 200
    assert body["code"] == 1009


def test_send_sms_code_consumes_ticket_once(test_client, app, monkeypatch):
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

from types import SimpleNamespace


def test_send_sms_code_without_check_sets_cache(app, monkeypatch, mock_redis_client):
    from flaskr.service.user import common as user_common

    app.config["REDIS_KEY_PREFIX_PHONE"] = "phone:"
    app.config["REDIS_KEY_PREFIX_PHONE_CODE"] = "phone_code:"
    app.config["PHONE_CODE_EXPIRE_TIME"] = 60
    app.config["PHONE_EXPIRE_TIME"] = 1800

    monkeypatch.setattr(user_common, "redis", mock_redis_client, raising=False)

    sent = {}

    def fake_send_sms_code_ali(_app, phone, code):
        sent["phone"] = phone
        sent["code"] = code

    monkeypatch.setattr(user_common, "send_sms_code_ali", fake_send_sms_code_ali)

    user = SimpleNamespace(user_id="user-1")
    with app.app_context():
        result = user_common.send_sms_code_without_check(app, user, phone="13800000000")

    assert result["phone"] == "13800000000"
    cached_phone = mock_redis_client.get("phone:user-1")
    cached_code = mock_redis_client.get("phone_code:13800000000")
    assert cached_phone == b"13800000000"
    assert cached_code is not None
    assert sent["phone"] == "13800000000"
    assert sent["code"] == cached_code.decode("utf-8")

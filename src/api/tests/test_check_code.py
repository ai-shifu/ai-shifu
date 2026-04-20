from types import SimpleNamespace


def test_verify_sms_code_without_phone_uses_cached_phone(
    app, monkeypatch, mock_redis_client
):
    from flaskr.service.user import common as user_common

    app.config["REDIS_KEY_PREFIX_PHONE"] = "phone:"
    mock_redis_client.set("phone:user-1", "13800000000")

    def fake_verify_sms_code(_app, user_id, phone, checkcode, course_id=None):
        assert user_id == "user-1"
        assert phone == "13800000000"
        assert checkcode == "0615"
        return SimpleNamespace(token="token")

    monkeypatch.setattr(user_common, "redis", mock_redis_client, raising=False)
    monkeypatch.setattr(user_common, "verify_sms_code", fake_verify_sms_code)

    user = SimpleNamespace(user_id="user-1")
    token = user_common.verify_sms_code_without_phone(app, user, "0615")
    assert token.token == "token"

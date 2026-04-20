from types import SimpleNamespace

from flask import Flask


def test_send_sms_code_ali_builds_request(monkeypatch):
    from flaskr.api.sms import aliyun as sms_aliyun

    captured = {}

    class FakeClient:
        def __init__(self, config):
            captured["config"] = config

        def send_sms_with_options(self, request, runtime):
            captured["request"] = request
            captured["runtime"] = runtime
            return SimpleNamespace(ok=True)

    monkeypatch.setattr(sms_aliyun, "Dysmsapi20170525Client", FakeClient)

    app = Flask("contract-sms")
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="key",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
        ALIBABA_CLOUD_SMS_TEMPLATE_CODE="TPL-001",
    )

    result = sms_aliyun.send_sms_code_ali(app, "13800000000", "123456")

    assert result is not None
    assert result.ok is True

    request = captured["request"]
    assert request.sign_name == "TestSign"
    assert request.template_code == "TPL-001"
    assert request.phone_numbers == "13800000000"
    assert request.template_param == '{"code":"123456"}'
    assert captured["config"].endpoint == "dysmsapi.aliyuncs.com"


def test_send_sms_code_ali_returns_none_without_keys(monkeypatch):
    from flaskr.api.sms import aliyun as sms_aliyun

    def fake_client(_config):
        raise AssertionError("client should not be created")

    monkeypatch.setattr(sms_aliyun, "Dysmsapi20170525Client", fake_client)

    app = Flask("contract-sms-missing")
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
        ALIBABA_CLOUD_SMS_TEMPLATE_CODE="TPL-001",
    )

    result = sms_aliyun.send_sms_code_ali(app, "13800000000", "123456")

    assert result is None


def test_send_sms_code_ali_handles_client_error(monkeypatch):
    from flaskr.api.sms import aliyun as sms_aliyun

    class DummyError(Exception):
        def __init__(self):
            super().__init__("boom")
            self.message = "boom"
            self.data = {"Recommend": "retry"}

    captured = {}

    class FakeClient:
        def __init__(self, config):
            captured["config"] = config

        def send_sms_with_options(self, request, runtime):
            raise DummyError()

    def fake_assert(message):
        captured["assert_message"] = message

    monkeypatch.setattr(sms_aliyun, "Dysmsapi20170525Client", FakeClient)
    monkeypatch.setattr(sms_aliyun.UtilClient, "assert_as_string", fake_assert)

    app = Flask("contract-sms-error")
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="key",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
        ALIBABA_CLOUD_SMS_TEMPLATE_CODE="TPL-001",
    )

    result = sms_aliyun.send_sms_code_ali(app, "13800000000", "123456")

    assert result is None
    assert captured["assert_message"] == "boom"

import logging
from types import SimpleNamespace

import pytest
from flask import Flask


def test_send_sms_ali_builds_request_for_generic_template(monkeypatch):
    from flaskr.api.sms import aliyun as sms_aliyun

    captured = {}

    class FakeClient:
        def __init__(self, config):
            captured["config"] = config

        def send_sms_with_options(self, request, runtime):
            captured["request"] = request
            captured["runtime"] = runtime
            return SimpleNamespace(body=SimpleNamespace(code="OK"))

    monkeypatch.setattr(sms_aliyun, "Dysmsapi20170525Client", FakeClient)

    app = Flask("contract-sms-generic")
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="key",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
    )

    result = sms_aliyun.send_sms_ali(
        app,
        "13800000000",
        template_code="TPL-SUB-001",
        template_params={"product": "轻量版", "date": "2026-05-01 00:00 UTC"},
    )

    assert result is not None
    assert result.body.code == "OK"

    request = captured["request"]
    assert request.sign_name == "TestSign"
    assert request.template_code == "TPL-SUB-001"
    assert request.phone_numbers == "13800000000"
    assert (
        request.template_param == '{"product":"轻量版","date":"2026-05-01 00:00 UTC"}'
    )
    assert captured["config"].endpoint == "dysmsapi.aliyuncs.com"


def test_send_sms_code_ali_builds_request(monkeypatch):
    from flaskr.api.sms import aliyun as sms_aliyun

    captured = {}

    class FakeClient:
        def __init__(self, config):
            captured["config"] = config

        def send_sms_with_options(self, request, runtime):
            captured["request"] = request
            captured["runtime"] = runtime
            return SimpleNamespace(body=SimpleNamespace(code="OK"))

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
    assert result.body.code == "OK"

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
            raise DummyError

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


def test_send_sms_ali_returns_none_when_provider_response_is_not_ok(monkeypatch):
    from flaskr.api.sms import aliyun as sms_aliyun

    class FakeClient:
        def __init__(self, _config):
            pass

        def send_sms_with_options(self, request, runtime):
            del request, runtime
            return SimpleNamespace(
                body=SimpleNamespace(
                    code="isv.TEMPLATE_PARAMS_ILLEGAL",
                    message="bad template params",
                    request_id="req-1",
                    biz_id=None,
                )
            )

    monkeypatch.setattr(sms_aliyun, "Dysmsapi20170525Client", FakeClient)

    app = Flask("contract-sms-provider-failure")
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="key",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
    )

    result = sms_aliyun.send_sms_ali(
        app,
        "13800000000",
        template_code="TPL-SUB-001",
        template_params={"product": "轻量版", "date": "2026-05-01 00:00:00"},
    )

    assert result is None


@pytest.mark.parametrize(
    "provider_message",
    [
        "触发号码天级流控Permits:40",
        "触发小时级流控Permits:5",
    ],
)
def test_send_sms_ali_logs_recipient_throttle_as_warning(
    monkeypatch, caplog, provider_message
):
    from flaskr.api.sms import aliyun as sms_aliyun

    class FakeClient:
        def __init__(self, _config):
            pass

        def send_sms_with_options(self, request, runtime):
            del request, runtime
            return SimpleNamespace(
                body=SimpleNamespace(
                    code="isv.BUSINESS_LIMIT_CONTROL",
                    message=provider_message,
                    request_id="req-throttle-1",
                    biz_id=None,
                )
            )

    monkeypatch.setattr(sms_aliyun, "Dysmsapi20170525Client", FakeClient)

    app = Flask("contract-sms-recipient-throttle")
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="key",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
    )

    with caplog.at_level(logging.WARNING):
        result = sms_aliyun.send_sms_ali(
            app,
            "13800000000",
            template_code="TPL-VERIFY-001",
            template_params={"code": "1234"},
        )

    assert result is None
    assert any(
        record.levelno == logging.WARNING
        and "isv.BUSINESS_LIMIT_CONTROL" in record.getMessage()
        and provider_message in record.getMessage()
        for record in caplog.records
    )
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_send_sms_ali_logs_illegal_recipient_number_as_warning(monkeypatch, caplog):
    from flaskr.api.sms import aliyun as sms_aliyun

    class FakeClient:
        def __init__(self, _config):
            pass

        def send_sms_with_options(self, request, runtime):
            del request, runtime
            return SimpleNamespace(
                body=SimpleNamespace(
                    code="isv.MOBILE_NUMBER_ILLEGAL",
                    message="invalid mobile number format",
                    request_id="req-illegal-number-1",
                    biz_id=None,
                )
            )

    monkeypatch.setattr(sms_aliyun, "Dysmsapi20170525Client", FakeClient)

    app = Flask("contract-sms-illegal-number")
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="key",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
    )

    with caplog.at_level(logging.WARNING):
        result = sms_aliyun.send_sms_ali(
            app,
            "14085986122",
            template_code="TPL-VERIFY-001",
            template_params={"code": "1234"},
        )

    assert result is None
    assert any(
        record.levelno == logging.WARNING
        and "isv.MOBILE_NUMBER_ILLEGAL" in record.getMessage()
        for record in caplog.records
    )
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]

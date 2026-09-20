"""Verify SMS template requests validate configuration and provider failures offline."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.api.sms import aliyun


@pytest.fixture
def sms_provider(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    app = Flask(__name__)
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="test-key",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="test-secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="Test sign",
    )
    response = SimpleNamespace(body=SimpleNamespace(code="OK"))
    client = Mock()
    client.send_sms_with_options.return_value = response
    client.get_sms_template_with_options.return_value = response
    client.query_sms_template_list_with_options.return_value = response
    factory = Mock(return_value=client)
    monkeypatch.setattr(aliyun, "Dysmsapi20170525Client", factory)
    return SimpleNamespace(app=app, client=client, factory=factory, response=response)


@pytest.mark.parametrize("operation", ["send", "get", "list"])
@pytest.mark.parametrize("missing", ["ACCESS_KEY_ID", "ACCESS_KEY_SECRET"])
def test_missing_credentials_prevent_sms_and_template_provider_requests(
    sms_provider: SimpleNamespace, operation: str, missing: str
) -> None:
    scope = sms_provider
    scope.app.config[f"ALIBABA_CLOUD_SMS_{missing}"] = ""
    if operation == "send":
        result = aliyun.send_sms_ali(
            scope.app, "13000000000", template_code="template", template_params={}
        )
    elif operation == "get":
        result = aliyun.get_sms_template_ali(scope.app, template_code="template")
    else:
        result = aliyun.query_sms_template_list_ali(scope.app)
    assert result is None
    scope.factory.assert_not_called()


@pytest.mark.parametrize("missing", ["send-template", "get-template", "sign"])
def test_empty_template_or_sign_is_rejected_before_constructing_client(
    sms_provider: SimpleNamespace, missing: str
) -> None:
    scope = sms_provider
    if missing == "get-template":
        result = aliyun.get_sms_template_ali(scope.app, template_code=" ")
    else:
        if missing == "sign":
            scope.app.config["ALIBABA_CLOUD_SMS_SIGN_NAME"] = " "
        result = aliyun.send_sms_ali(
            scope.app,
            "13000000000",
            template_code=" " if missing == "send-template" else "template",
            template_params={},
        )
    assert result is None
    scope.factory.assert_not_called()


def test_template_lookup_passes_normalized_id_and_configured_credentials(
    sms_provider: SimpleNamespace,
) -> None:
    scope = sms_provider
    assert (
        aliyun.get_sms_template_ali(scope.app, template_code="  SMS_TEST  ")
        is scope.response
    )
    request, _runtime = scope.client.get_sms_template_with_options.call_args.args
    assert request.template_code == "SMS_TEST"
    config = scope.factory.call_args.args[0]
    assert config.access_key_id == "test-key"
    assert config.access_key_secret == "test-secret"
    assert config.endpoint == "dysmsapi.aliyuncs.com"


@pytest.mark.parametrize(
    ("index", "size", "expected"),
    [
        ("bad", "bad", (1, 50)),
        ([1], {"invalid": 1}, (1, 50)),
        (-2, -3, (1, 1)),
        ("4", "70", (4, 50)),
    ],
)
def test_template_pagination_normalizes_untrusted_values_and_provider_bounds(
    sms_provider: SimpleNamespace, index: object, size: object, expected: tuple
) -> None:
    scope = sms_provider
    assert (
        aliyun.query_sms_template_list_ali(scope.app, page_index=index, page_size=size)
        is scope.response
    )
    request, _runtime = scope.client.query_sms_template_list_with_options.call_args.args
    assert (request.page_index, request.page_size) == expected


@pytest.mark.parametrize("operation", ["get", "list"])
def test_template_provider_failure_returns_no_result_and_logs_provider_diagnostics(
    sms_provider: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    scope = sms_provider
    error = RuntimeError("template service unavailable")
    error.data = {"Recommend": "retry request"}
    log = Mock()
    monkeypatch.setattr(scope.app.logger, "error", log)
    if operation == "get":
        scope.client.get_sms_template_with_options.side_effect = error
        result = aliyun.get_sms_template_ali(scope.app, template_code="template")
    else:
        scope.client.query_sms_template_list_with_options.side_effect = error
        result = aliyun.query_sms_template_list_ali(scope.app)
    assert result is None
    assert [call.args[0] for call in log.call_args_list] == [
        "template service unavailable",
        "retry request",
    ]


def test_send_sms_serializes_template_values_and_honors_explicit_sign(
    sms_provider: SimpleNamespace,
) -> None:
    scope = sms_provider
    result = aliyun.send_sms_ali(
        scope.app,
        "13000000000",
        template_code=" template ",
        template_params={"course": "示例", "code": "123456"},
        sign_name=" override ",
    )
    assert result is scope.response
    request, _runtime = scope.client.send_sms_with_options.call_args.args
    assert request.phone_numbers == "13000000000"
    assert request.sign_name == "override"
    assert request.template_code == "template"
    assert json.loads(request.template_param) == {"course": "示例", "code": "123456"}
    assert "\\u" not in request.template_param

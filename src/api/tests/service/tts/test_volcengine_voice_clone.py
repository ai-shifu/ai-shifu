"""Verify volcengine voice clone behavior."""

from __future__ import annotations

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.tts import volcengine_voice_clone
from flaskr.service.tts.volcengine_voice_clone import (
    VOLCENGINE_ICL_RESOURCE_ID,
    VOLCENGINE_MEGA_TTS_STATUS_URL,
    is_valid_volcengine_custom_voice_id,
    query_volcengine_voice_status,
    verify_volcengine_voice_id,
)

_TEST_CONFIG = {
    "VOLCENGINE_TTS_APP_KEY": "test-appid",
    "VOLCENGINE_TTS_ACCESS_KEY": "test-token",
}


def _patch_config(monkeypatch, config=None):
    values = _TEST_CONFIG if config is None else config
    monkeypatch.setattr(
        volcengine_voice_clone,
        "get_config",
        lambda key: values.get(key, ""),
    )


class _FakeResponse:
    def __init__(self, payload, status_code=200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("S_xxxxxxxxxx", True),
        ("S_xxxxxxxxx", True),
        ("S_xxxx", True),
        ("S_" + "Ab9" + "-z_7", True),  # mixed allowed character classes
        ("  S_xxxxxxxxxx  ", True),
        ("S_xx", False),  # too short
        ("AiShifu_xxxxxxxxxx", False),  # MiniMax-shaped id
        ("s_xxxxxxxxxx", False),  # lowercase prefix
        ("S_xxxxx xxxxx", False),  # whitespace inside
        ("", False),
        (None, False),
    ],
)
def test_is_valid_volcengine_custom_voice_id(value, expected) -> None:
    assert is_valid_volcengine_custom_voice_id(value) is expected


def test_query_status_sends_expected_request(monkeypatch) -> None:
    _patch_config(monkeypatch)

    def fake_post(url, headers, json, timeout):
        assert url == VOLCENGINE_MEGA_TTS_STATUS_URL
        assert headers["Authorization"] == "Bearer;test-token"
        assert headers["Resource-Id"] == VOLCENGINE_ICL_RESOURCE_ID
        assert json == {"appid": "test-appid", "speaker_id": "S_xxxxxxxxxx"}
        assert timeout == (10, 60)
        return _FakeResponse(
            {"BaseResp": {"StatusCode": 0, "StatusMessage": ""}, "status": 2}
        )

    monkeypatch.setattr(volcengine_voice_clone.requests, "post", fake_post)
    assert query_volcengine_voice_status("S_xxxxxxxxxx") == 2


def test_query_status_raises_on_base_resp_error(monkeypatch) -> None:
    _patch_config(monkeypatch)
    monkeypatch.setattr(
        volcengine_voice_clone.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            {"BaseResp": {"StatusCode": 1001, "StatusMessage": "bad request"}}
        ),
    )
    with pytest.raises(AppError):
        query_volcengine_voice_status("S_xxxxxxxxxx")


def test_query_status_raises_without_credentials(monkeypatch) -> None:
    _patch_config(monkeypatch, config={})
    with pytest.raises(AppError):
        query_volcengine_voice_status("S_xxxxxxxxxx")


def test_query_status_converts_transport_error_to_param_error(monkeypatch) -> None:
    """Provider unreachable / timeout must fail through the controlled parameter-error path, not bubble a raw RequestException into a 500."""
    import requests as requests_lib

    _patch_config(monkeypatch)

    def _raise_transport_error(*args, **kwargs):
        _ = (args, kwargs)
        message = "connect timeout"
        raise requests_lib.exceptions.ConnectTimeout(message)

    monkeypatch.setattr(volcengine_voice_clone.requests, "post", _raise_transport_error)
    with pytest.raises(AppError):
        query_volcengine_voice_status("S_xxxxxxxxxx")


def test_query_status_converts_invalid_json_to_param_error(monkeypatch) -> None:
    _patch_config(monkeypatch)

    class _BadJsonResponse:
        status_code = 200
        text = "<html>gateway error</html>"

        def json(self):
            message = "no json"
            raise ValueError(message)

    monkeypatch.setattr(
        volcengine_voice_clone.requests,
        "post",
        lambda *_args, **_kwargs: _BadJsonResponse(),
    )
    with pytest.raises(AppError):
        query_volcengine_voice_status("S_xxxxxxxxxx")


def test_query_status_converts_http_error_to_param_error(monkeypatch) -> None:
    """Volcengine answers 4xx (with a JSON message) for unknown speakers or missing grants; that must surface as a parameter error, not an HTTPError."""
    _patch_config(monkeypatch)
    monkeypatch.setattr(
        volcengine_voice_clone.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            {"message": "parameter license not found for appid"}, status_code=403
        ),
    )
    with pytest.raises(AppError):
        query_volcengine_voice_status("S_xxxxxxxxxxx")


@pytest.mark.parametrize("status", [2, 4])
def test_verify_accepts_success_and_active(monkeypatch, status) -> None:
    _patch_config(monkeypatch)
    monkeypatch.setattr(
        volcengine_voice_clone.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            {"BaseResp": {"StatusCode": 0}, "status": status}
        ),
    )
    verify_volcengine_voice_id("S_xxxxxxxxxx")


@pytest.mark.parametrize("status", [0, 1, 3])
def test_verify_rejects_not_ready_statuses(monkeypatch, status) -> None:
    _patch_config(monkeypatch)
    monkeypatch.setattr(
        volcengine_voice_clone.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse(
            {"BaseResp": {"StatusCode": 0}, "status": status}
        ),
    )
    with pytest.raises(AppError):
        verify_volcengine_voice_id("S_xxxxxxxxxx")


def test_icl_resource_is_not_a_selectable_model() -> None:
    """The clone resource id must stay out of the model dropdown; it is inferred from the S_ speaker id inside the provider instead."""
    from flaskr.api.tts.volcengine_provider import VOLCENGINE_MODELS

    assert VOLCENGINE_ICL_RESOURCE_ID not in {
        model.get("value") for model in VOLCENGINE_MODELS
    }


def test_provider_infers_icl_resource_for_cloned_speakers() -> None:
    from flaskr.api.tts.volcengine_provider import VolcengineTTSProvider

    provider = VolcengineTTSProvider()
    assert (
        provider._infer_resource_id_for_voice("S_xxxxxxxxxx")
        == VOLCENGINE_ICL_RESOURCE_ID
    )
    # Static voices keep their declared resource id.
    assert (
        provider._infer_resource_id_for_voice("zh_female_vv_uranus_bigtts")
        == "seed-tts-2.0"
    )
    # Unknown non-speaker ids leave the caller's model untouched.
    assert provider._infer_resource_id_for_voice("AiShifu_xxxxxxxxxx") == ""


def test_clone_provider_specs_dispatch_by_provider() -> None:
    from flaskr.service.tts.cloned_voice_registry import (
        get_clone_provider_spec,
        supports_cloned_voices,
    )

    minimax_spec = get_clone_provider_spec("minimax")
    volcengine_spec = get_clone_provider_spec(" Volcengine ")
    assert minimax_spec is not None
    assert volcengine_spec is not None
    assert minimax_spec.validation_requires_ready_row is False
    assert volcengine_spec.validation_requires_ready_row is True

    # Same S_ id: accepted by the volcengine spec, and (by design) also by the
    # MiniMax format rule — which is exactly why dispatch is by provider name.
    assert volcengine_spec.is_valid_custom_voice_id("S_xxxxxxxxxx") is True
    assert minimax_spec.is_valid_custom_voice_id("S_xxxxxxxxxx") is True
    assert volcengine_spec.is_valid_custom_voice_id("AiShifu_xxxxxxxxxx") is False

    assert supports_cloned_voices("volcengine") is True
    assert supports_cloned_voices("volcengine_http") is False
    assert supports_cloned_voices("baidu") is False

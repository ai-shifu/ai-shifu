"""Verify volcengine voice clone behavior."""

from __future__ import annotations

from uuid import UUID

import pytest
from flaskr.api.tts import volcengine_provider
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.tts import volcengine_voice_clone
from flaskr.service.tts.volcengine_voice_clone import (
    VOLCENGINE_VOICE_STATUS_URL,
    is_valid_volcengine_custom_voice_id,
    query_volcengine_voice_status,
    verify_volcengine_voice_id,
)


def _patch_config(monkeypatch: object, api_key: str = " speech-api-key ") -> None:
    monkeypatch.setattr(
        volcengine_provider,
        "get_config",
        lambda key: api_key if key == "VOLCENGINE_TTS_API_KEY" else "",
    )


class _FakeResponse:
    def __init__(self, payload: object, status_code: object = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> object:
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
def test_is_valid_volcengine_custom_voice_id(value: object, expected: object) -> None:
    assert is_valid_volcengine_custom_voice_id(value) is expected


@pytest.mark.parametrize("status", [2, 4])
def test_verify_voice_with_api_key(monkeypatch: object, status: int) -> None:
    _patch_config(monkeypatch)

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, str],
        timeout: tuple[int, int],
        allow_redirects: bool,
    ) -> _FakeResponse:
        request_id = headers["X-Api-Request-Id"]
        assert UUID(request_id).version == 4
        assert url == VOLCENGINE_VOICE_STATUS_URL
        assert headers == {
            "Content-Type": "application/json",
            "X-Api-Key": "speech-api-key",
            "X-Api-Request-Id": request_id,
        }
        assert json == {"speaker_id": "S_xxxxxxxxxx"}
        assert timeout == (10, 60)
        assert allow_redirects is False
        return _FakeResponse({"status": status})

    monkeypatch.setattr(volcengine_voice_clone.requests, "post", fake_post)
    verify_volcengine_voice_id(" S_xxxxxxxxxx ")


@pytest.mark.parametrize(
    ("http_status", "provider_code"), [(200, 45000000), (302, 0), (403, 0)]
)
def test_query_status_converts_provider_errors_to_param_error(
    monkeypatch: object, http_status: int, provider_code: int
) -> None:
    _patch_config(monkeypatch)
    requested_urls: list[str] = []

    def fake_post(url: str, **_kwargs: object) -> _FakeResponse:
        requested_urls.append(url)
        return _FakeResponse(
            {"code": provider_code, "message": "speaker unavailable", "status": 2},
            status_code=http_status,
        )

    monkeypatch.setattr(volcengine_voice_clone.requests, "post", fake_post)
    with pytest.raises(AppError) as error:
        query_volcengine_voice_status("S_xxxxxxxxxx")

    assert error.value.code == ERROR_CODE["server.common.paramsError"]
    assert requested_urls == [VOLCENGINE_VOICE_STATUS_URL]


def test_query_status_raises_without_api_key(monkeypatch: object) -> None:
    _patch_config(monkeypatch, api_key=" ")
    monkeypatch.setattr(
        volcengine_voice_clone.requests,
        "post",
        lambda *_args, **_kwargs: pytest.fail("An API key is required before querying"),
    )
    with pytest.raises(AppError) as error:
        query_volcengine_voice_status("S_xxxxxxxxxx")

    assert error.value.code == ERROR_CODE["server.common.paramsError"]


def test_query_status_converts_transport_error_to_param_error(
    monkeypatch: object,
) -> None:
    """Provider unreachable / timeout must fail through the controlled parameter-error path, not bubble a raw RequestException into a 500."""
    import requests as requests_lib

    _patch_config(monkeypatch)

    def _raise_transport_error(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        message = "connect timeout"
        raise requests_lib.exceptions.ConnectTimeout(message)

    monkeypatch.setattr(volcengine_voice_clone.requests, "post", _raise_transport_error)
    with pytest.raises(AppError):
        query_volcengine_voice_status("S_xxxxxxxxxx")


def test_query_status_converts_invalid_json_to_param_error(monkeypatch: object) -> None:
    _patch_config(monkeypatch)

    class _BadJsonResponse:
        status_code = 200
        text = "<html>gateway error</html>"

        def json(self) -> None:
            message = "no json"
            raise ValueError(message)

    monkeypatch.setattr(
        volcengine_voice_clone.requests,
        "post",
        lambda *_args, **_kwargs: _BadJsonResponse(),
    )
    with pytest.raises(AppError):
        query_volcengine_voice_status("S_xxxxxxxxxx")


@pytest.mark.parametrize("status", [0, 1, 3])
def test_verify_rejects_not_ready_statuses(monkeypatch: object, status: object) -> None:
    _patch_config(monkeypatch)
    monkeypatch.setattr(
        volcengine_voice_clone.requests,
        "post",
        lambda *_args, **_kwargs: _FakeResponse({"status": status}),
    )
    with pytest.raises(AppError):
        verify_volcengine_voice_id("S_xxxxxxxxxx")


def test_icl_resource_is_not_a_selectable_model() -> None:
    """The clone resource id must stay out of the model dropdown; it is inferred from the S_ speaker id inside the provider instead."""
    from flaskr.api.tts.volcengine_provider import VOLCENGINE_MODELS

    assert volcengine_provider.VOLCENGINE_ICL_RESOURCE_ID not in {
        model.get("value") for model in VOLCENGINE_MODELS
    }


def test_provider_infers_icl_resource_for_cloned_speakers() -> None:
    from flaskr.api.tts.volcengine_provider import VolcengineTTSProvider

    provider = VolcengineTTSProvider()
    assert (
        provider._infer_resource_id_for_voice("S_xxxxxxxxxx")
        == volcengine_provider.VOLCENGINE_ICL_RESOURCE_ID
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

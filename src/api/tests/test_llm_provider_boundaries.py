"""Verify LLM discovery degradation, numbered model isolation and gateway limits."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.api import llm
from flaskr.api.llm import model_selection
from flaskr.service.common.models import ERROR_CODE, AppError

pytestmark = pytest.mark.no_mock_llm


@pytest.fixture(autouse=True)
def provider_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "MODEL_ALIAS_MAP", {})
    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {})


@pytest.mark.parametrize(
    "legacy",
    [
        {"LLM_ALLOWED_MODELS": "legacy", "LLM_ALLOWED_MODEL_DISPLAY_NAMES": "Legacy"},
        {
            "llm-allowed-models": ["legacy"],
            "llm-allowed-model-display-names": ["Legacy"],
        },
        {"LLM_ALLOWED_MODELS": " ", "llm-allowed-models": "legacy"},
        {},
    ],
)
def test_numbered_model_slots_do_not_read_retired_allowlist_sources(
    monkeypatch: pytest.MonkeyPatch,
    legacy: dict,
) -> None:
    values = legacy | {"LLM_MODEL_1_NAME": "Daily", "LLM_MODEL_1_ID": "test/daily"}
    reader = Mock(side_effect=lambda key, default=None: values.get(key, default))
    monkeypatch.setattr(model_selection, "get_config", reader)
    monkeypatch.setattr(model_selection, "has_config_override", lambda _key: False)
    assert model_selection.get_configured_model_slots() == [
        {"index": "1", "display_name": "Daily", "model": "test/daily"}
    ]
    assert all(call.args[0].startswith("LLM_MODEL_") for call in reader.call_args_list)


def test_missing_api_key_disables_provider_without_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "get_config", lambda _: "")
    fetch = Mock()
    monkeypatch.setattr(llm, "_fetch_provider_models", fetch)
    result = llm._init_litellm_provider(
        llm.ProviderConfig(
            "example", "EXAMPLE_KEY", prefix="example/", wildcard_prefixes=("model-",)
        )
    )
    assert result == llm.ProviderState(
        enabled=False,
        params=None,
        models=[],
        prefix="example/",
        wildcard_prefixes=("model-",),
    )
    assert llm.MODEL_ALIAS_MAP == {}
    fetch.assert_not_called()


def test_provider_discovery_filters_duplicates_and_registers_alias_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm, "get_config", {"KEY": "key", "URL": "https://llm.invalid/v1"}.get
    )
    fetch = Mock(return_value=["chat-a", "embedding-b", "chat-a", "", "chat-b"])
    monkeypatch.setattr(llm, "_fetch_provider_models", fetch)
    config = llm.ProviderConfig(
        "example",
        "KEY",
        base_url_env="URL",
        prefix="example/",
        static_models=["static"],
        extra_models=[("alias", "actual"), ("alias", "other"), ""],
        filter_fn=lambda model: model.startswith("chat-"),
        custom_llm_provider="openai",
    )
    result = llm._init_litellm_provider(config)
    assert result.enabled
    assert result.params == {
        "api_key": "key",
        "api_base": "https://llm.invalid/v1",
        "custom_llm_provider": "openai",
    }
    assert result.models == [
        "example/static",
        "example/chat-a",
        "example/chat-b",
        "example/alias",
    ]
    assert llm.MODEL_ALIAS_MAP["example/alias"] == ("example", "actual")
    assert llm.MODEL_ALIAS_MAP["actual"] == ("example", "actual")
    fetch.assert_called_once_with("key", "https://llm.invalid/v1")


def test_failed_discovery_keeps_static_and_extra_models_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "get_config", lambda _: "key")
    monkeypatch.setattr(
        llm, "_fetch_provider_models", Mock(side_effect=ConnectionError("offline"))
    )
    config = llm.ProviderConfig(
        "example",
        "KEY",
        default_base_url="https://llm.invalid/v1",
        static_models=["static"],
        extra_models=["extra"],
    )
    result = llm._init_litellm_provider(config)
    assert result.enabled
    assert result.models == ["static", "extra"]
    assert result.params["api_base"] == "https://llm.invalid/v1"


def test_custom_model_loader_owns_discovery_and_gemini_uses_native_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm,
        "get_config",
        {"KEY": "key", "URL": "https://generativelanguage.googleapis.com/v1beta"}.get,
    )
    loader = Mock(return_value=[("display", "actual")])
    fetch = Mock()
    monkeypatch.setattr(llm, "_fetch_provider_models", fetch)
    config = llm.ProviderConfig(
        "gemini", "KEY", base_url_env="URL", model_loader=loader
    )
    result = llm._init_litellm_provider(config)
    assert result.params == {"api_key": "key"}
    assert result.models == ["display"]
    loader.assert_called_once_with(config, {"api_key": "key"}, None)
    fetch.assert_not_called()


def test_models_endpoint_handles_empty_key_and_ignores_entries_without_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.json.return_value = {
        "data": [{"id": "first"}, {}, {"id": ""}, {"id": "second"}]
    }
    get = Mock(return_value=response)
    monkeypatch.setattr(llm.requests, "get", get)
    assert llm._fetch_provider_models("", None) == []
    get.assert_not_called()
    assert llm._fetch_provider_models("key", "https://llm.invalid/v1/") == [
        "first",
        "second",
    ]
    get.assert_called_once_with(
        "https://llm.invalid/v1/models",
        headers={"Authorization": "Bearer key", "Content-Type": "application/json"},
        timeout=20,
    )
    response.raise_for_status.assert_called_once()


@pytest.mark.parametrize("registration", [None, "raises"])
def test_configured_output_limits_survive_missing_or_failing_litellm_registration(
    monkeypatch: pytest.MonkeyPatch, registration: str | None
) -> None:
    monkeypatch.setattr(llm, "get_config", lambda *_: {"model-a": 2048})
    register = (
        None if registration is None else Mock(side_effect=RuntimeError("unavailable"))
    )
    monkeypatch.setattr(llm.litellm, "register_model", register)
    assert llm._load_and_register_model_max_output_tokens() == {"model-a": 2048}
    if register is not None:
        register.assert_called_once_with({"model-a": {"max_output_tokens": 2048}})


def test_empty_output_limit_config_does_not_register_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "get_config", lambda *_: "")
    register = Mock()
    monkeypatch.setattr(llm.litellm, "register_model", register)
    assert llm._load_and_register_model_max_output_tokens() == {}
    register.assert_not_called()


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm, "get_litellm_params_and_model", lambda _: ({}, "upstream-model", "openai")
    )


@pytest.mark.usefixtures("gateway")
@pytest.mark.parametrize("requested", [True, False, 0, -1, "100", 1.5, 1025])
def test_gateway_rejects_invalid_or_excessive_output_limits(
    monkeypatch: pytest.MonkeyPatch, requested: object
) -> None:
    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {"model": 1024})
    reject = Mock(wraps=llm.raise_error_with_args)
    monkeypatch.setattr(llm, "raise_error_with_args", reject)
    with pytest.raises(AppError):
        llm.resolve_llm_max_output_tokens("model", requested)
    reject.assert_called_once_with(
        "server.llm.requestFailed",
        model="model",
        message="max_tokens exceeds model limit 1024"
        if requested == 1025
        else "max_tokens",
    )


@pytest.mark.usefixtures("gateway")
@pytest.mark.parametrize("limit", [0, None, RuntimeError("unknown")])
def test_gateway_rejects_models_without_a_known_positive_limit(
    monkeypatch: pytest.MonkeyPatch, limit: object
) -> None:
    get = (
        Mock(side_effect=limit)
        if isinstance(limit, Exception)
        else Mock(return_value=limit)
    )
    monkeypatch.setattr(llm.litellm, "get_max_tokens", get)
    with pytest.raises(AppError) as caught:
        llm.resolve_llm_max_output_tokens("model")
    assert caught.value.code == ERROR_CODE["server.llm.modelNotSupported"]
    get.assert_called_once_with("upstream-model")


@pytest.mark.usefixtures("gateway")
@pytest.mark.parametrize("count", [None, 0, -3])
def test_gateway_rejects_nonpositive_input_token_count(
    monkeypatch: pytest.MonkeyPatch, count: int | None
) -> None:
    counter = Mock(return_value=count)
    monkeypatch.setattr(llm.litellm, "token_counter", counter, raising=False)
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "function": {"name": "lookup"}}]
    with pytest.raises(AppError) as caught:
        llm.count_llm_chat_input_tokens("model", messages, tools=tools)
    assert caught.value.code == ERROR_CODE["server.llm.modelNotSupported"]
    counter.assert_called_once_with(
        model="upstream-model", messages=messages, tools=tools
    )


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (None, 0),
        ({}, 0),
        (SimpleNamespace(), 0),
        ({"input_cache": 7}, 7),
        ({"input_tokens_details": {"cached_tokens": 7}}, 7),
        ({"prompt_tokens_details": {"cached_tokens": 7}}, 7),
        (SimpleNamespace(input_cache=7), 7),
        (SimpleNamespace(input_tokens_details={"cached_tokens": 7}), 7),
        (SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens=7)), 7),
    ],
)
def test_cache_token_usage_accepts_provider_dict_and_object_shapes(
    usage: object, expected: int
) -> None:
    assert llm._extract_input_cache(usage) == expected
    assert llm._extract_usage_value(usage, "absent") == 0


def test_async_logging_inside_running_loop_keeps_task_until_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    background = set()
    monkeypatch.setattr(llm, "_background_asyncio_tasks", background)
    completed = []

    async def job() -> None:
        completed.append("done")

    async def parent() -> None:
        assert llm._safe_asyncio_run(job()) is None
        assert len(background) == 1
        await asyncio.gather(*background)
        await asyncio.sleep(0)
        assert completed == ["done"]
        assert background == set()

    llm._original_asyncio_run(parent())


def test_async_logging_preserves_unrelated_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("unrelated failure")
    monkeypatch.setattr(llm, "_original_asyncio_run", Mock(side_effect=failure))
    with pytest.raises(RuntimeError, match="unrelated failure") as caught:
        llm._safe_asyncio_run(object())
    assert caught.value is failure


def test_async_logging_scheduler_failure_does_not_break_user_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm,
        "_original_asyncio_run",
        Mock(side_effect=RuntimeError("cannot be called from a running event loop")),
    )
    loop = SimpleNamespace(create_task=Mock(side_effect=RuntimeError("loop closed")))
    monkeypatch.setattr(llm.asyncio, "get_running_loop", lambda: loop)
    assert llm._safe_asyncio_run(object()) is None
    loop.create_task.assert_called_once()

"""Verify numbered model isolation, gateway limits and provider boundaries."""

import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.api import llm
from flaskr.api.llm import model_selection
from flaskr.service.common.models import ERROR_CODE, AppError

from tests.common.fixtures.llm_routes import install_llm_routes

pytestmark = pytest.mark.no_mock_llm


@pytest.fixture(autouse=True)
def provider_state(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert model_selection.get_configured_model_slots() == [
        {"index": "1", "display_name": "Daily", "model": "test/daily"}
    ]
    assert all(call.args[0].startswith("LLM_MODEL_") for call in reader.call_args_list)


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


def test_empty_output_limit_config_keeps_native_model_metadata(
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
        llm,
        "get_litellm_params_and_model",
        lambda _: ({"api_key": "test"}, "upstream-model", "openai"),
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
@pytest.mark.parametrize(
    "limit", [0, -1, None, True, False, "8192", 1.5, {}, RuntimeError("unknown")]
)
@pytest.mark.parametrize(
    ("requested", "expected"), [(None, None), (32, 32), (8192, 8192)]
)
def test_gateway_allows_models_without_a_known_positive_limit(
    monkeypatch: pytest.MonkeyPatch,
    limit: object,
    requested: object,
    expected: int | None,
) -> None:
    get = (
        Mock(side_effect=limit)
        if isinstance(limit, Exception)
        else Mock(return_value=limit)
    )
    monkeypatch.setattr(llm.litellm, "get_max_tokens", get)
    assert llm.resolve_llm_max_output_tokens("model", requested) == expected
    get.assert_called_once_with("upstream-model")


@pytest.mark.usefixtures("gateway")
@pytest.mark.parametrize("requested", [True, False, 0, -1, "100", 1.5, {}, []])
def test_gateway_rejects_invalid_output_tokens_even_without_metadata(
    monkeypatch: pytest.MonkeyPatch, requested: object
) -> None:
    monkeypatch.setattr(
        llm.litellm, "get_max_tokens", Mock(side_effect=ValueError("unknown"))
    )
    reject = Mock(wraps=llm.raise_error_with_args)
    monkeypatch.setattr(llm, "raise_error_with_args", reject)
    with pytest.raises(AppError):
        llm.resolve_llm_max_output_tokens("model", requested)
    reject.assert_called_once_with(
        "server.llm.requestFailed", model="model", message="max_tokens"
    )


@pytest.mark.usefixtures("gateway")
@pytest.mark.parametrize("limit", [2048, 8192])
def test_gateway_uses_valid_litellm_ceiling_when_config_is_absent(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    monkeypatch.setattr(llm.litellm, "get_max_tokens", Mock(return_value=limit))
    assert llm.resolve_llm_max_output_tokens("model") == limit
    assert llm.resolve_llm_max_output_tokens("model", limit) == limit
    with pytest.raises(AppError):
        llm.resolve_llm_max_output_tokens("model", limit + 1)


@pytest.mark.usefixtures("gateway")
def test_gateway_routed_config_has_priority_over_upstream_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {"model": 16384})
    lookup = Mock(return_value=1024)
    monkeypatch.setattr(llm.litellm, "get_max_tokens", lookup)
    assert llm.resolve_llm_max_output_tokens("model", 8192) == 8192
    lookup.assert_not_called()


def test_gateway_still_rejects_unroutable_models_without_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_llm_routes(monkeypatch, {}, exclusive=True)
    lookup = Mock(side_effect=RuntimeError("unknown"))
    monkeypatch.setattr(llm.litellm, "get_max_tokens", lookup)
    with pytest.raises(AppError) as caught:
        llm.resolve_llm_max_output_tokens("unknown-model", 32)
    assert caught.value.code == ERROR_CODE["server.llm.modelNotSupported"]
    lookup.assert_not_called()


def test_gateway_still_requires_provider_credentials_when_limits_are_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_llm_routes(
        monkeypatch,
        {"model": ("openai", "model")},
        missing={"model": ("OPENAI_API_KEY",)},
    )
    lookup = Mock(side_effect=RuntimeError("unknown"))
    monkeypatch.setattr(llm.litellm, "get_max_tokens", lookup)
    with pytest.raises(AppError) as caught:
        llm.resolve_llm_max_output_tokens("model", 32)
    assert caught.value.code == ERROR_CODE["server.llm.specifiedLlmNotConfigured"]
    lookup.assert_not_called()


@pytest.mark.parametrize("limit", [0, -1, None, True, "8192", 1.5, {}])
@pytest.mark.parametrize("requested", [None, 8192])
def test_shared_stream_ignores_invalid_metadata_and_preserves_caller_tokens(
    monkeypatch: pytest.MonkeyPatch, limit: object, requested: int | None
) -> None:
    monkeypatch.setattr(llm.litellm, "get_max_tokens", Mock(return_value=limit))
    complete = Mock(return_value=iter([]))
    monkeypatch.setattr(llm.litellm, "completion", complete)
    kwargs = {} if requested is None else {"max_tokens": requested}
    llm._stream_litellm_completion(
        SimpleNamespace(logger=Mock()), "model", "upstream-model", [], {}, kwargs
    )
    if requested is None:
        assert "max_tokens" not in complete.call_args.kwargs
    else:
        assert complete.call_args.kwargs["max_tokens"] == requested


@pytest.mark.usefixtures("gateway")
@pytest.mark.parametrize(
    "method",
    [
        "invoke_llm",
        "chat_llm",
        "stream_openai_chat_completion",
        "complete_openai_chat_completion",
    ],
)
@pytest.mark.parametrize("requested", [True, False, 0, -1, "100", 1.5])
def test_all_completion_paths_reject_invalid_limits_before_provider_call(
    monkeypatch: pytest.MonkeyPatch, app: object, method: str, requested: object
) -> None:
    """Shared validation must not send invalid budgets upstream."""
    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {"model": 1024})
    complete = Mock()
    monkeypatch.setattr(llm.litellm, "completion", complete)
    monkeypatch.setattr(llm, "record_llm_usage", Mock())
    reject = Mock(wraps=llm.raise_error_with_args)
    monkeypatch.setattr(llm, "raise_error_with_args", reject)
    arguments = {
        "app": app,
        "user_id": "user",
        "span": Mock(),
        "model": "model",
        "max_tokens": requested,
    }
    if method == "invoke_llm":
        arguments["message"] = "hello"
    else:
        arguments["messages"] = [{"role": "user", "content": "hello"}]
    if "openai" in method:
        arguments.update(request_id="invalid-budget", fallback_input_tokens=12)

    def invoke() -> None:
        result = getattr(llm, method)(**arguments)
        if method != "complete_openai_chat_completion":
            list(result)

    with pytest.raises(AppError):
        invoke()
    reject.assert_called_once_with(
        "server.llm.requestFailed",
        model="model",
        message="max_tokens",
    )
    complete.assert_not_called()


@pytest.mark.usefixtures("gateway")
@pytest.mark.parametrize("stream", [False, True])
def test_gateway_rejects_excessive_budget_before_claim_or_provider_call(
    monkeypatch: pytest.MonkeyPatch, app: object, stream: bool
) -> None:
    """External budgets remain strict even though shared preparation caps task budgets."""
    from flaskr.route import model_gateway_runtime as runtime

    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {"model": 1024})
    monkeypatch.setattr(runtime, "admit_creator_usage", Mock())
    monkeypatch.setattr(runtime, "has_complete_llm_rates", lambda _model: True)
    claim = Mock()
    complete = Mock()
    counter = Mock()
    monkeypatch.setattr(runtime, "_claim_gateway_request", claim)
    monkeypatch.setattr(llm.litellm, "completion", complete)
    monkeypatch.setattr(llm.litellm, "token_counter", counter)
    with pytest.raises(runtime.GatewayRequestError) as caught:
        runtime.prepare_gateway_chat_request(
            app,
            creator_bid="user",
            idempotency_key="excessive-budget",
            payload={
                "model": "model",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 8192,
                "stream": stream,
            },
        )
    assert caught.value.status_code == 400
    assert caught.value.code == "model_not_available"
    claim.assert_not_called()
    counter.assert_not_called()
    complete.assert_not_called()


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


def test_litellm_stream_logs_with_its_own_loop() -> None:
    # A fresh process observes whether importing the gateway changes asyncio.run.
    script = textwrap.dedent(
        """
        import asyncio
        from queue import SimpleQueue
        from threading import get_ident
        from unittest.mock import patch

        original_run = asyncio.run
        from flaskr.api import llm
        from litellm.litellm_core_utils.litellm_logging import Logging

        assert asyncio.run is original_run
        logging_threads = SimpleQueue()

        async def observe_logging(*args, **kwargs):
            logging_threads.put(get_ident())

        async def consume_stream():
            chunks = llm.litellm.completion(
                model="gpt-4o",
                messages=[{"role": "user", "content": "hello"}],
                stream=True,
                mock_response="Hello world",
            )
            return "".join(
                chunk.choices[0].delta.content or ""
                for chunk in chunks if chunk.choices
            )

        with patch.object(Logging, "async_success_handler", observe_logging):
            assert asyncio.run(consume_stream()) == "Hello world"
            assert logging_threads.get(timeout=5) != get_ident()
        """
    )
    env = {
        key: value for key, value in os.environ.items() if not key.endswith("_API_KEY")
    }
    env.update(
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        PYTHON_DOTENV_DISABLED="1",
        SKIP_LOAD_DOTENV="1",
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        env=env,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

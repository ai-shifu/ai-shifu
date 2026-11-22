"""Verify model ids route by LiteLLM's rules with LiteLLM's own credentials."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, ClassVar
from unittest.mock import Mock, patch

import pytest
from flaskr.api import llm
from flaskr.api.llm import model_selection
from flaskr.common import llm_routing
from flaskr.service.common.models import ERROR_CODE, AppError

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.no_mock_llm

_CREDENTIAL_SUFFIXES = (
    "_KEY",
    "_TOKEN",
    "_API_BASE",
    "_API_URL",
    "_BASE_URL",
    "_API_VERSION",
)


@pytest.fixture
def clean_env() -> Iterator[dict[str, str]]:
    """Run with no provider credentials; tests add the ones they need."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.endswith(_CREDENTIAL_SUFFIXES)
    }
    with patch.dict(os.environ, environment, clear=True):
        yield os.environ


@pytest.mark.parametrize(
    ("model", "provider", "invoke_model"),
    [
        ("openai/gpt-4o", "openai", "gpt-4o"),
        ("gpt-4o", "openai", "gpt-4o"),
        ("o3-mini", "openai", "o3-mini"),
        ("dashscope/qwen-max", "dashscope", "qwen-max"),
        ("bigmodel/glm-4.6", "bigmodel", "glm-4.6"),
        ("zai/glm-4.6", "zai", "glm-4.6"),
        ("volcengine/doubao-seed-1-6", "volcengine", "doubao-seed-1-6"),
        ("deepseek/deepseek-chat", "deepseek", "deepseek-chat"),
        # A bare registry name uses the provider LiteLLM's registry records.
        ("deepseek-chat", "deepseek", "deepseek-chat"),
        ("gemini/gemini-2.5-pro", "gemini", "gemini-2.5-pro"),
        ("anthropic/claude-sonnet-4-5", "anthropic", "claude-sonnet-4-5"),
        ("claude-sonnet-4-5", "anthropic", "claude-sonnet-4-5"),
        ("openrouter/openai/gpt-4o", "openrouter", "openai/gpt-4o"),
        ("qianfan/ernie-4.5-turbo-128k", "qianfan", "ernie-4.5-turbo-128k"),
        ("siliconflow/Qwen/Qwen3-8B", "siliconflow", "Qwen/Qwen3-8B"),
    ],
)
def test_litellm_model_ids_resolve_to_litellm_providers(
    clean_env: dict[str, str], model: str, provider: str, invoke_model: str
) -> None:
    _ = clean_env
    route = llm_routing.resolve_route(model)

    assert route is not None
    assert (route.provider, route.model) == (provider, invoke_model)
    assert route.completion_params() == {"custom_llm_provider": provider}


@pytest.mark.parametrize(
    "model", ["", "  ", "vanchin/deepseek-v3", "not-a-known-model", "unknown/x/y"]
)
def test_unrecognized_ids_do_not_route_or_reach_litellm(
    monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    get_llm_provider = Mock(wraps=llm_routing.litellm.get_llm_provider)
    monkeypatch.setattr(llm_routing.litellm, "get_llm_provider", get_llm_provider)

    assert llm_routing.resolve_route(model) is None
    # LiteLLM prints a provider-list banner for every miss it is asked about.
    get_llm_provider.assert_not_called()


@pytest.mark.parametrize(
    ("model", "key"),
    [
        ("gpt-4o", "OPENAI_API_KEY"),
        ("dashscope/qwen-max", "DASHSCOPE_API_KEY"),
        ("bigmodel/glm-4.6", "BIGMODEL_API_KEY"),
        ("zai/glm-4.6", "ZAI_API_KEY"),
        ("volcengine/ep-1", "VOLCENGINE_API_KEY"),
        ("deepseek/deepseek-chat", "DEEPSEEK_API_KEY"),
        ("anthropic/claude-sonnet-4-5", "ANTHROPIC_API_KEY"),
        ("openrouter/openai/gpt-4o", "OPENROUTER_API_KEY"),
        ("qianfan/ernie-4.5", "QIANFAN_API_KEY"),
        ("siliconflow/Qwen/Qwen3-8B", "SILICONFLOW_API_KEY"),
    ],
)
def test_credentials_come_from_litellm_variables(
    clean_env: dict[str, str], model: str, key: str
) -> None:
    missing = llm_routing.resolve_route(model)
    assert missing is not None
    assert key in missing.missing_credentials
    assert not missing.configured

    clean_env[key] = "secret"
    configured = llm_routing.resolve_route(model)
    assert configured is not None
    assert configured.configured
    # LiteLLM reads the key itself; it never enters the request arguments.
    assert configured.completion_params() == {
        "custom_llm_provider": configured.provider
    }


@pytest.mark.parametrize(
    ("model", "key"),
    [
        ("openai/gpt-4o", "OPENAI_API_KEY"),
        ("anthropic/claude-sonnet-4-5", "ANTHROPIC_API_KEY"),
        ("dashscope/qwen-max", "DASHSCOPE_API_KEY"),
        ("bigmodel/glm-4.6", "BIGMODEL_API_KEY"),
        ("siliconflow/Qwen/Qwen3-8B", "SILICONFLOW_API_KEY"),
    ],
)
def test_blank_credentials_count_as_missing(
    clean_env: dict[str, str], model: str, key: str
) -> None:
    # An env file line such as ``OPENAI_API_KEY=`` must not pass validation.
    clean_env[key] = "  "
    route = llm_routing.resolve_route(model)
    assert route is not None
    assert route.missing_credentials == (key,)
    assert not route.configured


def test_credential_references_are_expanded_before_litellm_reads_them(
    clean_env: dict[str, str],
) -> None:
    clean_env.update(SHARED_KEY="real-secret", OPENAI_API_KEY="${SHARED_KEY}")
    route = llm_routing.resolve_route("openai/gpt-4o")
    assert route is not None
    assert route.configured
    # LiteLLM reads the variable itself, so it must hold the expanded value.
    assert os.environ["OPENAI_API_KEY"] == "real-secret"


def test_resolved_default_endpoint_satisfies_the_base_check(
    clean_env: dict[str, str],
) -> None:
    _ = clean_env
    route = llm_routing.resolve_route("ollama/llama3")
    assert route is not None
    assert route.api_base == "http://localhost:11434"
    assert route.configured


@pytest.mark.parametrize("key", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
def test_gemini_accepts_either_litellm_key_name(
    clean_env: dict[str, str], key: str
) -> None:
    clean_env[key] = "secret"
    route = llm_routing.resolve_route("gemini/gemini-2.5-pro")
    assert route is not None
    assert route.configured


def test_registered_provider_base_url_follows_its_litellm_variable(
    clean_env: dict[str, str],
) -> None:
    clean_env["SILICONFLOW_API_BASE"] = "https://api.siliconflow.com/v1"
    route = llm_routing.resolve_route("siliconflow/Qwen/Qwen3-8B")
    assert route is not None
    assert route.api_base == "https://api.siliconflow.com/v1"


def test_extra_providers_defer_to_a_litellm_release_that_ships_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = llm_routing._json_provider_registry()
    providers = dict(registry._providers)
    monkeypatch.setattr(registry, "_providers", providers)
    for name in llm_routing.EXTRA_OPENAI_COMPATIBLE_PROVIDERS:
        providers.pop(name, None)
    monkeypatch.setattr(
        llm_routing, "_builtin_provider_names", lambda: frozenset({"siliconflow"})
    )

    assert llm_routing.register_extra_providers() == ["qianfan"]
    assert "siliconflow" not in providers
    # A second registration changes nothing.
    assert llm_routing.register_extra_providers() == []


class _ChatServer(BaseHTTPRequestHandler):
    requests: ClassVar[list[dict[str, object]]] = []

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        self.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("authorization"),
                "model": body.get("model"),
            }
        )
        chunk = {
            "id": "chunk",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "hello"},
                    "finish_reason": "stop",
                }
            ],
        }
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode())

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def chat_server() -> Iterator[str]:
    _ChatServer.requests = []
    server = HTTPServer(("127.0.0.1", 0), _ChatServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("model", "key_env", "base_env", "upstream_model"),
    [
        (
            "siliconflow/Qwen/Qwen3-8B",
            "SILICONFLOW_API_KEY",
            "SILICONFLOW_API_BASE",
            "Qwen/Qwen3-8B",
        ),
        (
            "qianfan/ernie-4.5-turbo-128k",
            "QIANFAN_API_KEY",
            "QIANFAN_API_BASE",
            "ernie-4.5-turbo-128k",
        ),
    ],
)
def test_registered_providers_complete_through_litellm(
    clean_env: dict[str, str],
    chat_server: str,
    model: str,
    key_env: str,
    base_env: str,
    upstream_model: str,
) -> None:
    clean_env[key_env] = "provider-secret"
    clean_env[base_env] = chat_server
    params, invoke_model, provider = llm.get_litellm_params_and_model(model)

    response = llm_routing.litellm.completion(
        model=invoke_model,
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        **params,
    )

    assert "".join(chunk.choices[0].delta.content or "" for chunk in response) == (
        "hello"
    )
    assert provider == model.split("/", 1)[0]
    assert _ChatServer.requests == [
        {
            "path": "/v1/chat/completions",
            "authorization": "Bearer provider-secret",
            "model": upstream_model,
        }
    ]


def test_missing_credentials_raise_not_configured_naming_the_variables(
    clean_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = clean_env
    reject = Mock(wraps=llm.raise_error_with_args)
    monkeypatch.setattr(llm, "raise_error_with_args", reject)

    with pytest.raises(AppError) as exc_info:
        llm.get_litellm_params_and_model("anthropic/claude-sonnet-4-5")

    assert exc_info.value.code == ERROR_CODE["server.llm.specifiedLlmNotConfigured"]
    assert reject.call_args.kwargs["config_var"] == "ANTHROPIC_API_KEY"


def test_unrecognized_ids_return_no_provider(clean_env: dict[str, str]) -> None:
    _ = clean_env
    assert llm.get_litellm_params_and_model("vanchin/model") == (
        None,
        "vanchin/model",
        None,
    )


def test_any_litellm_provider_reaches_completion(
    clean_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, app: object
) -> None:
    clean_env["OPENROUTER_API_KEY"] = "secret"
    monkeypatch.setattr(llm, "MODEL_MAX_OUTPUT_TOKENS", {})
    captured: dict[str, object] = {}

    def fake_completion(model: str, **kwargs: object) -> object:
        captured.update(model=model, **kwargs)
        return iter([])

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    params, invoke_model, provider = llm.get_litellm_params_and_model(
        "openrouter/anthropic/claude-sonnet-4.5"
    )
    list(
        llm._iter_stream_with_precontent_retry(
            app,
            "openrouter/anthropic/claude-sonnet-4.5",
            invoke_model,
            [{"role": "user", "content": "hi"}],
            params,
            {},
            provider_key=provider,
        )
    )

    assert captured["model"] == "anthropic/claude-sonnet-4.5"
    assert captured["custom_llm_provider"] == "openrouter"
    assert "api_key" not in captured


def test_gemini_capabilities_apply_to_prefixed_ids(
    clean_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    clean_env["GEMINI_API_KEY"] = "secret"
    monkeypatch.setattr(
        llm,
        "MODEL_SUPPORTED_GENERATION_METHODS",
        {"gemini-live-preview": frozenset({"bidiGenerateContent"})},
    )
    values = {"LLM_MODEL_1_ID": "gemini/gemini-live-preview"}
    monkeypatch.setattr(
        model_selection, "get_config", lambda key, *_args: values.get(key)
    )

    assert llm.get_model_generation_methods("gemini/gemini-live-preview") == (
        frozenset({"bidiGenerateContent"})
    )
    with pytest.raises(AppError) as exc_info:
        model_selection.resolve_model_slot("1")
    assert exc_info.value.code == ERROR_CODE["server.llm.modelUnavailable"]


def test_region_in_model_id_reaches_completion_as_api_base(
    clean_env: dict[str, str],
) -> None:
    _ = clean_env
    route = llm_routing.resolve_route("bedrock_mantle/eu-west-1/openai.gpt-oss-120b")
    assert route is not None
    assert route.model == "openai.gpt-oss-120b"
    # Completion sees only the stripped model, so the region's endpoint is
    # forwarded explicitly instead of LiteLLM's default region.
    assert route.completion_params()["api_base"] == (
        "https://bedrock-mantle.eu-west-1.api.aws/v1"
    )
    plain = llm_routing.resolve_route("dashscope/qwen-max")
    assert plain is not None
    assert "api_base" not in plain.completion_params()


def test_azure_ad_token_stands_in_for_the_api_key(
    clean_env: dict[str, str],
) -> None:
    clean_env.update(AZURE_API_BASE="https://x.example", AZURE_API_VERSION="v1")
    route = llm_routing.resolve_route("azure/my-deployment")
    assert route is not None
    assert route.missing_credentials == ("AZURE_API_KEY",)

    clean_env["AZURE_AD_TOKEN"] = "token"
    route = llm_routing.resolve_route("azure/my-deployment")
    assert route is not None
    assert route.configured


@pytest.mark.parametrize(
    "key",
    [
        "TOGETHERAI_API_KEY",
        "TOGETHER_API_KEY",
        "TOGETHER_AI_API_KEY",
        "TOGETHER_AI_TOKEN",
    ],
)
def test_together_accepts_each_key_name_litellm_reads(
    clean_env: dict[str, str], key: str
) -> None:
    model = "together_ai/meta-llama/Llama-3-8b-chat-hf"
    route = llm_routing.resolve_route(model)
    assert route is not None
    assert route.missing_credentials == ("TOGETHERAI_API_KEY",)
    clean_env[key] = "secret"
    route = llm_routing.resolve_route(model)
    assert route is not None
    assert route.configured


@pytest.mark.parametrize(
    ("model", "reported", "alias"),
    [
        (
            "replicate/meta/llama-3-8b-instruct",
            "REPLICATE_API_KEY",
            "REPLICATE_API_TOKEN",
        ),
        ("huggingface/meta-llama/Llama-3-8B", "HUGGINGFACE_API_KEY", "HF_TOKEN"),
    ],
)
def test_key_aliases_litellm_completion_reads_satisfy_validation(
    clean_env: dict[str, str], model: str, reported: str, alias: str
) -> None:
    route = llm_routing.resolve_route(model)
    assert route is not None
    assert reported in route.missing_credentials
    clean_env[alias] = "secret"
    route = llm_routing.resolve_route(model)
    assert route is not None
    assert reported not in route.missing_credentials


@pytest.mark.parametrize(
    "slot_model", ["qwen/qwen-max", "dashscope/qwen-max", "qwen-max"]
)
def test_billing_candidates_include_the_canonical_litellm_id(
    clean_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, slot_model: str
) -> None:
    _ = clean_env
    if slot_model == "qwen-max":
        monkeypatch.setattr(
            llm, "_resolve_provider_for_model", lambda _m: ("dashscope", "qwen-max")
        )
    # A migrated rate keyed ``dashscope/qwen-max`` matches every slot form.
    provider, candidates = llm._resolve_billing_rate_identity(slot_model)
    assert provider == "dashscope"
    assert "dashscope/qwen-max" in candidates
    assert candidates[0] == "qwen-max"


def test_prefixed_live_only_model_is_rejected_without_metadata(
    clean_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn.live_follow_up_config import (
        GEMINI_LIVE_ONLY_MODEL_IDS,
    )

    clean_env["GEMINI_API_KEY"] = "secret"
    live_model = min(GEMINI_LIVE_ONLY_MODEL_IDS)
    # Discovery failed or a proxy omitted generation-method metadata.
    monkeypatch.setattr(llm, "MODEL_SUPPORTED_GENERATION_METHODS", {})
    values = {"LLM_MODEL_1_ID": f"gemini/{live_model}"}
    monkeypatch.setattr(
        model_selection, "get_config", lambda key, *_args: values.get(key)
    )

    with pytest.raises(AppError) as exc_info:
        model_selection.resolve_model_slot("1")
    assert exc_info.value.code == ERROR_CODE["server.llm.modelUnavailable"]


def test_billing_identity_uses_litellm_provider_names(
    clean_env: dict[str, str],
) -> None:
    _ = clean_env
    assert llm._resolve_billing_rate_identity("dashscope/qwen-max") == (
        "dashscope",
        ["qwen-max", "dashscope/qwen-max"],
    )

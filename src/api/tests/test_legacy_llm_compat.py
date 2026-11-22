"""Verify the temporary pre-LiteLLM configuration compatibility layer.

Delete this file together with ``flaskr/common/legacy_llm_compat.py``.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from flaskr.common import legacy_llm_compat, llm_routing

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.no_mock_llm

_CREDENTIAL_SUFFIXES = ("_API_KEY", "_API_BASE", "_API_URL", "_BASE_URL")


@pytest.fixture
def clean_env() -> Iterator[dict[str, str]]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.endswith(_CREDENTIAL_SUFFIXES)
    }
    with patch.dict(os.environ, environment, clear=True):
        yield os.environ


@pytest.mark.parametrize(
    ("legacy_model", "provider", "invoke_model"),
    [
        ("qwen/qwen-max", "dashscope", "qwen-max"),
        ("qwen/vanchin/deepseek-v3", "dashscope", "vanchin/deepseek-v3"),
        ("glm/glm-4.6", "bigmodel", "glm-4.6"),
        ("ark/doubao-seed-1-6", "volcengine", "doubao-seed-1-6"),
        ("ernie/ernie-4.5-turbo-128k", "qianfan", "ernie-4.5-turbo-128k"),
        ("silicon/deepseek-ai/DeepSeek-V3", "siliconflow", "deepseek-ai/DeepSeek-V3"),
        # LiteLLM would send a bare gemini name to Vertex AI.
        ("gemini-2.5-pro", "gemini", "gemini-2.5-pro"),
        ("deepseek-v4-flash", "deepseek", "deepseek-v4-flash"),
        ("gpt-6.1-sol-unlisted", "openai", "gpt-6.1-sol-unlisted"),
    ],
)
def test_legacy_model_ids_route_to_litellm_providers(
    clean_env: dict[str, str], legacy_model: str, provider: str, invoke_model: str
) -> None:
    _ = clean_env
    route = llm_routing.resolve_route(legacy_model)
    assert route is not None
    assert (route.provider, route.model) == (provider, invoke_model)


def test_known_bare_names_are_already_litellm_ids() -> None:
    assert legacy_llm_compat.rewrite_model_id("gpt-4o", {"gpt-4o"}) == "gpt-4o"
    assert legacy_llm_compat.rewrite_model_id("openai/gpt-4o") == "openai/gpt-4o"
    # ``qwen`` alone is a model name, not a legacy prefix.
    assert legacy_llm_compat.rewrite_model_id("qwen/") == "qwen/"


@pytest.mark.parametrize(
    ("model", "legacy_env", "provider", "param", "value"),
    [
        ("dashscope/qwen-max", "QWEN_API_KEY", "dashscope", "api_key", "k"),
        ("qwen/qwen-max", "QWEN_API_KEY", "dashscope", "api_key", "k"),
        ("volcengine/ep-1", "ARK_API_KEY", "volcengine", "api_key", "k"),
        ("qianfan/ernie-4.5", "ERNIE_API_KEY", "qianfan", "api_key", "k"),
        ("siliconflow/Qwen/Qwen3-8B", "SILICON_API_KEY", "siliconflow", "api_key", "k"),
    ],
)
def test_legacy_keys_configure_their_litellm_provider(
    clean_env: dict[str, str],
    model: str,
    legacy_env: str,
    provider: str,
    param: str,
    value: str,
) -> None:
    clean_env[legacy_env] = value
    route = llm_routing.resolve_route(model)
    assert route is not None
    assert route.configured
    assert route.completion_params() == {"custom_llm_provider": provider, param: value}


def test_litellm_variable_wins_over_legacy_variable(
    clean_env: dict[str, str],
) -> None:
    clean_env.update(
        DASHSCOPE_API_KEY="native",
        QWEN_API_KEY="legacy",
        QWEN_API_URL="https://legacy.example/v1",
    )
    route = llm_routing.resolve_route("dashscope/qwen-max")
    assert route is not None
    # LiteLLM reads DASHSCOPE_API_KEY itself; only the legacy base fills a gap.
    assert route.completion_params() == {
        "custom_llm_provider": "dashscope",
        "api_base": "https://legacy.example/v1",
    }
    assert route.api_base == "https://legacy.example/v1"


@pytest.mark.parametrize(
    ("legacy_env", "litellm_env", "value", "expected"),
    [
        (
            "DEEPSEEK_API_URL",
            "DEEPSEEK_API_BASE",
            "https://ds.example",
            "https://ds.example",
        ),
        (
            "SILICON_API_URL",
            "SILICONFLOW_API_BASE",
            "https://sf.example/v1",
            "https://sf.example/v1",
        ),
        (
            "GEMINI_API_URL",
            "GEMINI_API_BASE",
            "https://proxy.example/google",
            "https://proxy.example/google",
        ),
        # Earlier releases ignored the public Gemini endpoint as a base URL.
        (
            "GEMINI_API_URL",
            "GEMINI_API_BASE",
            "https://generativelanguage.googleapis.com",
            "",
        ),
        # A proxy whose path mentions that host is still a base URL.
        (
            "GEMINI_API_URL",
            "GEMINI_API_BASE",
            "https://proxy.example/generativelanguage.googleapis.com",
            "https://proxy.example/generativelanguage.googleapis.com",
        ),
        ("QWEN_API_URL", "DASHSCOPE_API_BASE", "  ", ""),
    ],
)
def test_legacy_base_urls_stand_in_for_unset_litellm_variables(
    clean_env: dict[str, str],
    legacy_env: str,
    litellm_env: str,
    value: str,
    expected: str,
) -> None:
    clean_env[legacy_env] = value
    assert llm_routing.env_value(litellm_env) == expected
    clean_env[litellm_env] = "https://native.example"
    assert llm_routing.env_value(litellm_env) == "https://native.example"


def test_compat_never_writes_the_environment(clean_env: dict[str, str]) -> None:
    clean_env.update(QWEN_API_KEY="k", ARK_API_KEY="a", GEMINI_API_URL="https://p")
    before = dict(clean_env)
    for model in ("qwen/qwen-max", "ark/ep-1", "gemini-2.5-pro"):
        llm_routing.resolve_route(model)
    llm_routing.env_value("GEMINI_API_BASE")
    assert dict(clean_env) == before


def test_each_legacy_form_warns_once_with_its_replacement(
    clean_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(legacy_llm_compat, "_warned", set())
    clean_env["QWEN_API_KEY"] = "k"
    with caplog.at_level(logging.WARNING, logger=legacy_llm_compat.__name__):
        for _ in range(3):
            llm_routing.resolve_route("qwen/qwen-max")

    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        "Model id 'qwen/qwen-max' uses a deprecated form; use 'dashscope/qwen-max'.",
        "QWEN_API_KEY is deprecated; set DASHSCOPE_API_KEY instead.",
    ]

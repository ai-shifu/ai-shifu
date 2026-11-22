"""Route text model ids the way LiteLLM does.

A model id follows LiteLLM's rules: ``provider/model`` (for example
``dashscope/qwen-max``, ``anthropic/claude-sonnet-4-5`` or
``openrouter/openai/gpt-4o``), or a bare model name LiteLLM's model registry
knows (``gpt-4o``). LiteLLM reads each provider's credentials from its own
environment variables, so AI-Shifu never passes an API key or base URL.

This module stays free of Flask and database imports because startup
configuration validation uses it before the application is built.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# litellm fetches its model cost map from GitHub at import time by default,
# which stalls every worker boot (and times out entirely on hosts without
# outbound internet). Default to the bundled local map; deployments can still
# override by exporting LITELLM_LOCAL_MODEL_COST_MAP=False before startup.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
# litellm hands every completion's success logging to a process-wide pool that grows to
# 100 threads and keeps them. No litellm callbacks are registered here, so a few threads
# drain that work; 100 idle threads per Gunicorn worker only hold memory.
os.environ.setdefault("LOGGING_EXECUTOR_MAX_THREADS", "4")

import litellm

from flaskr.common import legacy_llm_compat

# OpenAI-compatible providers LiteLLM 1.109.1 does not ship yet. Each entry has
# the same shape as an entry in LiteLLM's own
# ``litellm/llms/openai_like/providers.json``; upstream proposals use these
# names (BerriAI/litellm#29332 for SiliconFlow, #49777 for Qianfan). Once the
# pinned LiteLLM ships a provider, its own definition wins and the entry here
# can be deleted.
EXTRA_OPENAI_COMPATIBLE_PROVIDERS: dict[str, dict[str, str]] = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key_env": "SILICONFLOW_API_KEY",
        "api_base_env": "SILICONFLOW_API_BASE",
    },
    "qianfan": {
        "base_url": "https://qianfan.baidubce.com/v2",
        "api_key_env": "QIANFAN_API_KEY",
        "api_base_env": "QIANFAN_API_BASE",
    },
}


def _json_provider_registry() -> object | None:
    try:
        from litellm.llms.openai_like.json_loader import JSONProviderRegistry
    except ImportError:
        return None
    return JSONProviderRegistry


def register_extra_providers() -> list[str]:
    """Add the extra providers to LiteLLM's JSON provider registry.

    LiteLLM loads that registry only from its packaged file, so the entries are
    added to the loaded registry. Returns the names that were added.
    """
    registry = _json_provider_registry()
    if registry is None:
        return []
    from litellm.llms.openai_like.json_loader import SimpleProviderConfig

    registry.load()
    added = []
    for name, config in EXTRA_OPENAI_COMPATIBLE_PROVIDERS.items():
        if registry.exists(name) or name in _builtin_provider_names():
            continue
        # LiteLLM has no public registration hook for JSON providers.
        registry._providers[name] = SimpleProviderConfig(name, dict(config))
        added.append(name)
    return added


def _builtin_provider_names() -> frozenset[str]:
    names = set()
    for provider in getattr(litellm, "provider_list", None) or ():
        name = getattr(provider, "value", provider)
        if isinstance(name, str) and name:
            names.add(name)
    return frozenset(names)


def litellm_provider_names() -> frozenset[str]:
    """Return every provider name LiteLLM accepts as a model id prefix."""
    registry = _json_provider_registry()
    json_names = set(registry.list_providers()) if registry is not None else set()
    return _builtin_provider_names() | json_names


@dataclass(frozen=True)
class LLMRoute:
    """Describe how LiteLLM serves one configured model id.

    ``provider`` is LiteLLM's provider name; it is also the billing and usage
    identity. ``model`` is the provider-local id sent to LiteLLM.
    ``missing_credentials`` names environment variables LiteLLM needs but
    cannot find. ``credentials`` carries values only legacy variables supply;
    LiteLLM reads every other credential from its own variables.
    """

    provider: str
    model: str
    api_base: str | None = None
    missing_credentials: tuple[str, ...] = ()
    credentials: tuple[tuple[str, str], ...] = ()

    @property
    def configured(self) -> bool:
        """Return whether LiteLLM has the provider's credentials."""
        return not self.missing_credentials

    def completion_params(self) -> dict[str, str]:
        """Return the provider arguments passed to ``litellm.completion``."""
        return {"custom_llm_provider": self.provider, **dict(self.credentials)}


def env_value(name: str) -> str:
    """Read a LiteLLM variable, honoring its legacy name while compat lasts."""
    value = str(os.environ.get(name) or "").strip()
    return value or legacy_llm_compat.legacy_env_value(name)


# Key variables LiteLLM reads for these providers but does not report from
# ``validate_environment`` in the pinned version.
_UNREPORTED_KEY_ENVS: dict[str, str] = {
    "bigmodel": "BIGMODEL_API_KEY",
    "zai": "ZAI_API_KEY",
}


def _missing_credentials(provider: str, model: str) -> tuple[str, ...]:
    registry = _json_provider_registry()
    if registry is not None and registry.exists(provider):
        key_env = getattr(registry.get(provider), "api_key_env", None)
        if key_env and not str(os.environ.get(key_env) or "").strip():
            return (key_env,)
        return ()
    key_env = _UNREPORTED_KEY_ENVS.get(provider)
    if key_env:
        return () if str(os.environ.get(key_env) or "").strip() else (key_env,)
    try:
        environment = litellm.validate_environment(model=f"{provider}/{model}")
    except Exception:
        return ()
    return tuple(str(key) for key in environment.get("missing_keys") or () if key)


def resolve_route(model: object) -> LLMRoute | None:
    """Resolve a model id to its LiteLLM provider, or None if LiteLLM cannot."""
    requested = str(model or "").strip()
    if not requested:
        return None
    model_cost = getattr(litellm, "model_cost", None) or {}
    litellm_id = legacy_llm_compat.rewrite_model_id(requested, model_cost)
    prefix, separator, _rest = litellm_id.partition("/")
    providers = litellm_provider_names()
    if separator:
        if prefix not in providers:
            return None
    elif litellm_id in model_cost:
        # A bare registry name carries its provider; get_llm_provider cannot
        # always infer it from the name alone (for example deepseek-chat).
        registered = model_cost[litellm_id].get("litellm_provider")
        if isinstance(registered, str) and registered in providers:
            litellm_id = f"{registered}/{litellm_id}"
    else:
        # get_llm_provider prints a provider-list banner for every miss.
        return None
    try:
        invoke_model, provider, _key, api_base = litellm.get_llm_provider(litellm_id)
    except Exception:
        return None
    if not provider or not invoke_model:
        return None
    credentials = legacy_llm_compat.legacy_credentials(provider)
    missing = (
        () if "api_key" in credentials else _missing_credentials(provider, invoke_model)
    )
    return LLMRoute(
        provider=provider,
        model=invoke_model,
        api_base=credentials.get("api_base") or api_base or None,
        missing_credentials=missing,
        credentials=tuple(sorted(credentials.items())),
    )


register_extra_providers()

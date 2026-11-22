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
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

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
    cannot find, for providers whose credential names AI-Shifu has checked
    against LiteLLM's completion path. ``unverified_missing_credentials``
    holds what LiteLLM's environment check reports for any other provider;
    that check can ask for more than completion needs, so it only warns.
    ``credentials`` carries values only legacy variables supply; LiteLLM reads
    every other credential from its own variables.
    """

    provider: str
    model: str
    api_base: str | None = None
    missing_credentials: tuple[str, ...] = ()
    credentials: tuple[tuple[str, str], ...] = ()
    unverified_missing_credentials: tuple[str, ...] = ()

    @property
    def configured(self) -> bool:
        """Return whether LiteLLM has the provider's credentials."""
        return not self.missing_credentials

    @property
    def litellm_id(self) -> str:
        """Return the canonical LiteLLM model id, ``provider/model``."""
        return f"{self.provider}/{self.model}"

    def completion_params(self) -> dict[str, str]:
        """Return the provider arguments passed to ``litellm.completion``."""
        return {"custom_llm_provider": self.provider, **dict(self.credentials)}


class _ReaderView:
    """Expose a ``name -> value`` reader with the ``Mapping.get`` shape."""

    def __init__(self, read: Callable[[str], object]) -> None:
        self._read = read

    def get(self, name: str, default: object = None) -> object:
        value = self._read(name)
        return default if value is None else value


def config_value(name: str, read: Callable[[str], object]) -> str:
    """Read a LiteLLM-named setting through ``read``, such as ``get_config``.

    The legacy name stands in while compat lasts, read through the same
    reader, so settings stored outside the environment keep working.
    """
    value = str(read(name) or "").strip()
    return value or legacy_llm_compat.legacy_env_value(name, _ReaderView(read))


def env_value(name: str) -> str:
    """Read a LiteLLM variable, honoring its legacy name while compat lasts."""
    _normalize_credential_envs()
    return config_value(name, os.environ.get)


# Variables LiteLLM accepts for the Gemini API key, in lookup order.
GEMINI_API_KEY_ENVS: tuple[str, ...] = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

# Credential-like variable suffixes; a blank value means the setting is absent.
# ``_API_URL`` covers the legacy base URL names compat still reads.
_CREDENTIAL_ENV_SUFFIXES = (
    "_KEY",
    "_TOKEN",
    "_API_BASE",
    "_BASE_URL",
    "_API_URL",
    "_API_VERSION",
)


_ENV_REFERENCE = re.compile(r"\$\{([^}]+)\}")


def _normalize_credential_envs() -> None:
    """Prepare credential variables for LiteLLM, which reads them raw.

    ``${VAR}`` references are expanded the way ``EnhancedConfig`` expands
    configuration values (an unset reference stays literal), because LiteLLM
    would otherwise send the placeholder as the credential. Surrounding
    whitespace is trimmed, as configuration reads did. Blank values are
    removed: ``litellm.validate_environment`` only checks that a name exists,
    so an ``OPENAI_API_KEY=`` line would count as configured, while LiteLLM
    treats a blank value as unset anyway.
    """
    # Resolve every reference against one snapshot, so removing a blank
    # variable cannot leave a reference to it unexpanded.
    snapshot = dict(os.environ)
    updates: dict[str, str | None] = {}
    for name, value in snapshot.items():
        if not name.endswith(_CREDENTIAL_ENV_SUFFIXES):
            continue
        expanded = _ENV_REFERENCE.sub(
            lambda match: snapshot.get(match.group(1), match.group(0)), value
        ).strip()
        if not expanded:
            updates[name] = None
        elif expanded != value:
            updates[name] = expanded
    for name, value in updates.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


# Missing key -> variables LiteLLM's completion path accepts in its place but
# ``validate_environment`` does not consider.
_ALTERNATIVE_CREDENTIAL_ENVS: dict[str, tuple[str, ...]] = {
    "AZURE_API_KEY": ("AZURE_AD_TOKEN",),
    # LiteLLM resolves Together's key from any of these names.
    "TOGETHERAI_API_KEY": (
        "TOGETHER_API_KEY",
        "TOGETHER_AI_API_KEY",
        "TOGETHER_AI_TOKEN",
    ),
    "REPLICATE_API_KEY": ("REPLICATE_API_TOKEN",),
    "HUGGINGFACE_API_KEY": ("HF_TOKEN",),
}


# Providers whose credential variables were checked against LiteLLM's
# completion path, so a missing one blocks startup and requests. For other
# providers LiteLLM's environment check can over-report (alternative key
# names, built-in defaults), so a missing variable is only a warning.
CONFIRMED_CREDENTIAL_PROVIDERS: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "dashscope",
        "deepseek",
        "gemini",
        "bigmodel",
        "zai",
        "volcengine",
        "openrouter",
        *EXTRA_OPENAI_COMPATIBLE_PROVIDERS,
    }
)

# Reported variables LiteLLM's completion path fills with its own default.
_DEFAULTED_ENVS: frozenset[str] = frozenset({"AZURE_API_VERSION"})


def _has_alternative_credential(missing_key: str) -> bool:
    return any(
        str(os.environ.get(name) or "").strip()
        for name in _ALTERNATIVE_CREDENTIAL_ENVS.get(missing_key, ())
    )


# Key variables LiteLLM reads for these providers but does not report from
# ``validate_environment`` in the pinned version.
_UNREPORTED_KEY_ENVS: dict[str, str] = {
    "bigmodel": "BIGMODEL_API_KEY",
    "zai": "ZAI_API_KEY",
}


def _missing_credentials(
    provider: str, model: str, resolved_api_base: str | None
) -> tuple[str, ...]:
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
    return tuple(
        str(key)
        for key in environment.get("missing_keys") or ()
        # Some checks report a whole group when one member is missing.
        if key
        and not str(os.environ.get(str(key)) or "").strip()
        and not _has_alternative_credential(str(key))
        and str(key) not in _DEFAULTED_ENVS
        # LiteLLM already resolved a default endpoint (Ollama's localhost).
        and not (resolved_api_base and str(key).endswith(("_API_BASE", "_BASE_URL")))
    )


def _api_base_without_directives(provider: str, model: str) -> str | None:
    try:
        return litellm.get_llm_provider(f"{provider}/{model}")[3]
    except Exception:
        return None


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
    _normalize_credential_envs()
    try:
        invoke_model, provider, _key, api_base = litellm.get_llm_provider(litellm_id)
    except Exception:
        return None
    if not provider or not invoke_model:
        return None
    credentials = legacy_llm_compat.legacy_credentials(provider)
    if (
        api_base
        and "api_base" not in credentials
        and api_base != _api_base_without_directives(provider, invoke_model)
    ):
        # The id carried routing LiteLLM strips from the returned model, such
        # as the region in ``bedrock_mantle/<region>/<model>``. Completion only
        # sees the stripped model, so forward the endpoint it implied.
        credentials["api_base"] = api_base
    missing = (
        ()
        if "api_key" in credentials
        else _missing_credentials(provider, invoke_model, api_base)
    )
    confirmed = provider in CONFIRMED_CREDENTIAL_PROVIDERS
    return LLMRoute(
        provider=provider,
        model=invoke_model,
        api_base=credentials.get("api_base") or api_base or None,
        missing_credentials=missing if confirmed else (),
        credentials=tuple(sorted(credentials.items())),
        unverified_missing_credentials=() if confirmed else missing,
    )


register_extra_providers()

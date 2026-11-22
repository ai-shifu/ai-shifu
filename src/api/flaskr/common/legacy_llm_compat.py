"""Temporary compatibility for pre-LiteLLM model configuration.

Earlier AI-Shifu releases used their own environment variable names and model
id prefixes. This module translates them into LiteLLM's names so the rest of
the system only knows LiteLLM's rules. A LiteLLM-named setting always wins
over its legacy counterpart, and each translation logs one deprecation warning
naming the replacement.

To end the compatibility period, delete this module and its uses in
``flaskr/common/llm_routing.py``. Nothing else references it.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Container, Mapping

logger = logging.getLogger(__name__)

# LiteLLM variable -> the legacy AI-Shifu variable that used to mean the same.
LEGACY_ENV_NAMES: dict[str, str] = {
    "DASHSCOPE_API_KEY": "QWEN_API_KEY",
    "DASHSCOPE_API_BASE": "QWEN_API_URL",
    "VOLCENGINE_API_KEY": "ARK_API_KEY",
    "QIANFAN_API_KEY": "ERNIE_API_KEY",
    "SILICONFLOW_API_KEY": "SILICON_API_KEY",
    "SILICONFLOW_API_BASE": "SILICON_API_URL",
    "DEEPSEEK_API_BASE": "DEEPSEEK_API_URL",
    "GEMINI_API_BASE": "GEMINI_API_URL",
}

# LiteLLM provider -> (API key variable, API base variable) with a legacy name.
_PROVIDER_CREDENTIAL_ENVS: dict[str, tuple[str | None, str | None]] = {
    "dashscope": ("DASHSCOPE_API_KEY", "DASHSCOPE_API_BASE"),
    "volcengine": ("VOLCENGINE_API_KEY", None),
    "qianfan": ("QIANFAN_API_KEY", None),
    "siliconflow": ("SILICONFLOW_API_KEY", "SILICONFLOW_API_BASE"),
    "deepseek": (None, "DEEPSEEK_API_BASE"),
    "gemini": (None, "GEMINI_API_BASE"),
}

# Earlier releases ignored the public Gemini endpoint as a base so LiteLLM used
# its own default; a proxy on another host is still a base URL.
_IGNORED_LEGACY_HOSTS: dict[str, tuple[str, ...]] = {
    "GEMINI_API_URL": ("generativelanguage.googleapis.com",),
}

# Legacy model id prefix -> LiteLLM provider prefix.
LEGACY_MODEL_PREFIXES: dict[str, str] = {
    "qwen/": "dashscope/",
    "glm/": "bigmodel/",
    "ark/": "volcengine/",
    "ernie/": "qianfan/",
    "silicon/": "siliconflow/",
}

# Bare model names earlier releases routed by name. LiteLLM sends every bare
# ``gemini-*`` to Vertex AI, so those always gain the Gemini API prefix. Bare
# ``deepseek-*`` and ``gpt*`` names gain a prefix only when LiteLLM's model
# registry does not already know them.
ALWAYS_REWRITTEN_BARE_PREFIXES: dict[str, str] = {"gemini-": "gemini/"}
UNKNOWN_BARE_MODEL_PREFIXES: dict[str, str] = {
    "deepseek-": "deepseek/",
    "gpt": "openai/",
}

_warned: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key in _warned:
        return
    _warned.add(key)
    logger.warning(message)


def _value(environ: Mapping[str, str], name: str) -> str:
    return str(environ.get(name) or "").strip()


def legacy_env_value(
    litellm_name: str, environ: Mapping[str, str] | None = None
) -> str:
    """Return the legacy value standing in for an unset LiteLLM variable."""
    env = os.environ if environ is None else environ
    legacy = LEGACY_ENV_NAMES.get(litellm_name)
    if not legacy or _value(env, litellm_name):
        return ""
    value = _value(env, legacy)
    if not value or urlsplit(value).hostname in _IGNORED_LEGACY_HOSTS.get(legacy, ()):
        return ""
    _warn_once(f"env:{legacy}", f"{legacy} is deprecated; set {litellm_name} instead.")
    return value


def legacy_credentials(
    provider: str, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Return ``api_key``/``api_base`` that only legacy variables provide."""
    key_env, base_env = _PROVIDER_CREDENTIAL_ENVS.get(provider, (None, None))
    credentials = {}
    if key_env and (api_key := legacy_env_value(key_env, environ)):
        credentials["api_key"] = api_key
    if base_env and (api_base := legacy_env_value(base_env, environ)):
        credentials["api_base"] = api_base
    return credentials


def rewrite_model_id(model: str, known_bare_models: Container[str] = ()) -> str:
    """Return the LiteLLM model id for a legacy one; other ids are unchanged.

    ``known_bare_models`` is LiteLLM's model registry; bare names in it are
    already valid LiteLLM ids.
    """
    for legacy, litellm_prefix in LEGACY_MODEL_PREFIXES.items():
        if model.startswith(legacy) and len(model) > len(legacy):
            return _rewritten(model, litellm_prefix + model[len(legacy) :])
    if "/" in model:
        return model
    for legacy, litellm_prefix in ALWAYS_REWRITTEN_BARE_PREFIXES.items():
        if model.startswith(legacy):
            return _rewritten(model, litellm_prefix + model)
    if model in known_bare_models:
        return model
    for legacy, litellm_prefix in UNKNOWN_BARE_MODEL_PREFIXES.items():
        if model.startswith(legacy):
            return _rewritten(model, litellm_prefix + model)
    return model


def _rewritten(legacy: str, litellm_id: str) -> str:
    _warn_once(
        f"model:{legacy}",
        f"Model id {legacy!r} uses a deprecated form; use {litellm_id!r}.",
    )
    return litellm_id

"""Resolve LiteLLM request parameters for minimum thinking and provider gaps."""

from __future__ import annotations

import logging

import litellm

# Keep the package logger name so debug output is routed exactly as before.
logger = logging.getLogger(__package__)

_REASONING_EFFORT_CAPABILITIES = (
    ("none", "supports_none_reasoning_effort"),
    ("minimal", "supports_minimal_reasoning_effort"),
    ("low", "supports_low_reasoning_effort"),
)


_THINKING_CONTROL_KEYS = ("reasoning_effort", "thinking", "enable_thinking")


_LIST_PATCH_KEYS = frozenset({"allowed_openai_params", "additional_drop_params"})


_THINKING_CONFLICT_PATHS = (
    "reasoning_effort",
    "reasoning",
    "thinking",
    "enable_thinking",
    "thinkingConfig",
    "thinking_config",
    "extra_body.reasoning_effort",
    "extra_body.reasoning",
    "extra_body.thinking",
    "extra_body.enable_thinking",
    "extra_body.thinkingConfig",
    "extra_body.thinking_config",
    "generationConfig.thinkingConfig",
    "generationConfig.thinking_config",
    "generation_config.thinkingConfig",
    "generation_config.thinking_config",
    "extra_body.generationConfig.thinkingConfig",
    "extra_body.generationConfig.thinking_config",
    "extra_body.generation_config.thinkingConfig",
    "extra_body.generation_config.thinking_config",
)


# These entries cover confirmed gaps in LiteLLM 1.102.0. The normal path is
# capability-driven; upgrading LiteLLM should make individual rows removable
# when their contract tests start passing without the row.
_ZAI_DISABLED_THINKING_PATCH: dict[str, object] = {
    # LiteLLM 1.102 sends top-level thinking to the OpenAI SDK for ZAI, where it
    # is rejected. extra_body reaches the provider wire format.
    "extra_body": {"thinking": {"type": "disabled"}},
}


_LITELLM_1102_COMPATIBILITY_PATCHES: dict[tuple[str, str | None], dict[str, object]] = {
    ("qwen", None): {"extra_body": {"enable_thinking": False}},
    ("silicon", None): {"extra_body": {"enable_thinking": False}},
    ("ark", None): {"allowed_openai_params": ["response_format"]},
    ("glm", None): {"allowed_openai_params": ["response_format"]},
    ("glm", "glm-4.5"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5v"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5-air"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5-x"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5-airx"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.5-flash"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.6"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.7"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-4.7-flash"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-5"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-5.1"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-5-code"): _ZAI_DISABLED_THINKING_PATCH,
    ("glm", "glm-5.2"): _ZAI_DISABLED_THINKING_PATCH,
    ("qwen", "glm-5.3"): {
        "reasoning_effort": "low",
        "allowed_openai_params": ["reasoning_effort"],
    },
    ("qwen", "glm-5.3-flash"): {
        "reasoning_effort": "low",
        "allowed_openai_params": ["reasoning_effort"],
    },
    ("qwen", "zhipu/glm-5.3"): {
        "reasoning_effort": "low",
        "allowed_openai_params": ["reasoning_effort"],
    },
    ("qwen", "zhipu/glm-5.3-flash"): {
        "reasoning_effort": "low",
        "allowed_openai_params": ["reasoning_effort"],
    },
    ("gemini", "gemini-3.7-flash"): {"reasoning_effort": "low"},
    ("gemini", "gemini-3.8-flash"): {"reasoning_effort": "low"},
    ("gemini", "gemini-2.5-pro"): {"reasoning_effort": "minimal"},
    ("openai", "gpt-5-pro"): {"reasoning_effort": "high"},
    ("openai", "gpt-5-pro-2025-10-06"): {"reasoning_effort": "high"},
    ("openai", "gpt-5.2-pro"): {"reasoning_effort": "medium"},
    ("openai", "gpt-5.2-pro-2025-12-11"): {"reasoning_effort": "medium"},
    ("openai", "gpt-5.4-pro"): {"reasoning_effort": "medium"},
    ("openai", "gpt-5.4-pro-2026-03-05"): {"reasoning_effort": "medium"},
    ("openai", "gpt-6-astra"): {"reasoning_effort": "low"},
}


def _ordered_param_union(*values: object) -> list[object]:
    merged: list[object] = []
    for value in values:
        if not isinstance(value, (list, tuple)):
            continue
        for item in value:
            if item not in merged:
                merged.append(item)
    return merged


def _merge_litellm_param_patch(
    base: dict[str, object], patch: dict[str, object]
) -> dict[str, object]:
    """Shallow-merge one request patch without inventing a policy language."""
    merged = dict(base)
    for key, value in patch.items():
        if key in _LIST_PATCH_KEYS:
            merged[key] = _ordered_param_union(merged.get(key), value)
        elif key == "extra_body" and isinstance(value, dict):
            current = merged.get(key)
            merged[key] = {
                **(current if isinstance(current, dict) else {}),
                **value,
            }
        elif isinstance(value, dict):
            merged[key] = dict(value)
        elif isinstance(value, list):
            merged[key] = list(value)
        else:
            merged[key] = value
    return merged


def _litellm_minimum_thinking_params(
    model_id: str, custom_llm_provider: str
) -> dict[str, object]:
    """Use LiteLLM's declared adapter capabilities for the product minimum."""
    try:
        supported_params = litellm.get_supported_openai_params(
            model=model_id,
            custom_llm_provider=custom_llm_provider,
        )
    except Exception as exc:
        logger.debug(
            "LiteLLM supported params unavailable for %s/%s: %s",
            custom_llm_provider,
            model_id,
            exc,
        )
        supported_params = None

    if supported_params and "reasoning_effort" in supported_params:
        try:
            model_info = litellm.get_model_info(
                model=model_id,
                custom_llm_provider=custom_llm_provider,
            )
        except Exception as exc:
            logger.debug(
                "LiteLLM model info unavailable for %s/%s: %s",
                custom_llm_provider,
                model_id,
                exc,
            )
            model_info = {}

        for effort, capability in _REASONING_EFFORT_CAPABILITIES:
            if model_info.get(capability) is True:
                return {"reasoning_effort": effort}
        if all(
            model_info.get(capability) is False
            for _effort, capability in _REASONING_EFFORT_CAPABILITIES
        ):
            return {"reasoning_effort": "medium"}
        # The adapter supports the standard parameter but the model metadata is
        # incomplete. LiteLLM maps none to each provider's native minimum.
        return {"reasoning_effort": "none"}

    if supported_params and "thinking" in supported_params:
        return {"thinking": {"type": "disabled"}}
    return {}


def _find_thinking_control(
    params: dict[str, object],
) -> tuple[str, str] | None:
    for key in _THINKING_CONTROL_KEYS:
        if key in params:
            return "root", key
    extra_body = params.get("extra_body")
    if isinstance(extra_body, dict):
        for key in _THINKING_CONTROL_KEYS:
            if key in extra_body:
                return "extra_body", key
    return None


def _keep_primary_thinking_control(
    params: dict[str, object], primary: tuple[str, str] | None
) -> dict[str, object]:
    if primary is None:
        return params
    kept = dict(params)
    for key in _THINKING_CONTROL_KEYS:
        if primary != ("root", key):
            kept.pop(key, None)
    extra_body = kept.get("extra_body")
    if isinstance(extra_body, dict):
        kept_extra_body = dict(extra_body)
        for key in _THINKING_CONTROL_KEYS:
            if primary != ("extra_body", key):
                kept_extra_body.pop(key, None)
        if kept_extra_body:
            kept["extra_body"] = kept_extra_body
        else:
            kept.pop("extra_body", None)
    return kept


def _thinking_conflict_drop_params(primary: tuple[str, str]) -> list[object]:
    if primary[0] == "root":
        protected_paths = {primary[1]}
        if primary[1] == "thinking":
            # OpenAI-compatible adapters can map standard thinking into
            # extra_body, so dropping that path would remove the policy value.
            protected_paths.add("extra_body.thinking")
    else:
        # A flat drop also removes an extra_body field with the same name.
        protected_paths = {primary[1], f"extra_body.{primary[1]}"}
    return [path for path in _THINKING_CONFLICT_PATHS if path not in protected_paths]


def _drop_path_overlaps_primary(path: object, primary: tuple[str, str]) -> bool:
    if not isinstance(path, str):
        return False
    target_path = primary[1] if primary[0] == "root" else f"extra_body.{primary[1]}"
    protected_paths = {target_path}
    if primary == ("root", "thinking"):
        protected_paths.add("extra_body.thinking")
    if primary[0] == "extra_body":
        # LiteLLM also treats the flat field name as an extra_body filter.
        protected_paths.add(primary[1])
    return any(
        path == protected
        or path.startswith(f"{protected}.")
        or protected.startswith(f"{path}.")
        for protected in protected_paths
    )


def _should_inject_default_temperature(
    provider_key: str,
    model_id: str,
    primary: tuple[str, str] | None,
    policy_params: dict[str, object],
) -> bool:
    normalized_model = model_id.casefold()
    if provider_key == "gemini" and normalized_model.startswith("gemini-3"):
        return False
    return not (
        provider_key == "openai"
        and primary == ("root", "reasoning_effort")
        and policy_params.get("reasoning_effort") != "none"
    )

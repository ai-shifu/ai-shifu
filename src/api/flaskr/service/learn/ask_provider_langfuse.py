"""Langfuse helpers for external ask providers."""

from typing import Any, Generator, Iterable


SENSITIVE_PROVIDER_CONFIG_KEYS = {
    "ak",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "secret_key",
    "sk",
    "token",
}


def _is_sensitive_provider_config_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    if not normalized:
        return False
    if normalized in SENSITIVE_PROVIDER_CONFIG_KEYS:
        return True
    return normalized.endswith(("_key", "_secret", "_token", "_password"))


def sanitize_provider_config_for_langfuse(value: Any, key: str | None = None) -> Any:
    if key and _is_sensitive_provider_config_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): sanitize_provider_config_for_langfuse(
                child_value, key=str(child_key)
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [sanitize_provider_config_for_langfuse(item) for item in value]
    return value


def _build_provider_generation_input(
    *,
    user_query: str,
    messages: list[dict[str, Any]],
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "user_query": user_query,
        "messages": messages,
        "provider_config": sanitize_provider_config_for_langfuse(provider_config),
    }


def _build_provider_generation_metadata(
    *,
    provider_name: str,
    provider_config: dict[str, Any],
    error: Exception | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "provider": provider_name,
        "provider_mode": str(provider_config.get("mode") or ""),
        "provider_config": sanitize_provider_config_for_langfuse(provider_config),
        "status": "error" if error else "success",
    }
    if error is not None:
        metadata["error_type"] = type(error).__name__
        metadata["error_message"] = str(error)
    return metadata


def stream_provider_with_langfuse(
    *,
    provider_stream: Iterable[Any],
    span: Any,
    provider_name: str,
    generation_name: str,
    user_query: str,
    messages: list[dict[str, Any]],
    provider_config: dict[str, Any],
) -> Generator[Any, None, None]:
    generation_input = _build_provider_generation_input(
        user_query=user_query,
        messages=messages,
        provider_config=provider_config,
    )
    generation = None
    if span is not None:
        generation = span.generation(
            model=provider_name,
            input=generation_input,
            name=generation_name,
        )

    response_text = ""
    error: Exception | None = None
    try:
        for chunk in provider_stream:
            current_content = getattr(chunk, "content", "")
            if isinstance(current_content, str) and current_content:
                response_text += current_content
            yield chunk
    except Exception as exc:
        error = exc
        raise
    finally:
        if generation is not None:
            generation.end(
                input=generation_input,
                output=response_text,
                metadata=_build_provider_generation_metadata(
                    provider_name=provider_name,
                    provider_config=provider_config,
                    error=error,
                ),
            )

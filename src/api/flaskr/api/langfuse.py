import ast
import json
import uuid
from typing import Any

from flask import Flask, request
from langfuse import Langfuse

from flaskr.common.log import thread_local


class MockClient:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        def method(*args, **kwargs):
            return self

        return method


langfuse_client = MockClient()


def get_langfuse_client():
    return langfuse_client


def get_request_id() -> str:
    request_id = getattr(thread_local, "request_id", "") or ""
    if request_id:
        return request_id

    try:
        request_id = request.headers.get("X-Request-ID", "") or ""
    except RuntimeError:
        request_id = ""

    return request_id


def get_request_trace_id() -> str:
    return get_request_id() or uuid.uuid4().hex


def resolve_langfuse_trace_id(observation: Any, trace_id: str | None = None) -> str:
    return trace_id or getattr(observation, "trace_id", "") or get_request_trace_id()


def build_langfuse_observation_link(
    observation: Any, trace_id: str | None = None
) -> dict[str, str]:
    observation_link: dict[str, str] = {}
    resolved_trace_id = resolve_langfuse_trace_id(observation, trace_id)
    parent_observation_id = (
        getattr(observation, "id", "")
        or getattr(observation, "observation_id", "")
        or ""
    )
    if resolved_trace_id:
        observation_link["trace_id"] = resolved_trace_id
    if parent_observation_id:
        observation_link["parent_observation_id"] = parent_observation_id
    return observation_link


def init_langfuse(app: Flask):
    global langfuse_client
    app.logger.info("Initializing Langfuse client")
    if (
        app.config.get("LANGFUSE_PUBLIC_KEY")
        and app.config.get("LANGFUSE_SECRET_KEY")
        and app.config.get("LANGFUSE_HOST")
    ):
        langfuse_client = Langfuse(
            public_key=app.config["LANGFUSE_PUBLIC_KEY"],
            secret_key=app.config["LANGFUSE_SECRET_KEY"],
            host=app.config["LANGFUSE_HOST"],
        )
    else:
        app.logger.warning("Langfuse configuration not found, using MockLangfuse")
        langfuse_client = MockClient()


def _has_langfuse_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _looks_like_structured_text(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) < 2:
        return False
    return (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    )


def _parse_langfuse_text_value(value: str) -> Any:
    stripped = value.strip()
    if not _looks_like_structured_text(stripped):
        return value
    try:
        return json.loads(stripped)
    except Exception:
        pass
    try:
        return ast.literal_eval(stripped)
    except Exception:
        return value


def normalize_langfuse_input_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = _parse_langfuse_text_value(value)
        if parsed is value:
            return value if value.strip() else None
        return normalize_langfuse_input_value(parsed)
    if isinstance(value, dict):
        parts: list[str] = []
        for raw in value.values():
            values = raw if isinstance(raw, list) else [raw]
            for item in values:
                normalized = normalize_langfuse_output_value(item)
                if normalized:
                    parts.append(normalized)
        return ", ".join(parts) or None
    if isinstance(value, (list, tuple, set)):
        parts: list[str] = []
        for item in value:
            normalized = normalize_langfuse_output_value(item)
            if normalized:
                parts.append(normalized)
        return ", ".join(parts) or None
    text = str(value)
    return text if text.strip() else None


def normalize_langfuse_output_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = _parse_langfuse_text_value(value)
        if parsed is value:
            return value if value.strip() else None
        return normalize_langfuse_output_value(parsed)
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
            return text if text.strip() else None
    if isinstance(value, (list, tuple, set)):
        normalized_items = [
            normalize_langfuse_output_value(item)
            for item in (list(value) if not isinstance(value, list) else value)
        ]
        cleaned_items = [item for item in normalized_items if item]
        if not cleaned_items:
            return None
        try:
            return json.dumps(cleaned_items, ensure_ascii=False)
        except Exception:
            return "\n".join(cleaned_items)
    text = str(value)
    return text if text.strip() else None


def compact_langfuse_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    return {key: value for key, value in payload.items() if _has_langfuse_value(value)}


def create_trace_with_root_span(
    *,
    client: Any,
    trace_payload: dict[str, Any],
    root_span_payload: dict[str, Any],
):
    trace = client.trace(**compact_langfuse_payload(trace_payload))
    root_span = trace.span(**compact_langfuse_payload(root_span_payload))
    return trace, root_span


def update_langfuse_trace(trace: Any, payload: dict[str, Any] | None = None, **kwargs):
    update_payload = compact_langfuse_payload(payload or kwargs)
    if update_payload:
        trace.update(**update_payload)
    return trace


def update_langfuse_observation(
    observation: Any,
    payload: dict[str, Any] | None = None,
    **kwargs,
):
    update_payload = compact_langfuse_payload(payload or kwargs)
    if update_payload:
        observation.update(**update_payload)
    return observation


def finalize_langfuse_trace(
    *,
    trace: Any,
    root_span: Any | None,
    trace_payload: dict[str, Any] | None = None,
    root_span_payload: dict[str, Any] | None = None,
):
    if root_span is not None:
        root_span.end(**compact_langfuse_payload(root_span_payload))
    update_langfuse_trace(trace, payload=trace_payload)
    return trace

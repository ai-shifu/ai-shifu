"""Integrate Langfuse tracing and prompt retrieval."""

import ast
import contextlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from flask import Flask, request
from langfuse import Langfuse

from flaskr.common.log import thread_local

# Langfuse SDK v3 is OTel based: trace ids must be 32 lowercase hex chars and
# parent/child links are derived from the span object hierarchy instead of the
# explicit trace_id/parent_observation_id kwargs the v2 SDK accepted. The
# handle classes below keep the v2-style call surface (trace.span(),
# span.generation(), generation.end(output=...)) so call sites stay unchanged.

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_OBSERVATION_KEYS = {
    "name",
    "input",
    "output",
    "metadata",
    "version",
    "level",
    "status_message",
}
_GENERATION_KEYS = _OBSERVATION_KEYS | {
    "completion_start_time",
    "model",
    "model_parameters",
    "usage_details",
    "cost_details",
    "prompt",
}
_TRACE_KEYS = {
    "name",
    "user_id",
    "session_id",
    "version",
    "input",
    "output",
    "metadata",
    "tags",
    "public",
}
# v2-era link kwargs that no longer exist in SDK v3; parenthood is implicit.
_LINK_KEYS = {"trace_id", "parent_observation_id", "id"}


class MockClient:
    """Provide a no-op Langfuse client when tracing is disabled."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize the no-op Langfuse client."""

    def __getattr__(self, name) -> Any:
        """Return a no-op callable for any Langfuse operation."""

        def method(*args: object, **kwargs: object):
            _ = (args, kwargs)
            return self

        return method


@dataclass(slots=True)
class _LangfuseState:
    client: Any = field(default_factory=MockClient)


_langfuse_state = _LangfuseState()


def get_langfuse_client() -> object:
    """Return langfuse client."""
    return _langfuse_state.client


def get_request_id() -> str:
    """Return request ID."""
    request_id = getattr(thread_local, "request_id", "") or ""
    if request_id:
        return request_id

    try:
        request_id = request.headers.get("X-Request-ID", "") or ""
    except RuntimeError:
        request_id = ""

    return request_id


def coerce_langfuse_trace_id(raw: str | None = None) -> str:
    # SDK v3 only accepts W3C trace ids (32 lowercase hex). Non-conforming
    # request ids are mapped deterministically via create_trace_id(seed=...)
    # so the same request always lands on the same Langfuse trace.
    """Coerce langfuse trace ID."""
    if isinstance(raw, str) and _TRACE_ID_RE.match(raw):
        return raw
    if isinstance(raw, str) and raw:
        return Langfuse.create_trace_id(seed=raw)
    return Langfuse.create_trace_id()


def get_request_trace_id() -> str:
    """Return request trace ID."""
    return coerce_langfuse_trace_id(get_request_id() or uuid.uuid4().hex)


def resolve_langfuse_trace_id(observation: Any, trace_id: str | None = None) -> str:
    # Only accept real string trace ids. When Langfuse is disabled the client is
    # a MockClient whose __getattr__ returns a method object for any attribute
    # (including ``trace_id``); using that object as the trace id later breaks the
    # bill_usage insert ("Data too long for column 'trace_id'"), which rolls back
    # the whole request transaction and silently drops user profile writes.
    """Resolve langfuse trace ID."""
    if isinstance(trace_id, str) and trace_id:
        return trace_id
    observation_trace_id = getattr(observation, "trace_id", "")
    if isinstance(observation_trace_id, str) and observation_trace_id:
        return observation_trace_id
    return get_request_trace_id()


def build_langfuse_observation_link(
    observation: Any, trace_id: str | None = None
) -> dict[str, str]:
    # Kept for logging/correlation. The handle classes drop these keys before
    # calling into SDK v3, where the span hierarchy already encodes the link.
    """Build langfuse observation link."""
    observation_link: dict[str, str] = {}
    resolved_trace_id = resolve_langfuse_trace_id(observation, trace_id)
    parent_observation_id = (
        getattr(observation, "id", "")
        or getattr(observation, "observation_id", "")
        or ""
    )
    if resolved_trace_id:
        observation_link["trace_id"] = resolved_trace_id
    if isinstance(parent_observation_id, str) and parent_observation_id:
        observation_link["parent_observation_id"] = parent_observation_id
    return observation_link


PRELOAD_MASTER_ENV = "AI_SHIFU_PRELOAD_MASTER"


def init_langfuse(app: Flask) -> None:
    """Initialize langfuse."""
    if os.environ.get(PRELOAD_MASTER_ENV):
        # Running inside the gunicorn preload master. Creating a real client
        # here starts the Langfuse/OTel BatchProcessor worker thread in the
        # master and registers an os.register_at_fork hook; after fork every
        # worker restarts that orphaned processor's thread, whose gevent
        # threading bookkeeping then crashes the hub (KeyError on the stopped
        # Thread in AbstractLinkable._notify_links) and can interrupt
        # unrelated in-flight DB exchanges. post_fork clears the flag and
        # calls init_langfuse again to build the real client per worker.
        app.logger.info("Deferring Langfuse init out of the preload master")
        _langfuse_state.client = MockClient()
        return
    app.logger.info("Initializing Langfuse client")
    if (
        app.config.get("LANGFUSE_PUBLIC_KEY")
        and app.config.get("LANGFUSE_SECRET_KEY")
        and app.config.get("LANGFUSE_HOST")
    ):
        _langfuse_state.client = Langfuse(
            public_key=app.config["LANGFUSE_PUBLIC_KEY"],
            secret_key=app.config["LANGFUSE_SECRET_KEY"],
            host=app.config["LANGFUSE_HOST"],
        )
    else:
        app.logger.warning("Langfuse configuration not found, using MockLangfuse")
        _langfuse_state.client = MockClient()


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
    with contextlib.suppress(Exception):
        return json.loads(stripped)
    try:
        return ast.literal_eval(stripped)
    except Exception:
        return value


def normalize_langfuse_input_value(value: Any) -> str | None:
    """Normalize langfuse input value."""
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
    """Normalize langfuse output value."""
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
    """Compact langfuse payload."""
    if not payload:
        return {}
    return {key: value for key, value in payload.items() if _has_langfuse_value(value)}


def _usage_to_details(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        details = {
            key: int(usage[key])
            for key in ("input", "output", "total")
            if usage.get(key) is not None
        }
        return details or None
    details = {}
    for key in ("input", "output", "total"):
        value = getattr(usage, key, None)
        if value is not None:
            details[key] = int(value)
    return details or None


def _map_observation_kwargs(
    kwargs: dict[str, Any], allowed: set[str]
) -> dict[str, Any]:
    mapped = dict(kwargs)
    for key in _LINK_KEYS:
        mapped.pop(key, None)
    usage = mapped.pop("usage", None)
    if usage is not None and "usage_details" not in mapped:
        usage_details = _usage_to_details(usage)
        if usage_details:
            mapped["usage_details"] = usage_details
    return compact_langfuse_payload(
        {key: value for key, value in mapped.items() if key in allowed}
    )


class LangfuseObservationHandle:
    """v2-style facade over a Langfuse SDK v3 span or generation."""

    def __init__(self, delegate: Any, trace_id: str = "") -> None:
        """Wrap a Langfuse observation and its trace identity."""
        self._delegate = delegate
        delegate_trace_id = getattr(delegate, "trace_id", "")
        self.trace_id = trace_id or (
            delegate_trace_id if isinstance(delegate_trace_id, str) else ""
        )

    @property
    def id(self) -> str:
        """Return the underlying observation identifier."""
        delegate_id = getattr(self._delegate, "id", "")
        return delegate_id if isinstance(delegate_id, str) else ""

    def span(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Create a child span observation."""
        payload = _map_observation_kwargs(kwargs, _OBSERVATION_KEYS)
        payload.setdefault("name", "span")
        child = self._delegate.start_span(**payload)
        return LangfuseObservationHandle(child, self.trace_id)

    def generation(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Create a child generation observation."""
        payload = _map_observation_kwargs(kwargs, _GENERATION_KEYS)
        payload.setdefault("name", "generation")
        # start_generation() is deprecated in SDK v3; start_observation() is
        # the v4-compatible replacement.
        child = self._delegate.start_observation(as_type="generation", **payload)
        return LangfuseObservationHandle(child, self.trace_id)

    def event(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Create a child event observation."""
        payload = _map_observation_kwargs(kwargs, _OBSERVATION_KEYS)
        payload.setdefault("name", "event")
        child = self._delegate.create_event(**payload)
        return LangfuseObservationHandle(child, self.trace_id)

    def update(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Update the underlying Langfuse observation."""
        payload = _map_observation_kwargs(kwargs, _GENERATION_KEYS)
        if payload:
            self._delegate.update(**payload)
        return self

    def end(self, **kwargs: object) -> "LangfuseObservationHandle":
        # SDK v3 end() only accepts end_time; flush attribute updates first.
        """Finalize the underlying Langfuse observation."""
        end_time = kwargs.pop("end_time", None)
        payload = _map_observation_kwargs(kwargs, _GENERATION_KEYS)
        if payload:
            self._delegate.update(**payload)
        if end_time is not None:
            self._delegate.end(end_time=end_time)
        else:
            self._delegate.end()
        return self

    def update_trace(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Update the trace that owns this observation."""
        payload = _map_observation_kwargs(kwargs, _TRACE_KEYS)
        if payload:
            self._delegate.update_trace(**payload)
        return self


class LangfuseTraceHandle(LangfuseObservationHandle):
    """v2-style trace facade; trace attributes live on the root span in v3."""

    def update(self, **kwargs: object) -> "LangfuseTraceHandle":
        """Update the underlying Langfuse observation."""
        self.update_trace(**kwargs)
        return self


def create_trace_with_root_span(
    *,
    client: Any,
    trace_payload: dict[str, Any],
    root_span_payload: dict[str, Any],
) -> tuple[LangfuseTraceHandle, LangfuseObservationHandle]:
    """Create trace with root span."""
    trace_payload = compact_langfuse_payload(trace_payload)
    root_payload = _map_observation_kwargs(root_span_payload, _OBSERVATION_KEYS)
    raw_trace_id = trace_payload.pop("id", None)
    trace_id = coerce_langfuse_trace_id(
        raw_trace_id if isinstance(raw_trace_id, str) else None
    )
    root_payload.setdefault("name", trace_payload.get("name") or "trace")
    root_span = client.start_span(
        trace_context={"trace_id": trace_id},
        **root_payload,
    )
    trace = LangfuseTraceHandle(root_span, trace_id)
    trace.update(**trace_payload)
    return trace, LangfuseObservationHandle(root_span, trace_id)


def update_langfuse_trace(
    trace: Any,
    payload: dict[str, Any] | None = None,
    **kwargs: object,
) -> object:
    """Update langfuse trace."""
    update_payload = compact_langfuse_payload(payload or kwargs)
    if update_payload:
        trace.update(**update_payload)
    return trace


def update_langfuse_observation(
    observation: Any,
    payload: dict[str, Any] | None = None,
    **kwargs: object,
) -> object:
    """Update langfuse observation."""
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
) -> object:
    # Update trace attributes before ending the root span: in SDK v3 trace
    # attributes are written through the (still open) root span.
    """Finalize langfuse trace."""
    update_langfuse_trace(trace, payload=trace_payload)
    if root_span is not None:
        root_span.end(**compact_langfuse_payload(root_span_payload))
    return trace

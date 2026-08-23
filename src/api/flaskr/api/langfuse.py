"""Integrate Langfuse tracing and prompt retrieval."""

import ast
import contextlib
import json
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from flask import Flask, request
from langfuse import Langfuse, propagate_attributes
from opentelemetry import trace as otel_trace_api

from flaskr.common.log import thread_local

# The Langfuse SDK is OTel based: trace ids must be 32 lowercase hex chars and
# parent/child links are derived from the span object hierarchy instead of the
# explicit trace_id/parent_observation_id kwargs the v2 SDK accepted. SDK v4
# additionally drops trace-level records: correlating attributes (user_id,
# session_id, tags, ...) are replicated onto every observation through
# propagate_attributes(), and input/output belong to the root observation. The
# handle classes below keep the legacy call surface (trace.span(),
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
# Trace attributes that SDK v4 replicates onto every observation. "name" is
# accepted here and forwarded as propagate_attributes(trace_name=...).
_PROPAGATED_TRACE_KEYS = {
    "user_id",
    "session_id",
    "version",
    "tags",
    "metadata",
    "environment",
}
# Trace-level input/output is deprecated in v4; these land on the observation.
_TRACE_IO_KEYS = {"input", "output"}
_TRACE_KEYS = _PROPAGATED_TRACE_KEYS | _TRACE_IO_KEYS | {"name", "public"}
# v2-era link kwargs that no longer exist since SDK v3; parenthood is implicit.
_LINK_KEYS = {"trace_id", "parent_observation_id", "id"}


class MockClient:
    """Provide a no-op Langfuse client when tracing is disabled."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize the no-op Langfuse client."""

    def __getattr__(self, name: object) -> Any:
        """Return a no-op callable for any Langfuse operation."""

        def method(*args: object, **kwargs: object) -> object:
            _ = (args, kwargs)
            return self

        return method


@dataclass(slots=True)
class _LangfuseState:
    client: Any = field(default_factory=MockClient)


_langfuse_state = _LangfuseState()


def get_langfuse_client() -> object:
    """Return the configured Langfuse client."""
    return _langfuse_state.client


def get_request_id() -> str:
    """Return the current request identifier, if one is available."""
    request_id = getattr(thread_local, "request_id", "") or ""
    if request_id:
        return request_id

    try:
        request_id = request.headers.get("X-Request-ID", "") or ""
    except RuntimeError:
        request_id = ""

    return request_id


def coerce_langfuse_trace_id(raw: str | None = None) -> str:
    # The SDK only accepts W3C trace ids (32 lowercase hex). Non-conforming
    # request ids are mapped deterministically via create_trace_id(seed=...)
    # so the same request always lands on the same Langfuse trace.
    """Return a W3C-compatible trace identifier for an optional source value."""
    if isinstance(raw, str) and _TRACE_ID_RE.match(raw):
        return raw
    if isinstance(raw, str) and raw:
        return Langfuse.create_trace_id(seed=raw)
    return Langfuse.create_trace_id()


def get_request_trace_id() -> str:
    """Return the current request trace identifier or create one."""
    return coerce_langfuse_trace_id(get_request_id() or uuid.uuid4().hex)


def resolve_langfuse_trace_id(observation: Any, trace_id: str | None = None) -> str:
    # Only accept real string trace ids. When Langfuse is disabled the client is
    # a MockClient whose __getattr__ returns a method object for any attribute
    # (including ``trace_id``); using that object as the trace id later breaks the
    # bill_usage insert ("Data too long for column 'trace_id'"), which rolls back
    # the whole request transaction and silently drops user profile writes.
    """Resolve a usable trace identifier from explicit and observation values."""
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
    # calling into the SDK, where the span hierarchy already encodes the link.
    """Build correlation identifiers for a Langfuse observation."""
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
    """Initialize the process-local Langfuse client for a Flask application."""
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
    """Normalize a Langfuse input value into displayable text."""
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
    """Normalize a Langfuse output value into displayable text."""
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
    """Return a payload without values Langfuse should omit."""
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


def _map_trace_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    payload = dict(kwargs)
    for key in _LINK_KEYS:
        payload.pop(key, None)
    return compact_langfuse_payload(
        {key: value for key, value in payload.items() if key in _TRACE_KEYS}
    )


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


class TraceAttributePropagation:
    """Trace attributes that SDK v4 replicates onto every observation.

    v4 removed the mutable trace record, so ``user_id``, ``session_id``,
    ``tags``, ``version`` and ``metadata`` are carried by every observation of
    the trace. The attributes are collected here and applied through
    ``propagate_attributes()`` whenever an observation is created, plus
    retroactively on observations that already exist when an attribute is bound
    late (for example the session id, which is only known once the progress
    record is resolved).
    """

    def __init__(self) -> None:
        """Start with an empty set of trace attributes."""
        self._values: dict[str, Any] = {}

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of the trace attributes accumulated for propagation."""
        return dict(self._values)

    def merge(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Merge trace attributes and return the snapshot when it changed."""
        updated = dict(self._values)
        for raw_key, value in payload.items():
            key = "trace_name" if raw_key == "name" else raw_key
            if key != "trace_name" and key not in _PROPAGATED_TRACE_KEYS:
                continue
            if (
                key == "metadata"
                and isinstance(value, dict)
                and isinstance(updated.get(key), dict)
            ):
                updated[key] = {**updated[key], **value}
                continue
            updated[key] = value
        if updated == self._values:
            return {}
        self._values = updated
        return dict(updated)

    @contextmanager
    def scope(self, delegate: Any) -> Iterator[None]:
        """Propagate the collected attributes to observations started inside.

        Entering ``propagate_attributes()`` also writes the attributes on the
        active span, so ``delegate`` is activated first and propagation is
        skipped when it owns no OTel span (a MockClient handle while Langfuse is
        disabled). Otherwise the attributes would land on whatever ambient span
        the request carries, for example the HTTP server span that
        flaskr.common.observability exports to the OTLP endpoint.
        """
        values = self.snapshot()
        otel_span = getattr(delegate, "_otel_span", None)
        if not values or not isinstance(otel_span, otel_trace_api.Span):
            yield
            return
        with (
            otel_trace_api.use_span(otel_span, end_on_exit=False),
            propagate_attributes(**values),
        ):
            yield

    def apply_to(self, delegate: Any) -> None:
        """Set the current attributes on an already started observation."""
        with self.scope(delegate):
            pass


class LangfuseObservationHandle:
    """v2-style facade over a Langfuse SDK span or generation."""

    def __init__(
        self,
        delegate: Any,
        trace_id: str = "",
        propagation: TraceAttributePropagation | None = None,
    ) -> None:
        """Wrap a Langfuse observation and its trace identity."""
        self._delegate = delegate
        self._propagation = propagation or TraceAttributePropagation()
        delegate_trace_id = getattr(delegate, "trace_id", "")
        self.trace_id = trace_id or (
            delegate_trace_id if isinstance(delegate_trace_id, str) else ""
        )

    @property
    def id(self) -> str:
        """Return the delegated observation identifier when the SDK exposes one."""
        delegate_id = getattr(self._delegate, "id", "")
        return delegate_id if isinstance(delegate_id, str) else ""

    def _child(self, delegate: Any) -> "LangfuseObservationHandle":
        return LangfuseObservationHandle(delegate, self.trace_id, self._propagation)

    def span(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Start and wrap a child span while propagating trace attributes."""
        payload = _map_observation_kwargs(kwargs, _OBSERVATION_KEYS)
        payload.setdefault("name", "span")
        with self._propagation.scope(self._delegate):
            child = self._delegate.start_observation(as_type="span", **payload)
        return self._child(child)

    def generation(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Start and wrap a child generation observation."""
        payload = _map_observation_kwargs(kwargs, _GENERATION_KEYS)
        payload.setdefault("name", "generation")
        with self._propagation.scope(self._delegate):
            child = self._delegate.start_observation(as_type="generation", **payload)
        return self._child(child)

    def event(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Create an event observation beneath the current observation."""
        payload = _map_observation_kwargs(kwargs, _OBSERVATION_KEYS)
        payload.setdefault("name", "event")
        with self._propagation.scope(self._delegate):
            child = self._delegate.create_event(**payload)
        return self._child(child)

    def update(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Apply supported observation updates and return this handle."""
        payload = _map_observation_kwargs(kwargs, _GENERATION_KEYS)
        if payload:
            self._delegate.update(**payload)
        return self

    def end(self, **kwargs: object) -> "LangfuseObservationHandle":
        """Flush attribute updates and end the delegated observation."""
        # SDK end() only accepts end_time; flush attribute updates first.
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
        """Apply trace attributes to this observation and future descendants."""
        payload = _map_trace_kwargs(kwargs)
        if not payload:
            return self
        propagated = self._propagation.merge(payload)
        if propagated:
            self._propagation.apply_to(self._delegate)
        # v4 reads input/output from the observation, not from the trace.
        io_payload = {key: payload[key] for key in _TRACE_IO_KEYS if key in payload}
        if io_payload:
            self._delegate.update(**io_payload)
        if payload.get("public"):
            self._delegate.set_trace_as_public()
        return self


class LangfuseTraceHandle(LangfuseObservationHandle):
    """v2-style trace facade; trace attributes live on the observations in v4."""

    def update(self, **kwargs: object) -> "LangfuseTraceHandle":
        """Update propagated trace attributes and return this trace facade."""
        self.update_trace(**kwargs)
        return self


def create_trace_with_root_span(
    *,
    client: Any,
    trace_payload: dict[str, Any],
    root_span_payload: dict[str, Any],
) -> tuple[LangfuseTraceHandle, LangfuseObservationHandle]:
    """Create a trace facade and its root observation from caller payloads."""
    raw_trace_id = compact_langfuse_payload(trace_payload).get("id")
    trace_id = coerce_langfuse_trace_id(
        raw_trace_id if isinstance(raw_trace_id, str) else None
    )
    trace_attributes = _map_trace_kwargs(trace_payload)
    root_payload = _map_observation_kwargs(root_span_payload, _OBSERVATION_KEYS)
    root_payload.setdefault("name", trace_attributes.get("name") or "trace")
    # v4 reads input/output from the root observation, and propagated metadata
    # is coerced to short strings, so keep the full payload on the observation.
    for key in _TRACE_IO_KEYS | {"metadata"}:
        if key in trace_attributes:
            root_payload.setdefault(key, trace_attributes[key])

    root_span = client.start_observation(
        trace_context={"trace_id": trace_id},
        **root_payload,
    )
    # The attributes are written onto the root observation itself, so it must
    # exist before propagation starts.
    propagation = TraceAttributePropagation()
    propagation.merge(trace_attributes)
    propagation.apply_to(root_span)
    trace = LangfuseTraceHandle(root_span, trace_id, propagation)
    if trace_attributes.get("public"):
        root_span.set_trace_as_public()
    return trace, LangfuseObservationHandle(root_span, trace_id, propagation)


def update_langfuse_trace(
    trace: Any, payload: dict[str, Any] | None = None, **kwargs: object
) -> object:
    """Apply non-empty attributes to a Langfuse trace facade."""
    update_payload = compact_langfuse_payload(payload or kwargs)
    if update_payload:
        trace.update(**update_payload)
    return trace


def update_langfuse_observation(
    observation: Any,
    payload: dict[str, Any] | None = None,
    **kwargs: object,
) -> object:
    """Apply non-empty attributes to a Langfuse observation."""
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
    # Update trace attributes before ending the root span: the attributes are
    # written through the (still open) root span.
    """Apply final attributes and end the root observation when present."""
    update_langfuse_trace(trace, payload=trace_payload)
    if root_span is not None:
        root_span.end(**compact_langfuse_payload(root_span_payload))
    return trace

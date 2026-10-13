"""Measure active requests and SSE lifetimes without reading stream content."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Iterator

from flask import Response, g, request
from prometheus_client import Counter, Gauge, Histogram

HTTP_IN_PROGRESS = Gauge(
    "ai_shifu_http_in_progress",
    "Active application requests, including response bodies for SSE.",
    ("method", "path"),
    multiprocess_mode="livesum",
)
SSE_ACTIVE = Gauge(
    "ai_shifu_sse_active",
    "SSE responses whose body has not completed, closed, or failed.",
    ("method", "path"),
    multiprocess_mode="livesum",
)
SSE_OUTCOMES = Counter(
    "ai_shifu_sse_responses_total",
    "SSE response terminal outcomes; HTTP status remains the header status.",
    ("method", "path", "status", "outcome"),
)
SSE_DURATION = Histogram(
    "ai_shifu_sse_duration_seconds",
    "Time from request entry to SSE body completion, close, or error.",
    ("method", "path", "status", "outcome"),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600, 1800),
)
SSE_FIRST_CHUNK = Histogram(
    "ai_shifu_sse_first_chunk_seconds",
    "Time from request entry to the first nonempty SSE body chunk, not model token.",
    ("method", "path", "status"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)


def _safe(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except Exception:
        # Telemetry must never interrupt delivery or suppress business errors.
        return False
    else:
        return True


class _RequestLifetime:
    def __init__(self, method: str, path: str) -> None:
        self.labels = (method, path)
        self.started = time.perf_counter()
        self._lock = threading.Lock()
        self._finished = False
        self.active = _safe(lambda: HTTP_IN_PROGRESS.labels(*self.labels).inc())

    def finish(self) -> None:
        with self._lock:
            if self._finished:
                return
            self._finished = True
        if self.active:
            _safe(lambda: HTTP_IN_PROGRESS.labels(*self.labels).dec())


class _SSELifetime(Iterator[bytes | str]):
    def __init__(
        self, body: Iterable[bytes | str], lifetime: _RequestLifetime, status: int
    ) -> None:
        self._body = body
        self._iterator = iter(body)
        self._request = lifetime
        self._labels = (*lifetime.labels, str(status))
        self._active = _safe(lambda: SSE_ACTIVE.labels(*lifetime.labels).inc())
        self._lock = threading.Lock()
        self._finished = False
        self._closed = False
        self._first_chunk = False

    def __iter__(self) -> _SSELifetime:
        return self

    def __next__(self) -> bytes | str:
        try:
            chunk = next(self._iterator)
        except StopIteration:
            self._finish("completed")
            raise
        except GeneratorExit:
            self._finish("closed")
            raise
        except BaseException:
            self._finish("error")
            raise
        if chunk and not self._first_chunk:
            self._first_chunk = True
            _safe(
                lambda: SSE_FIRST_CHUNK.labels(*self._labels).observe(
                    max(0.0, time.perf_counter() - self._request.started)
                )
            )
        return chunk

    def _finish(self, outcome: str) -> None:
        with self._lock:
            if self._finished:
                return
            self._finished = True
        if self._active:
            _safe(lambda: SSE_ACTIVE.labels(*self._request.labels).dec())
        labels = (*self._labels, outcome)
        _safe(lambda: SSE_OUTCOMES.labels(*labels).inc())
        _safe(
            lambda: SSE_DURATION.labels(*labels).observe(
                max(0.0, time.perf_counter() - self._request.started)
            )
        )
        self._request.finish()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            close = getattr(self._body, "close", None)
            if close is not None:
                close()
        except BaseException:
            self._finish("error")
            raise
        finally:
            self._finish("closed")


def start_capacity_request(excluded_paths: set[str]) -> None:
    """Capture stable labels while Flask's request context is available."""
    if request.path in excluded_paths:
        return
    path = request.url_rule.rule if request.url_rule is not None else "<unmatched>"
    g._ai_shifu_capacity_request = _RequestLifetime(request.method, path)


def finalize_capacity_response(response: Response) -> None:
    """Keep SSE requests active until their unbuffered iterator terminates."""
    lifetime = getattr(g, "_ai_shifu_capacity_request", None)
    if lifetime is None:
        return
    if response.is_streamed and response.mimetype == "text/event-stream":
        response.response = _SSELifetime(
            response.response, lifetime, response.status_code
        )
        g._ai_shifu_capacity_streaming = True
    else:
        lifetime.finish()


def teardown_capacity_request() -> None:
    """Account for dispatch errors without closing a still-running SSE body."""
    lifetime = getattr(g, "_ai_shifu_capacity_request", None)
    if lifetime is not None and not getattr(g, "_ai_shifu_capacity_streaming", False):
        lifetime.finish()

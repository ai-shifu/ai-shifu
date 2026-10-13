"""Observe SSE completion and cancellation without changing body delivery."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from flask import Flask, Response
from flaskr.common import capacity_metrics as metrics
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> CollectorRegistry:
    result = CollectorRegistry()
    labels = ("method", "path")
    for name in ("HTTP_IN_PROGRESS", "SSE_ACTIVE"):
        monkeypatch.setattr(
            metrics, name, Gauge(name.lower(), "test", labels, registry=result)
        )
    monkeypatch.setattr(
        metrics,
        "SSE_OUTCOMES",
        Counter(
            "sse_outcomes", "test", (*labels, "status", "outcome"), registry=result
        ),
    )
    for name, dimensions in (
        ("SSE_DURATION", (*labels, "status", "outcome")),
        ("SSE_FIRST_CHUNK", (*labels, "status")),
    ):
        monkeypatch.setattr(
            metrics, name, Histogram(name.lower(), "test", dimensions, registry=result)
        )
    return result


def response_with_body(body: Iterator[bytes], status: int = 200) -> Response:
    app = Flask(__name__)
    # Only route matching is needed here; never echo a route parameter as HTML.
    app.add_url_rule(
        "/stream/<item_id>", view_func=lambda **_values: Response(status=204)
    )
    with app.test_request_context("/stream/private-id"):
        metrics.start_capacity_request(set())
        response = Response(body, status=status, mimetype="text/event-stream")
        metrics.finalize_capacity_response(response)
        metrics.teardown_capacity_request()
    return response


def value(registry: CollectorRegistry, name: str, **extra: str) -> float | None:
    return registry.get_sample_value(
        name, {"method": "GET", "path": "/stream/<item_id>", **extra}
    )


def test_sse_counts_full_lifetime_and_preserves_chunks_and_callbacks(
    registry: CollectorRegistry,
) -> None:
    events = []

    def body() -> Iterator[bytes]:
        events.append("started")
        yield b""
        yield b"data: one\n\n"
        events.append("resumed")
        yield b"data: two\n\n"

    response = response_with_body(body())
    callback = Mock()
    response.call_on_close(callback)
    assert events == []  # Wrapping does not prefetch the body.
    assert value(registry, "http_in_progress") == 1
    assert value(registry, "sse_active") == 1
    iterator = iter(response.response)
    assert next(iterator) == b""
    assert value(registry, "sse_first_chunk_count", status="200") is None
    assert next(iterator) == b"data: one\n\n"
    assert value(registry, "sse_first_chunk_count", status="200") == 1
    assert list(iterator) == [b"data: two\n\n"]
    assert events == ["started", "resumed"]
    assert value(registry, "http_in_progress") == 0
    assert value(registry, "sse_active") == 0
    assert value(registry, "sse_outcomes_total", status="200", outcome="completed") == 1
    assert value(registry, "sse_duration_count", status="200", outcome="completed") == 1
    response.close()
    response.response.close()
    callback.assert_called_once_with()
    assert value(registry, "sse_outcomes_total", status="200", outcome="closed") is None


@pytest.mark.parametrize("consume_first", [False, True])
def test_close_before_or_after_first_chunk_finishes_once(
    registry: CollectorRegistry, consume_first: bool
) -> None:
    close = Mock()

    class Body:
        def __iter__(self) -> "Body":
            return self

        def __next__(self) -> bytes:
            return b"data: still active\n\n"

        def close(self) -> None:
            close()

    response = response_with_body(Body())
    if consume_first:
        next(iter(response.response))
    response.response.close()
    response.response.close()
    response.close()
    close.assert_called_once_with()
    assert value(registry, "http_in_progress") == 0
    assert value(registry, "sse_active") == 0
    assert value(registry, "sse_outcomes_total", status="200", outcome="closed") == 1
    assert value(registry, "sse_first_chunk_count", status="200") == (
        1 if consume_first else None
    )


@pytest.mark.parametrize("failure", [ValueError("body failed"), GeneratorExit()])
def test_body_error_or_generator_exit_is_preserved_and_accounted_once(
    registry: CollectorRegistry, failure: BaseException
) -> None:
    def body() -> Iterator[bytes]:
        yield b"data: first\n\n"
        raise failure

    response = response_with_body(body())
    iterator = iter(response.response)
    assert next(iterator) == b"data: first\n\n"
    with pytest.raises(type(failure)) as raised:
        next(iterator)
    assert raised.value is failure
    response.close()
    outcome = "closed" if isinstance(failure, GeneratorExit) else "error"
    assert value(registry, "sse_outcomes_total", status="200", outcome=outcome) == 1
    assert value(registry, "sse_active") == 0
    assert value(registry, "http_in_progress") == 0


@pytest.mark.usefixtures("registry")
def test_telemetry_errors_do_not_change_stream_or_its_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = Mock()
    broken.labels.side_effect = RuntimeError("metrics failed")
    for name in (
        "HTTP_IN_PROGRESS",
        "SSE_ACTIVE",
        "SSE_OUTCOMES",
        "SSE_DURATION",
        "SSE_FIRST_CHUNK",
    ):
        monkeypatch.setattr(metrics, name, broken)
    failure = ValueError("business error")

    def body() -> Iterator[bytes]:
        yield b"unchanged"
        raise failure

    response = response_with_body(body())
    assert next(iter(response.response)) == b"unchanged"
    with pytest.raises(ValueError, match="business error") as raised:
        next(iter(response.response))
    assert raised.value is failure
    response.close()


def test_probe_exclusion_unmatched_labels_and_dispatch_error(
    registry: CollectorRegistry,
) -> None:
    app = Flask(__name__)
    with app.test_request_context("/internal/metrics"):
        metrics.start_capacity_request({"/internal/metrics"})
        metrics.finalize_capacity_response(Response("metrics"))
        metrics.teardown_capacity_request()
    assert not any(family.samples for family in registry.collect())
    with app.test_request_context("/unknown-private-identity"):
        metrics.start_capacity_request(set())
        assert (
            registry.get_sample_value(
                "http_in_progress", {"method": "GET", "path": "<unmatched>"}
            )
            == 1
        )
        metrics.teardown_capacity_request()
        metrics.teardown_capacity_request()
    assert (
        registry.get_sample_value(
            "http_in_progress", {"method": "GET", "path": "<unmatched>"}
        )
        == 0
    )
    assert "unknown-private-identity" not in str(list(registry.collect()))


def test_non_sse_streams_are_not_wrapped(registry: CollectorRegistry) -> None:
    app = Flask(__name__)
    body = iter([b"download"])
    with app.test_request_context("/download"):
        metrics.start_capacity_request(set())
        response = Response(
            body, mimetype="application/octet-stream", direct_passthrough=True
        )
        metrics.finalize_capacity_response(response)
        assert response.response is body
        metrics.teardown_capacity_request()
    assert (
        registry.get_sample_value(
            "http_in_progress", {"method": "GET", "path": "<unmatched>"}
        )
        == 0
    )


def test_original_close_exception_remains_visible_and_counts_error(
    registry: CollectorRegistry,
) -> None:
    failure = ValueError("cleanup failed")

    class Body:
        def __iter__(self) -> "Body":
            return self

        def __next__(self) -> bytes:
            return b"data: active\n\n"

        def close(self) -> None:
            raise failure

    response = response_with_body(Body())
    with pytest.raises(ValueError, match="cleanup failed") as raised:
        response.close()
    assert raised.value is failure
    response.response.close()
    assert value(registry, "sse_outcomes_total", status="200", outcome="error") == 1
    assert value(registry, "http_in_progress") == 0
    assert value(registry, "sse_active") == 0


def test_flask_stream_context_and_response_close_hooks_finish_accounting(
    registry: CollectorRegistry,
) -> None:
    from flask import request, stream_with_context
    from flaskr.common.observability import init_observability

    app = Flask(__name__)
    init_observability(app)
    closed = Mock()

    @app.get("/stream/<item_id>")
    def stream(item_id: str) -> Response:
        @stream_with_context
        def body() -> Iterator[bytes]:
            assert request.view_args["item_id"] == item_id
            yield b"data: first\n\n"
            yield b"data: second\n\n"

        response = Response(body(), mimetype="text/event-stream")
        response.call_on_close(closed)
        return response

    response = app.test_client().get("/stream/private-id", buffered=False)
    assert value(registry, "http_in_progress") == 1
    assert value(registry, "sse_active") == 1
    response.close()
    closed.assert_called_once_with()
    assert value(registry, "http_in_progress") == 0
    assert value(registry, "sse_active") == 0
    assert value(registry, "sse_outcomes_total", status="200", outcome="closed") == 1

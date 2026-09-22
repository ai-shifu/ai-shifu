"""Verify request spans, metrics and failure-tolerant instrumentation."""

import threading
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.common import observability
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest


@pytest.fixture(autouse=True)
def isolated_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = CollectorRegistry()
    labels = ("method", "path", "status")
    monkeypatch.setattr(observability, "thread_local", threading.local())
    monkeypatch.setattr(
        observability,
        "HTTP_REQUEST_COUNT",
        Counter(
            "ai_shifu_http_requests_total",
            "Test request count",
            labels,
            registry=registry,
        ),
    )
    monkeypatch.setattr(
        observability,
        "HTTP_REQUEST_DURATION",
        Histogram(
            "ai_shifu_http_request_duration_seconds",
            "Test request duration",
            labels,
            registry=registry,
        ),
    )
    monkeypatch.setattr(
        observability, "generate_latest", lambda: generate_latest(registry)
    )


@pytest.fixture
def traced_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    install = Mock()
    monkeypatch.setattr(observability, "TracerProvider", Mock(return_value=provider))
    monkeypatch.setattr(observability.trace, "set_tracer_provider", install)
    monkeypatch.setattr(observability.trace, "get_tracer", provider.get_tracer)
    app = Flask(__name__)
    app.config.update(OBSERVABILITY_TRACES_ENABLED="yes", OTEL_TRACE_SAMPLE_RATE="bad")
    observability.init_observability(app)
    yield SimpleNamespace(
        app=app, exporter=exporter, provider=provider, install=install
    )
    provider.shutdown()


@pytest.mark.parametrize("status", [200, 404, 503])
def test_request_span_has_status_timing_and_identity_and_detaches_context(
    traced_app: SimpleNamespace,
    status: int,
) -> None:
    app = traced_app.app

    @app.get("/items/<item_id>")
    def item(item_id: str) -> tuple[dict, int]:
        assert item_id == "abc"
        trace_id, span_id = observability.current_trace_ids()
        assert len(trace_id) == 32
        assert len(span_id) == 16
        return {"ok": status == 200}, status

    response = app.test_client().get(
        "/items/abc", headers={"X-Request-ID": "request-id"}
    )
    assert response.status_code == status
    spans = traced_app.exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "GET /items/abc"
    assert span.attributes["http.request_id"] == "request-id"
    assert span.attributes["http.status_code"] == status
    assert span.attributes["http.response_content_type"] == "application/json"
    assert span.attributes["http.duration_ms"] >= 0
    assert span.status.status_code == (
        StatusCode.UNSET if status == 200 else StatusCode.ERROR
    )
    assert observability.current_trace_ids() == ("-", "-")
    assert app.extensions["ai_shifu_trace_sample_rate"] == 1.0


def test_instrumentation_initialization_is_idempotent(
    traced_app: SimpleNamespace,
) -> None:
    app = traced_app.app
    before = len(app.before_request_funcs[None])
    assert observability.init_observability(app) is app
    assert len(app.before_request_funcs[None]) == before
    traced_app.install.assert_called_once()


def test_export_endpoint_is_normalized_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, exporter, processor = Mock(), Mock(), Mock()
    monkeypatch.setattr(observability, "TracerProvider", Mock(return_value=provider))
    exporter_factory = Mock(return_value=exporter)
    processor_factory = Mock(return_value=processor)
    monkeypatch.setattr(observability, "OTLPSpanExporter", exporter_factory)
    monkeypatch.setattr(observability, "BatchSpanProcessor", processor_factory)
    monkeypatch.setattr(observability.trace, "set_tracer_provider", Mock())
    app = Flask(__name__)
    app.config.update(
        OBSERVABILITY_TRACES_ENABLED=True,
        OTEL_EXPORTER_OTLP_ENDPOINT=" https://trace.example.test/// ",
    )
    observability.init_observability(app)
    exporter_factory.assert_called_once_with(
        endpoint="https://trace.example.test/v1/traces"
    )
    processor_factory.assert_called_once_with(exporter)
    provider.add_span_processor.assert_called_once_with(processor)


def test_teardown_records_unhandled_exception_on_active_span(
    traced_app: SimpleNamespace,
) -> None:
    app = traced_app.app
    error = RuntimeError("request operation failed")
    with app.test_request_context("/broken"):
        app.preprocess_request()
        app.teardown_request_funcs[None][-1](error)
        response = app.response_class(status=500)
        app.process_response(response)
    span = traced_app.exporter.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR
    assert any(event.name == "exception" for event in span.events)
    assert span.events[0].attributes["exception.message"] == str(error)


def test_metrics_and_health_are_available_without_tracing() -> None:
    app = Flask(__name__)
    app.config.update(
        INTERNAL_METRICS_PATH="/private/metrics",
        INTERNAL_OBSERVABILITY_HEALTH_PATH="/private/health",
    )
    observability.init_observability(app)
    client = app.test_client()
    response = client.get("/private/metrics")
    assert response.status_code == 200
    assert b"ai_shifu_http_requests_total" in response.data
    health = client.get("/private/health").get_json()
    assert health == {
        "ok": True,
        "traces_enabled": False,
        "metrics_path": "/private/metrics",
        "otlp_endpoint": "",
        "request_id_header": "X-Request-ID",
    }


@pytest.mark.parametrize("count", [None, -1, 3, "bad"])
def test_notification_metric_is_best_effort_and_never_increments_negative(
    monkeypatch: pytest.MonkeyPatch,
    count: object,
) -> None:
    counter = Mock()
    monkeypatch.setattr(observability, "CREDIT_NOTIFICATION_EVENTS", counter)
    observability.record_credit_notification_event("", count=count)
    counter.labels.assert_called_once_with("unknown", "unknown", "unknown", "unknown")
    if count == "bad":
        counter.labels.return_value.inc.assert_not_called()
    else:
        counter.labels.return_value.inc.assert_called_once_with(max(0, count or 0))
    counter.labels.side_effect = RuntimeError("metrics unavailable")
    observability.record_credit_notification_event("delivery")


def test_metrics_without_start_timestamp_use_zero_duration_and_unmatched_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(observability.thread_local, "request_started_at", raising=False)
    counts, durations = Mock(), Mock()
    monkeypatch.setattr(observability, "HTTP_REQUEST_COUNT", counts)
    monkeypatch.setattr(observability, "HTTP_REQUEST_DURATION", durations)
    with Flask(__name__).test_request_context("/unknown"):
        assert observability._record_request_metrics(404) == 0
    counts.labels.assert_called_once_with("GET", "/unknown", "404")
    durations.labels.return_value.observe.assert_called_once_with(0)


def test_absent_or_invalid_span_has_no_trace_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = Mock(return_value=None)
    monkeypatch.setattr(observability.trace, "get_current_span", current)
    assert observability.current_trace_ids() == ("-", "-")
    current.return_value = SimpleNamespace(
        get_span_context=lambda: SimpleNamespace(is_valid=False)
    )
    assert observability.set_thread_local_trace_ids() == ("-", "-")

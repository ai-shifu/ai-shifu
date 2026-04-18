from __future__ import annotations

import time

from flask import Flask, Response, g, jsonify, request
from opentelemetry import context, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .request_context import thread_local


HTTP_REQUEST_COUNT = Counter(
    "ai_shifu_http_requests_total",
    "Total HTTP requests handled by the backend.",
    ("method", "path", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "ai_shifu_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "path", "status"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)


def _bool_config(app: Flask, key: str, default: bool = False) -> bool:
    value = app.config.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _float_config(app: Flask, key: str, default: float) -> float:
    try:
        return float(app.config.get(key, default))
    except (TypeError, ValueError):
        return default


def init_observability(app: Flask) -> Flask:
    if getattr(app, "_ai_shifu_observability_initialized", False):
        return app

    metrics_path = app.config.get("INTERNAL_METRICS_PATH", "/internal/metrics")
    health_path = app.config.get(
        "INTERNAL_OBSERVABILITY_HEALTH_PATH", "/internal/observability/health"
    )
    traces_enabled = _bool_config(app, "OBSERVABILITY_TRACES_ENABLED", False)
    sample_rate = _float_config(app, "OTEL_TRACE_SAMPLE_RATE", 1.0)

    if traces_enabled:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": app.config.get("OTEL_SERVICE_NAME", "ai-shifu-api"),
                    "service.version": app.config.get("VERSION", "dev"),
                    "deployment.environment": app.config.get("ENV", "development"),
                }
            )
        )
        endpoint = str(app.config.get("OTEL_EXPORTER_OTLP_ENDPOINT", "") or "").strip()
        if endpoint:
            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")
                )
            )
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer("ai_shifu.http")
        app.extensions["ai_shifu_tracer"] = tracer
        app.extensions["ai_shifu_trace_sample_rate"] = sample_rate
    else:
        tracer = None

    @app.before_request
    def _start_request_observability():
        request_id = request.headers.get("X-Request-ID", "") or getattr(
            thread_local, "request_id", ""
        )
        thread_local.request_started_at = time.perf_counter()
        thread_local.status_code = "-"
        thread_local.duration_ms = "-"
        if tracer is None:
            thread_local.trace_id = "-"
            thread_local.span_id = "-"
            return

        span = tracer.start_span(
            f"{request.method} {request.path}",
            kind=SpanKind.SERVER,
            attributes={
                "http.method": request.method,
                "http.target": request.path,
                "http.scheme": request.scheme,
                "http.user_agent": request.user_agent.string or "",
                "http.request_id": request_id,
                "ai_shifu.request_id": request_id,
            },
        )
        token = context.attach(trace.set_span_in_context(span))
        g._ai_shifu_observability_span = span
        g._ai_shifu_observability_token = token
        set_thread_local_trace_ids()

    @app.after_request
    def _finalize_request_observability(response):
        duration_ms = _record_request_metrics(response.status_code)
        span = getattr(g, "_ai_shifu_observability_span", None)
        if span is not None:
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute(
                "http.response_content_type", response.content_type or ""
            )
            span.set_attribute("http.duration_ms", duration_ms)
            span.set_attribute("ai_shifu.duration_ms", duration_ms)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            elif response.status_code >= 400:
                span.set_status(Status(StatusCode.ERROR, "client_error"))
            span.end()
        token = getattr(g, "_ai_shifu_observability_token", None)
        if token is not None:
            context.detach(token)
        set_thread_local_trace_ids()
        return response

    @app.teardown_request
    def _teardown_request_observability(error: Exception | None):
        if error is None:
            return
        span = getattr(g, "_ai_shifu_observability_span", None)
        if span is not None:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, str(error)))

    @app.route(metrics_path, methods=["GET"])
    def metrics_handler():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.route(health_path, methods=["GET"])
    def observability_health_handler():
        return jsonify(
            {
                "ok": True,
                "traces_enabled": traces_enabled,
                "metrics_path": metrics_path,
                "otlp_endpoint": app.config.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
                "request_id_header": "X-Request-ID",
            }
        )

    app._ai_shifu_observability_initialized = True
    return app


def _request_path_label() -> str:
    if request.url_rule is not None and request.url_rule.rule:
        return request.url_rule.rule
    return request.path


def _record_request_metrics(status_code: int) -> float:
    started_at = getattr(thread_local, "request_started_at", None)
    duration_seconds = 0.0
    if started_at is not None:
        duration_seconds = max(time.perf_counter() - started_at, 0.0)
    duration_ms = round(duration_seconds * 1000, 3)
    path_label = _request_path_label()
    status_label = str(status_code)
    HTTP_REQUEST_COUNT.labels(request.method, path_label, status_label).inc()
    HTTP_REQUEST_DURATION.labels(request.method, path_label, status_label).observe(
        duration_seconds
    )
    thread_local.status_code = status_label
    thread_local.duration_ms = str(duration_ms)
    return duration_ms


def current_trace_ids() -> tuple[str, str]:
    span = trace.get_current_span()
    if span is None:
        return "-", "-"
    context_obj = span.get_span_context()
    if not context_obj.is_valid:
        return "-", "-"
    return format(context_obj.trace_id, "032x"), format(context_obj.span_id, "016x")


def set_thread_local_trace_ids() -> tuple[str, str]:
    trace_id, span_id = current_trace_ids()
    thread_local.trace_id = trace_id
    thread_local.span_id = span_id
    return trace_id, span_id

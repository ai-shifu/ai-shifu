"""Verify request logging remains observational across HTTP body types."""

import io
import logging
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, Response
from flaskr.common import config, log


@pytest.fixture
def logged_app(tmp_path: object, monkeypatch: object) -> object:
    monkeypatch.setattr(log, "thread_local", threading.local())
    monkeypatch.setattr(config, "get_config", lambda _key, default=None: default or "")
    app = Flask(f"request-logging-{uuid.uuid4().hex}")
    path = tmp_path / "nested" / "request.log"
    app.config["LOGGING_PATH"] = str(path)
    log.init_log(app)

    @app.route("/echo", methods=["GET", "POST"])
    def echo() -> Response:
        return Response("business response", status=201)

    @app.get("/events")
    def events() -> Response:
        return Response(iter(["data: event\n\n"]), mimetype="text/event-stream")

    @app.get("/download")
    def download() -> Response:
        return Response(iter([b"binary payload"]), direct_passthrough=True)

    yield SimpleNamespace(app=app, path=path, client=app.test_client())
    for handler in app.logger.handlers:
        handler.close()
    app.logger.handlers = []


@pytest.mark.parametrize("body_type", ["file", "form", "args", "raw", "json"])
def test_request_body_types_are_logged_without_changing_response(
    logged_app: object, body_type: str
) -> None:
    kwargs = {}
    url = "/echo"
    if body_type == "file":
        kwargs = {
            "data": {"file": (io.BytesIO(b"unlogged file contents"), "upload.txt")}
        }
        marker = "File Upload"
    elif body_type == "form":
        kwargs = {"data": {"field": "form value"}}
        marker = "Form"
    elif body_type == "args":
        url += "?field=query-value"
        marker = "Args"
    elif body_type == "raw":
        kwargs = {"data": "raw value", "content_type": "text/plain"}
        marker = "Raw"
    else:
        kwargs = {"json": {"field": "json value"}}
        marker = "JSON"
    response = logged_app.client.post(url, **kwargs)
    assert response.status_code == 201
    assert response.get_data(as_text=True) == "business response"
    text = logged_app.path.read_text()
    assert f"'{marker}'" in text
    assert "unlogged file contents" not in text


def test_streaming_response_logging_does_not_consume_payload_and_logs_close(
    logged_app: object,
) -> None:
    response = logged_app.client.get("/events", buffered=False)
    assert next(response.response) == b"data: event\n\n"
    response.close()
    download = logged_app.client.get("/download", buffered=False)
    assert next(download.response) == b"binary payload"
    download.close()
    text = logged_app.path.read_text()
    assert "<SSE streaming response>" in text
    assert "<streaming ended>" in text
    assert "<streaming response omitted>" in text
    assert "binary payload" not in text


def test_request_body_read_failure_does_not_prevent_business_handler(
    logged_app: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(
        logged_app.app.request_class,
        "get_data",
        Mock(side_effect=OSError("body unavailable")),
    )
    response = logged_app.client.post("/echo", data="test", content_type="text/plain")
    assert response.status_code == 201
    assert response.get_data(as_text=True) == "business response"
    assert "Failed to get request body" in logged_app.path.read_text()


def test_response_logging_failure_returns_the_original_response(
    logged_app: object,
) -> None:
    class UnreadableResponse(Response):
        def get_data(self, as_text: bool = False) -> object:
            _ = as_text
            message = "response unavailable for logging"
            raise RuntimeError(message)

    @logged_app.app.get("/unreadable")
    def unreadable() -> Response:
        return UnreadableResponse("still delivered", status=202)

    response = logged_app.client.get("/unreadable")
    assert response.status_code == 202
    assert response.get_data(as_text=True) == "still delivered"
    assert "Error logging response" in logged_app.path.read_text()


def test_formatter_uses_fallback_fields_when_context_resolution_raises(
    monkeypatch: object,
) -> None:
    class BrokenContext:
        def __getattr__(self, _name: str) -> object:
            message = "context gone"
            raise RuntimeError(message)

    monkeypatch.setattr(log, "thread_local", BrokenContext())
    formatter = log.RequestFormatter(
        "%(url)s %(request_id)s %(client_ip)s %(trace_id)s %(span_id)s %(status_code)s %(duration_ms)s %(message)s"
    )
    record = logging.makeLogRecord({"msg": "original"})
    assert (
        formatter.format(record) == "No_URL No_Request_ID No_Client_IP - - - - original"
    )


def test_formatter_date_format_and_existing_duration_remain_stable(
    monkeypatch: object,
) -> None:
    formatter = log.RequestFormatter()
    record = logging.makeLogRecord({"created": 0})
    assert formatter.formatTime(record, "%Y-%m-%d %H:%M:%S") == "1970-01-01 08:00:00"
    context = SimpleNamespace(duration_ms="12.5", request_started_at=0)
    monkeypatch.setattr(log, "thread_local", context)
    log._update_request_timing(204)
    assert context.duration_ms == "12.5"
    assert context.status_code == "204"


def test_unexpected_webhook_format_failure_resets_delivery_guard(
    monkeypatch: object,
) -> None:
    handler = log.FeishuLogHandler("https://example.invalid/test-webhook")
    formatter = Mock(format=Mock(side_effect=ValueError("format failed")))
    handler.setFormatter(formatter)
    handler.handleError = Mock()
    post = Mock(return_value=Mock())
    monkeypatch.setattr(log.requests, "post", post)
    record = logging.makeLogRecord({"msg": "failure"})
    handler.emit(record)
    handler.handleError.assert_called_once_with(record)
    post.assert_not_called()
    assert handler._delivering.active is False
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(record)
    post.assert_called_once()
    assert handler._delivering.active is False


@pytest.mark.parametrize("existing_handler", [True, False])
def test_gunicorn_logger_configuration_and_webhook_setup_are_isolated(
    tmp_path: object, monkeypatch: object, existing_handler: bool
) -> None:
    gunicorn_logger = logging.getLogger("gunicorn.info")
    inherited = logging.NullHandler()
    monkeypatch.setattr(
        gunicorn_logger, "handlers", [inherited] if existing_handler else []
    )
    monkeypatch.setattr(
        config,
        "get_config",
        lambda key, default=None: {
            "SERVER_SOFTWARE": "gunicorn/23",
            "FEISHU_LOG_WEBHOOK_URL": "https://example.invalid/webhook",
        }.get(key, default),
    )
    post = Mock()
    monkeypatch.setattr(log.requests, "post", post)
    app = Flask(f"gunicorn-log-{uuid.uuid4().hex}")
    app.config["LOGGING_PATH"] = str(tmp_path / "gunicorn.log")
    try:
        assert log.init_log(app) is app
        assert (inherited in app.logger.handlers) is existing_handler
        assert any(
            isinstance(handler, log.FeishuLogHandler) for handler in app.logger.handlers
        )
        assert app.logger.level == logging.INFO
        assert app.logger.propagate is False
        post.assert_not_called()
    finally:
        for handler in app.logger.handlers:
            handler.close()
        app.logger.handlers = []

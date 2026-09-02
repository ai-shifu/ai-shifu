"""Focused security and protocol contracts for Gemini Live routes."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flask import Flask, request
from flaskr.route.common import by_pass_login_func
from flaskr.service.common.models import AppError
from flaskr.service.learn import live_follow_up_routes as routes
from flaskr.service.learn import live_follow_up_security as security
from flaskr.service.learn.gemini_live_provider import GeminiLiveServerEvent
from flaskr.service.learn.live_follow_up_capacity import LiveFollowUpCapacityLease
from flaskr.service.learn.live_follow_up_security import (
    LIVE_FOLLOW_UP_TICKET_COOKIE_NAME,
    IssuedLiveFollowUpTicket,
    LiveFollowUpTicketBinding,
)

if TYPE_CHECKING:
    from typing import ClassVar


class _FakeSock:
    """Capture Flask-Sock handlers without starting a WebSocket server."""

    def __init__(self, app: Flask) -> None:
        self._app = app

    def route(self, path: str) -> object:
        def decorator(func: object) -> object:
            handlers = self._app.extensions.setdefault("test_live_sock", {})
            handlers[path] = func
            return func

        return decorator


class _CaptureWebSocket:
    """Capture outbound frames and replay deterministic browser input."""

    def __init__(self, incoming: list[object] | None = None) -> None:
        self.incoming = deque(incoming or [])
        self.sent: list[str | bytes] = []
        self.connected = True

    def send(self, payload: str | bytes) -> None:
        self.sent.append(payload)

    def receive(self, *, timeout: float) -> object:
        _ = timeout
        if self.incoming:
            return self.incoming.popleft()
        self.connected = False
        return None


class _BlockingProvider:
    """Keep the reader thread blocked while the browser loop is exercised."""

    instances: ClassVar[list[_BlockingProvider]] = []

    def __init__(self, **_kwargs: object) -> None:
        self.audio_frames: list[bytes] = []
        self._closed = threading.Event()
        self.instances.append(self)

    def connect(self) -> None:
        return None

    def receive(self) -> object:
        self._closed.wait(timeout=2)
        message = "closed"
        raise routes.GeminiLiveConnectionError(message)

    def send_audio(self, frame: bytes) -> None:
        self.audio_frames.append(frame)

    def send_audio_stream_end(self) -> None:
        return None

    def close(self) -> None:
        self._closed.set()


class _FakeTrace:
    """Avoid external tracing while retaining the route's trace contract."""

    trace_id = "trace-1"

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        return None

    def close(self, *, end_reason: str) -> None:
        _ = end_reason


def _binding(**overrides: object) -> LiveFollowUpTicketBinding:
    values: dict[str, object] = {
        "session_bid": "session-1",
        "user_bid": "user-1",
        "shifu_bid": "course-1",
        "outline_bid": "chapter-1",
        "anchor_element_bid": "element-1",
        "progress_record_bid": "progress-1",
        "preview_mode": False,
        "origin": "https://learn.example.com",
        "model": routes.GEMINI_LIVE_MODEL_ID,
        "voice_name": "Kore",
        "language": "zh-CN",
        "learning_mode": "read",
    }
    values.update(overrides)
    return LiveFollowUpTicketBinding(**values)  # type: ignore[arg-type]


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "anchor_element_bid": "element-1",
        "preview_mode": False,
        "learning_mode": "read",
        "surface": "read_content",
    }
    payload.update(overrides)
    return payload


def _route_app(monkeypatch: object, *, enabled: bool = True) -> Flask:
    app = Flask("live-follow-up-route-test")
    app.testing = True
    app.config.update(ENV="production", SECRET_KEY="test-secret")

    @app.before_request
    def install_user() -> None:
        request.user = SimpleNamespace(user_id="user-1")

    monkeypatch.setattr(routes, "Sock", _FakeSock)
    monkeypatch.setattr(routes, "is_gemini_live_enabled", lambda: enabled)
    routes.register_live_follow_up_routes(app)
    return app


def _stub_session_validation(monkeypatch: object) -> None:
    monkeypatch.setattr(
        routes,
        "is_live_follow_up_model_available",
        lambda _model: True,
    )
    monkeypatch.setattr(
        routes,
        "_require_course_access",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        routes,
        "_load_anchor",
        lambda **_kwargs: SimpleNamespace(progress_record_bid="progress-1"),
    )
    monkeypatch.setattr(
        routes,
        "_resolve_live_config",
        lambda *_args, **_kwargs: (
            SimpleNamespace(ask_model=routes.GEMINI_LIVE_MODEL_ID),
            "Kore",
        ),
    )
    monkeypatch.setattr(
        routes,
        "get_config",
        lambda name, default=None: (
            "test-gemini-key" if name == "GEMINI_API_KEY" else default
        ),
    )
    monkeypatch.setattr(routes, "generate_id", lambda _app: "session-1")
    monkeypatch.setattr(routes, "get_current_language", lambda: "zh-CN")
    monkeypatch.setattr(routes, "is_allowed_oauth_origin", lambda *_args: False)


def _session_post(
    app: Flask,
    *,
    payload: object,
    origin: str | None = "https://learn.example.com",
) -> object:
    headers = {"Origin": origin} if origin is not None else {}
    return app.test_client().post(
        "/api/learn/shifu/course-1/live-follow-up/chapter-1/session",
        json=payload,
        headers=headers,
        base_url="https://learn.example.com",
    )


def _ws_handler(app: Flask) -> object:
    handlers = app.extensions["test_live_sock"]
    return handlers["/api/learn/live-follow-up/ws/<session_bid>"]


def _json_frames(ws: _CaptureWebSocket) -> list[dict[str, object]]:
    return [json.loads(frame) for frame in ws.sent if isinstance(frame, str)]


def _fail_ticket_issue(*_args: object, **_kwargs: object) -> None:
    pytest.fail("rejected session request reached ticket issuance")


def test_session_endpoint_fails_before_ticket_when_feature_is_disabled(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch, enabled=False)
    monkeypatch.setattr(routes, "issue_live_follow_up_ticket", _fail_ticket_issue)

    with pytest.raises(AppError):
        _session_post(app, payload=_valid_payload())


def test_session_endpoint_fails_before_ticket_when_bidi_model_is_unavailable(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch)
    monkeypatch.setattr(
        routes,
        "is_live_follow_up_model_available",
        lambda _model: False,
    )
    monkeypatch.setattr(routes, "issue_live_follow_up_ticket", _fail_ticket_issue)

    with pytest.raises(AppError):
        _session_post(app, payload=_valid_payload())


@pytest.mark.parametrize("origin", [None, "https://attacker.example.com"])
def test_session_endpoint_rejects_missing_or_untrusted_origin(
    monkeypatch: object,
    origin: str | None,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    monkeypatch.setattr(routes, "issue_live_follow_up_ticket", _fail_ticket_issue)

    with pytest.raises(AppError):
        _session_post(app, payload=_valid_payload(), origin=origin)


def test_session_endpoint_ignores_spoofed_forwarded_authority(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    monkeypatch.setattr(routes, "issue_live_follow_up_ticket", _fail_ticket_issue)

    with pytest.raises(AppError):
        app.test_client().post(
            "/api/learn/shifu/course-1/live-follow-up/chapter-1/session",
            json=_valid_payload(),
            headers={
                "Origin": "https://attacker.example.com",
                "X-Forwarded-Host": "attacker.example.com:8443",
                "X-Forwarded-Port": "8443",
                "X-Forwarded-Proto": "https",
            },
            base_url="https://learn.example.com",
        )


def test_session_endpoint_preserves_same_origin_non_default_port(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    issued = IssuedLiveFollowUpTicket(
        token="raw-secret-ticket",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    captured: dict[str, object] = {}

    def issue_ticket(
        _app: object,
        *,
        binding: LiveFollowUpTicketBinding,
    ) -> IssuedLiveFollowUpTicket:
        captured["binding"] = binding
        return issued

    monkeypatch.setattr(routes, "issue_live_follow_up_ticket", issue_ticket)

    response = app.test_client().post(
        "/api/learn/shifu/course-1/live-follow-up/chapter-1/session",
        json=_valid_payload(),
        headers={
            "Origin": "https://learn.example.com:8443",
            "X-Forwarded-Proto": "https",
        },
        base_url="http://learn.example.com:8443",
    )

    assert response.status_code == 200
    assert captured["binding"] == _binding(origin="https://learn.example.com:8443")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        _valid_payload(learning_mode="classroom"),
        _valid_payload(surface="teacher_preview"),
    ],
)
def test_session_endpoint_rejects_non_object_classroom_and_preview_mismatch(
    monkeypatch: object,
    payload: object,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    monkeypatch.setattr(routes, "issue_live_follow_up_ticket", _fail_ticket_issue)

    with pytest.raises(AppError):
        _session_post(app, payload=payload)


def test_session_endpoint_fails_closed_when_ticket_redis_is_unavailable(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    monkeypatch.setattr(security, "_redis_client", lambda: None)

    with pytest.raises(AppError):
        _session_post(app, payload=_valid_payload())


def test_session_response_keeps_ticket_out_of_json_and_scopes_secure_cookie(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    issued = IssuedLiveFollowUpTicket(
        token="raw-secret-ticket",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    captured: dict[str, object] = {}

    def issue_ticket(
        _app: object,
        *,
        binding: LiveFollowUpTicketBinding,
    ) -> IssuedLiveFollowUpTicket:
        captured["binding"] = binding
        return issued

    monkeypatch.setattr(routes, "issue_live_follow_up_ticket", issue_ticket)

    response = _session_post(app, payload=_valid_payload())
    body = response.get_json()
    serialized = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body["data"] == {
        "session_bid": "session-1",
        "ws_path": "/api/learn/live-follow-up/ws/session-1",
        "expires_at": "2030-01-01T00:00:00Z",
    }
    assert "raw-secret-ticket" not in serialized
    assert "raw-secret-ticket" not in body["data"]["ws_path"]
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith(f"{LIVE_FOLLOW_UP_TICKET_COOKIE_NAME}=raw-secret-ticket;")
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=Strict" in cookie
    assert "Path=/api/learn/live-follow-up/ws/session-1" in cookie
    assert captured["binding"] == _binding()


def test_text_follow_up_model_is_rejected_instead_of_downgraded(
    monkeypatch: object,
) -> None:
    app = Flask("live-text-model-rejection-test")
    follow_up_info = SimpleNamespace(
        ask_mode=5103,
        ask_model="gpt-text-only",
        ask_provider_config={},
    )
    monkeypatch.setattr(routes, "get_follow_up_info_v2", lambda *_args: follow_up_info)
    monkeypatch.setattr(
        routes,
        "get_effective_ask_provider_config",
        lambda *_args: pytest.fail("text model entered Live provider normalization"),
    )

    with app.test_request_context("/"), pytest.raises(AppError):
        routes._resolve_live_config(
            app,
            shifu_bid="course-1",
            outline_bid="chapter-1",
            progress_record_bid="progress-1",
            preview_mode=False,
        )


def test_live_config_rejects_model_without_discovered_bidi_capability(
    monkeypatch: object,
) -> None:
    app = Flask("live-model-capability-rejection-test")
    follow_up_info = SimpleNamespace(
        ask_mode=5103,
        ask_model=routes.GEMINI_LIVE_MODEL_ID,
        ask_provider_config={
            "provider": "llm",
            "mode": "provider_only",
            "config": {"live_voice": "Kore"},
        },
    )
    monkeypatch.setattr(routes, "get_follow_up_info_v2", lambda *_args: follow_up_info)
    monkeypatch.setattr(
        routes,
        "is_live_follow_up_model_available",
        lambda _model: False,
    )

    with pytest.raises(routes.LiveFollowUpModelUnavailableError):
        routes._resolve_live_config(
            app,
            shifu_bid="course-1",
            outline_bid="chapter-1",
            progress_record_bid="progress-1",
            preview_mode=False,
        )


def test_ws_feature_disabled_does_not_consume_cookie(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch, enabled=False)
    ws = _CaptureWebSocket()
    handler = _ws_handler(app)

    def unexpected_consume(*_args: object, **_kwargs: object) -> None:
        pytest.fail("disabled WebSocket must not touch a ticket")

    monkeypatch.setattr(routes, "consume_live_follow_up_ticket", unexpected_consume)
    with app.test_request_context(
        "/api/learn/live-follow-up/ws/session-1",
        headers={
            "Origin": "https://learn.example.com",
            "Cookie": f"{LIVE_FOLLOW_UP_TICKET_COOKIE_NAME}=raw-ticket",
        },
    ):
        request.user = SimpleNamespace(user_id="user-1")
        handler(ws, "session-1")

    assert _json_frames(ws) == [
        {"type": "error", "code": "feature_disabled", "retryable": True}
    ]


@pytest.mark.parametrize(
    "failure",
    [
        security.LiveFollowUpSecurityUnavailableError("redis_unavailable"),
        security.LiveFollowUpTicketRejectedError("invalid_origin"),
    ],
)
def test_ws_origin_or_redis_failure_is_auth_failed_and_never_starts_session(
    monkeypatch: object,
    failure: Exception,
) -> None:
    app = _route_app(monkeypatch)
    ws = _CaptureWebSocket()
    handler = _ws_handler(app)

    def reject_ticket(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(routes, "consume_live_follow_up_ticket", reject_ticket)
    monkeypatch.setattr(
        routes,
        "_run_live_websocket",
        lambda *_args, **_kwargs: pytest.fail("rejected ticket started a session"),
    )
    with app.test_request_context(
        "/api/learn/live-follow-up/ws/session-1",
        headers={
            "Origin": "https://learn.example.com",
            "Cookie": f"{LIVE_FOLLOW_UP_TICKET_COOKIE_NAME}=raw-ticket",
        },
    ):
        request.user = SimpleNamespace(user_id="user-1")
        handler(ws, "session-1")

    assert _json_frames(ws) == [
        {"type": "error", "code": "auth_failed", "retryable": False}
    ]


def test_ws_passes_only_cookie_and_exact_origin_to_atomic_consumer(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch)
    ws = _CaptureWebSocket()
    handler = _ws_handler(app)
    captured: dict[str, object] = {}

    def consume_ticket(_app: object, **kwargs: object) -> LiveFollowUpTicketBinding:
        captured.update(kwargs)
        return _binding()

    monkeypatch.setattr(routes, "consume_live_follow_up_ticket", consume_ticket)
    monkeypatch.setattr(
        routes,
        "_run_live_websocket",
        lambda _app, _ws, *, binding: captured.update({"started": binding}),
    )
    with app.test_request_context(
        "/api/learn/live-follow-up/ws/session-1",
        headers={
            "Origin": "https://learn.example.com",
            "Cookie": f"{LIVE_FOLLOW_UP_TICKET_COOKIE_NAME}=raw-ticket",
        },
    ):
        handler(ws, "session-1")

    assert captured == {
        "session_bid": "session-1",
        "token": "raw-ticket",
        "origin": "https://learn.example.com",
        "started": _binding(),
    }
    assert ws.sent == []


def test_ws_uses_one_time_ticket_instead_of_unavailable_browser_token_header(
    monkeypatch: object,
) -> None:
    app = _route_app(monkeypatch)
    ws = _CaptureWebSocket()
    handler = _ws_handler(app)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        routes,
        "consume_live_follow_up_ticket",
        lambda *_args, **_kwargs: _binding(),
    )
    monkeypatch.setattr(
        routes,
        "_run_live_websocket",
        lambda _app, _ws, *, binding: captured.update({"binding": binding}),
    )

    with app.test_request_context(
        "/api/learn/live-follow-up/ws/session-1",
        headers={
            "Origin": "https://learn.example.com",
            "Cookie": f"{LIVE_FOLLOW_UP_TICKET_COOKIE_NAME}=raw-ticket",
        },
    ):
        assert not hasattr(request, "user")
        handler(ws, "session-1")

    assert "live_follow_up_ws" in by_pass_login_func
    assert captured == {"binding": _binding()}


def _stub_websocket_runtime(monkeypatch: object) -> None:
    _BlockingProvider.instances.clear()
    monkeypatch.setattr(
        routes,
        "acquire_live_follow_up_capacity",
        lambda *_args, **_kwargs: LiveFollowUpCapacityLease(
            lease_id="lease-1",
            user_bid="user-1",
            worker_id="worker-1",
        ),
    )
    monkeypatch.setattr(
        routes,
        "release_live_follow_up_capacity",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        routes,
        "_resolve_live_config",
        lambda *_args, **_kwargs: (
            SimpleNamespace(ask_model=routes.GEMINI_LIVE_MODEL_ID),
            "Kore",
        ),
    )
    monkeypatch.setattr(
        routes, "_build_conversation", lambda *_args, **_kwargs: ("prompt", ())
    )
    monkeypatch.setattr(
        routes,
        "get_config",
        lambda name, default=None: (
            "test-gemini-key" if name == "GEMINI_API_KEY" else default
        ),
    )
    monkeypatch.setattr(routes, "GeminiLiveProvider", _BlockingProvider)
    monkeypatch.setattr(routes, "LiveFollowUpTrace", _FakeTrace)
    monkeypatch.setattr(
        routes,
        "_commit_turns",
        lambda *_args, **_kwargs: True,
    )


@pytest.mark.parametrize("audio", [b"", b"x" * 3, b"x" * 8194])
def test_ws_rejects_empty_odd_or_over_limit_pcm_without_upstream_send(
    monkeypatch: object,
    audio: bytes,
) -> None:
    _stub_websocket_runtime(monkeypatch)
    app = Flask("live-audio-reject-test")
    ws = _CaptureWebSocket([audio])

    with app.test_request_context("/api/learn/live-follow-up/ws/session-1"):
        routes._run_live_websocket(app, ws, binding=_binding())

    assert _BlockingProvider.instances[0].audio_frames == []
    messages = _json_frames(ws)
    assert {"type": "error", "code": "invalid_audio", "retryable": False} in messages
    assert messages[-1] == {"type": "session_end", "reason": "invalid_request"}


def test_ws_accepts_exact_8kib_even_pcm_boundary(monkeypatch: object) -> None:
    _stub_websocket_runtime(monkeypatch)
    app = Flask("live-audio-boundary-test")
    audio = b"x" * routes.GEMINI_LIVE_MAX_INPUT_FRAME_BYTES
    ws = _CaptureWebSocket([audio, '{"type":"end"}'])

    with app.test_request_context("/api/learn/live-follow-up/ws/session-1"):
        routes._run_live_websocket(app, ws, binding=_binding())

    assert _BlockingProvider.instances[0].audio_frames == [audio]
    messages = _json_frames(ws)
    assert not any(message.get("type") == "error" for message in messages)
    assert messages[-1] == {"type": "session_end", "reason": "ended_by_user"}


def test_ws_ends_bounded_session_when_browser_floods_pcm(monkeypatch: object) -> None:
    _stub_websocket_runtime(monkeypatch)
    app = Flask("live-audio-rate-test")
    frame = b"x" * 1280
    ws = _CaptureWebSocket([frame] * 60)

    with app.test_request_context("/api/learn/live-follow-up/ws/session-1"):
        routes._run_live_websocket(app, ws, binding=_binding())

    assert len(_BlockingProvider.instances[0].audio_frames) < 60
    messages = _json_frames(ws)
    assert {
        "type": "error",
        "code": "audio_rate_exceeded",
        "retryable": False,
    } in messages
    assert messages[-1] == {"type": "session_end", "reason": "invalid_request"}


def test_upstream_writer_rejects_backlog_without_blocking_caller() -> None:
    class SlowProvider:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()
            self.frames: list[bytes] = []

        def send_audio(self, frame: bytes) -> None:
            self.started.set()
            self.release.wait(timeout=2)
            self.frames.append(frame)

        def send_audio_stream_end(self) -> None:
            return None

    provider = SlowProvider()
    ready = threading.Event()
    ready.set()
    failures: queue.SimpleQueue[routes._ReaderFailure] = queue.SimpleQueue()
    writer = routes._UpstreamWriter(
        provider=provider,  # type: ignore[arg-type]
        upstream_ready=ready,
        upstream_connection_lock=threading.Lock(),
        session_stop=threading.Event(),
        failures=failures,
        max_queue_bytes=4,
        max_queue_frames=4,
    )

    assert writer.enqueue_audio(b"aa") is True
    assert provider.started.wait(timeout=1)
    assert writer.enqueue_audio(b"bb") is True
    started_at = time.monotonic()
    assert writer.enqueue_audio(b"cc") is False
    assert time.monotonic() - started_at < 0.1

    provider.release.set()
    writer.close(drain=True)
    assert provider.frames == [b"aa", b"bb"]
    assert failures.empty()


def test_upstream_writer_reports_bounded_send_failure() -> None:
    class FailingProvider:
        def send_audio(self, _frame: bytes) -> None:
            message = "raw upstream failure"
            raise routes.GeminiLiveConnectionError(message)

        def send_audio_stream_end(self) -> None:
            return None

    ready = threading.Event()
    ready.set()
    stopped = threading.Event()
    failures: queue.SimpleQueue[routes._ReaderFailure] = queue.SimpleQueue()
    writer = routes._UpstreamWriter(
        provider=FailingProvider(),  # type: ignore[arg-type]
        upstream_ready=ready,
        upstream_connection_lock=threading.Lock(),
        session_stop=stopped,
        failures=failures,
    )

    assert writer.enqueue_audio(b"aa") is True
    assert stopped.wait(timeout=1)

    failure = failures.get_nowait()
    assert failure == routes._ReaderFailure(
        code="upstream_unavailable",
        retryable=True,
    )
    assert writer.failed is True
    writer.close(drain=False)


def test_browser_sender_cuts_off_slow_or_failed_consumers() -> None:
    class SlowWebSocket:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()

        def send(self, _payload: str | bytes) -> None:
            self.started.set()
            self.release.wait(timeout=2)

    slow_ws = SlowWebSocket()
    slow_sender = routes._BrowserSender(
        slow_ws,
        max_queue_bytes=4,
        max_queue_frames=4,
    )
    assert slow_sender.binary(b"aa") is True
    assert slow_ws.started.wait(timeout=1)
    assert slow_sender.binary(b"bb") is True
    started_at = time.monotonic()
    assert slow_sender.binary(b"cc") is False
    assert time.monotonic() - started_at < 0.1
    assert slow_sender.failed is True
    slow_ws.release.set()
    slow_sender.close(drain=False)

    stalled_ws = SlowWebSocket()
    stalled_sender = routes._BrowserSender(
        stalled_ws,
        max_queue_bytes=1024,
        send_timeout_seconds=0.02,
    )
    assert stalled_sender.binary(b"one frame") is True
    assert stalled_ws.started.wait(timeout=1)
    deadline = time.monotonic() + 1
    while not stalled_sender.failed and time.monotonic() < deadline:
        time.sleep(0.01)
    assert stalled_sender.failed is True
    stalled_ws.release.set()
    stalled_sender.close(drain=False)

    failed = threading.Event()

    class FailingWebSocket:
        def send(self, _payload: str | bytes) -> None:
            failed.set()
            raise OSError

    failing_sender = routes._BrowserSender(FailingWebSocket())
    assert failing_sender.json({"type": "state"}) is True
    assert failed.wait(timeout=1)
    deadline = time.monotonic() + 1
    while not failing_sender.failed and time.monotonic() < deadline:
        time.sleep(0.01)
    assert failing_sender.failed is True
    failing_sender.close(drain=False)


def test_ws_rejects_text_control_without_invoking_text_follow_up(
    monkeypatch: object,
) -> None:
    _stub_websocket_runtime(monkeypatch)
    app = Flask("live-no-text-fallback-test")
    ws = _CaptureWebSocket(['{"type":"text","text":"fallback please"}'])

    with app.test_request_context("/api/learn/live-follow-up/ws/session-1"):
        routes._run_live_websocket(app, ws, binding=_binding())

    assert _BlockingProvider.instances[0].audio_frames == []
    messages = _json_frames(ws)
    assert {"type": "error", "code": "invalid_control", "retryable": False} in messages
    assert messages[-1] == {"type": "session_end", "reason": "invalid_request"}


def test_reader_maps_upstream_error_to_bounded_failure_without_forwarding() -> None:
    class UpstreamErrorProvider:
        def receive(self) -> GeminiLiveServerEvent:
            return GeminiLiveServerEvent(
                upstream_error=True,
                upstream_error_code="raw-provider-code",
            )

    class UnexpectedAccumulator:
        def process_event(self, _event: object) -> object:
            pytest.fail("upstream errors must not enter the turn accumulator")

    ws = _CaptureWebSocket()
    failures: queue.SimpleQueue[routes._ReaderFailure] = queue.SimpleQueue()
    stop_event = threading.Event()

    routes._reader_loop(
        provider=UpstreamErrorProvider(),  # type: ignore[arg-type]
        accumulator=UnexpectedAccumulator(),  # type: ignore[arg-type]
        sender=routes._BrowserSender(ws),
        stop_event=stop_event,
        upstream_ready=threading.Event(),
        upstream_connection_lock=threading.Lock(),
        failures=failures,
        turn_started_at={},
        turn_started_lock=threading.Lock(),
    )

    failure = failures.get_nowait()
    assert stop_event.is_set()
    assert failure.code == "upstream_unavailable"
    assert failure.retryable is True
    assert ws.sent == []


def test_reader_reconciles_go_away_usage_before_ending() -> None:
    class GoAwayProvider:
        def receive(self) -> GeminiLiveServerEvent:
            return GeminiLiveServerEvent(
                go_away=True,
                turn_complete=True,
                usage_metadata={"totalTokenCount": 11},
            )

        def can_resume_after(self, _event: object) -> bool:
            return False

    accumulator = routes.LiveTurnAccumulator("go-away-usage-session")
    ws = _CaptureWebSocket()
    sender = routes._BrowserSender(ws)
    failures: queue.SimpleQueue[routes._ReaderFailure] = queue.SimpleQueue()
    stop_event = threading.Event()

    routes._reader_loop(
        provider=GoAwayProvider(),  # type: ignore[arg-type]
        accumulator=accumulator,
        sender=sender,
        stop_event=stop_event,
        upstream_ready=threading.Event(),
        upstream_connection_lock=threading.Lock(),
        failures=failures,
        turn_started_at={},
        turn_started_lock=threading.Lock(),
    )
    sender.close()

    assert failures.get_nowait().code == "upstream_ended"
    commits = accumulator.finish_session()
    assert len(commits) == 1
    assert commits[0].usage_metadata == {"totalTokenCount": 11}


def test_pending_turn_retries_before_acknowledging_persistence(
    monkeypatch: object,
) -> None:
    app = Flask("live-turn-retry-test")
    ws = _CaptureWebSocket()
    calls = 0
    session_removals: list[None] = []

    def persist_after_one_failure(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            message = "transient usage write failure"
            raise RuntimeError(message)
        return SimpleNamespace(usage_bid="usage-1")

    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        persist_after_one_failure,
    )
    monkeypatch.setattr(
        routes.db.session,
        "remove",
        lambda: session_removals.append(None),
    )
    commits = [
        routes.LiveTurnCommit(
            session_bid="session-1",
            turn_index=1,
            user_transcript="Question",
            answer_transcript="Answer",
            full_answer_transcript="Answer",
            interrupted=False,
            terminal_reason="turn_complete",
            usage_metadata={"totalTokenCount": 2},
            audio_sent_bytes=2,
            audio_played_bytes=2,
        )
    ]
    context = routes.LiveTurnPersistenceContext(
        session_bid="session-1",
        user_bid="user-1",
        shifu_bid="course-1",
        outline_item_bid="chapter-1",
        progress_record_bid="progress-1",
        anchor_element_bid="element-1",
        preview_mode=False,
        learning_mode="read",
    )

    sender = routes._BrowserSender(ws)
    assert routes._commit_pending_turns(
        app,
        commits=commits,
        persistence_context=context,
        trace=_FakeTrace(),  # type: ignore[arg-type]
        sender=sender,
        turn_started_at={1: 1.0},
        turn_started_lock=threading.Lock(),
    )
    sender.close()

    assert calls == 2
    assert len(session_removals) == 2
    assert commits == []
    assert _json_frames(ws) == [{"type": "turn_committed", "turn_index": 1}]

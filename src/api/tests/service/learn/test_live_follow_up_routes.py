"""Security, token, and persistence contracts for direct Gemini Live routes."""

from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from typing import ClassVar

import pytest
from flask import Flask, request
from flaskr.common.http import get_sensitive_body_limit, init_sensitive_body_policy
from flaskr.service.common.models import AppError
from flaskr.service.learn import live_follow_up_routes as routes
from flaskr.service.learn import live_follow_up_session_store as session_store
from flaskr.service.learn.gemini_live_token import (
    GEMINI_LIVE_CONSTRAINED_ENDPOINT,
    GeminiLiveEphemeralToken,
    GeminiLiveHistoryTurn,
    GeminiLiveTokenError,
    GeminiLiveTokenTimeoutError,
)
from flaskr.service.learn.live_follow_up_admission import (
    AdmissionRequest,
    AdmissionResult,
)
from flaskr.service.learn.live_follow_up_capacity import (
    LiveFollowUpCapacityLease,
)
from flaskr.service.learn.live_follow_up_persistence import (
    LiveFollowUpPersistenceError,
    LiveTurnPersistenceResult,
)
from flaskr.service.learn.live_follow_up_session_store import (
    LiveFollowUpSessionBinding,
    LiveFollowUpSessionRejectedError,
    LiveFollowUpSessionStoreUnavailableError,
    LiveFollowUpTurnReservation,
    LiveFollowUpTurnState,
    StoredLiveFollowUpSession,
)


class _FakeTrace:
    trace_id = "a" * 32
    instances: ClassVar[list[_FakeTrace]] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.recorded: list[tuple[object, object]] = []
        self.closed: list[str] = []
        self.instances.append(self)

    def record_turn(self, turn: object, result: object) -> None:
        self.recorded.append((turn, result))

    def close(self, *, end_reason: str) -> None:
        self.closed.append(end_reason)


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "anchor_element_bid": "element-1",
        "preview_mode": False,
        "learning_mode": "read",
        "surface": "read_content",
    }
    payload.update(overrides)
    return payload


def _binding(**overrides: object) -> LiveFollowUpSessionBinding:
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
        "expires_at_epoch": datetime.now(tz=UTC).timestamp() + 900,
    }
    values.update(overrides)
    return LiveFollowUpSessionBinding(**values)  # type: ignore[arg-type]


def _stored_session(**overrides: object) -> StoredLiveFollowUpSession:
    return StoredLiveFollowUpSession(
        binding=_binding(**overrides),
        lease=LiveFollowUpCapacityLease(
            lease_id="lease-1",
            user_bid="user-1",
            worker_id="worker-1",
        ),
    )


def _route_app(monkeypatch: pytest.MonkeyPatch, *, enabled: bool = True) -> Flask:
    app = Flask("live-follow-up-route-test")
    app.testing = True
    app.config.update(ENV="production", SECRET_KEY="test-secret")
    init_sensitive_body_policy(app)

    @app.before_request
    def install_user() -> None:
        request.user = SimpleNamespace(user_id="user-1")

    monkeypatch.setattr(routes, "is_gemini_live_enabled", lambda: enabled)
    monkeypatch.setattr(routes, "is_allowed_oauth_origin", lambda *_args: False)
    monkeypatch.setattr(
        routes, "live_follow_up_persistence_lock", lambda *_args: nullcontext()
    )
    routes.register_live_follow_up_routes(app)
    return app


def _stub_session_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "is_gemini_live_rotation_enabled", lambda: False)
    monkeypatch.setattr(
        routes, "legacy_request_bid", lambda: "01990000-0000-7000-8000-000000000001"
    )
    monkeypatch.setattr(routes, "begin_admission", lambda *_a, **_k: _admission())
    monkeypatch.setattr(routes, "complete_admission", lambda *_a, **_k: True)
    monkeypatch.setattr(routes, "fail_admission", lambda *_a, **_k: None)
    monkeypatch.setattr(
        routes,
        "admission_status",
        lambda *_a, **_k: {
            **_admission().data,
            "operation_status": "failed",
            "ownership_current": True,
        },
    )
    monkeypatch.setattr(routes, "is_live_follow_up_model_available", lambda _: True)
    monkeypatch.setattr(routes, "_require_course_access", lambda *_a, **_k: None)
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
    monkeypatch.setattr(
        routes,
        "_build_conversation",
        lambda *_args, **_kwargs: (
            "private system instruction",
            (GeminiLiveHistoryTurn(role="user", text="Earlier question"),),
        ),
    )


def _admission() -> AdmissionResult:
    return AdmissionResult(
        {
            "request_bid": "01990000-0000-7000-8000-000000000001",
            "session_bid": "session-1",
            "admission_revision": "revision-1",
            "operation_status": "pending",
            "ownership_current": True,
            "rotation_enabled": False,
        },
        lease=_stored_session().lease,
        issued_at_ms=1_788_570_123_123,
        deadline_ms=1_788_570_138_123,
    )


def _token(now: datetime) -> GeminiLiveEphemeralToken:
    return GeminiLiveEphemeralToken(
        token="auth_tokens/ephemeral",
        expires_at=now + timedelta(minutes=15),
        new_session_expires_at=now + timedelta(seconds=30),
    )


def _post_session(
    app: Flask,
    payload: object,
    *,
    origin: str | None = "https://learn.example.com",
) -> object:
    headers = {"Origin": origin} if origin else {}
    return app.test_client().post(
        "/api/learn/shifu/course-1/live-follow-up/chapter-1/session",
        json=payload,
        headers=headers,
        base_url="https://learn.example.com",
    )


def _post_action(
    app: Flask,
    action: str,
    payload: object | None = None,
    *,
    origin: str = "https://learn.example.com",
) -> object:
    response = app.test_client().post(
        f"/api/learn/live-follow-up/session/session-1/{action}",
        json=payload if payload is not None else {},
        headers={"Origin": origin},
        base_url="https://learn.example.com",
    )
    if response.status_code == 200:
        assert response.mimetype == "application/json"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    return response


def test_live_response_never_interprets_reflected_values_as_html() -> None:
    payload = {"session_bid": "<script>alert('test')</script>"}
    response = routes._make_live_response(payload)
    assert response.mimetype == "application/json"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.json == {"code": 0, "message": "success", "data": payload}


@pytest.mark.parametrize(
    "path",
    [
        "/api/learn/shifu/course-1/live-follow-up/chapter-1/session",
        "/api/learn/live-follow-up/session/session-1/heartbeat",
        "/api/learn/live-follow-up/session/session-1/turn",
        "/api/learn/live-follow-up/session/session-1/finalize",
        "/api/learn/live-follow-up/session/session-1/end",
    ],
)
def test_all_live_routes_protect_bodies_before_shared_parsing(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    app = _route_app(monkeypatch)
    with app.test_request_context(path, method="POST"):
        assert get_sensitive_body_limit() == 60 * 1024
    body = BytesIO(b"x" * (60 * 1024 + 1))
    response = app.test_client().post(
        path,
        environ_overrides={
            "wsgi.input": body,
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(body.getvalue())),
        },
    )
    assert response.status_code == 413
    assert body.tell() == 0
    assert response.headers["Cache-Control"] == "no-store"


def test_disabled_or_unavailable_model_stops_before_token_mint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for enabled, available in ((False, True), (True, False)):
        app = _route_app(monkeypatch, enabled=enabled)
        monkeypatch.setattr(
            routes,
            "is_live_follow_up_model_available",
            lambda _model, value=available: value,
        )
        monkeypatch.setattr(
            routes,
            "mint_gemini_live_ephemeral_token",
            lambda **_kwargs: pytest.fail("invalid request reached token mint"),
        )
        with pytest.raises(AppError):
            _post_session(app, _valid_payload())


@pytest.mark.parametrize(
    ("payload", "origin"),
    [
        ([], "https://learn.example.com"),
        (_valid_payload(learning_mode="classroom"), "https://learn.example.com"),
        (_valid_payload(surface="teacher_preview"), "https://learn.example.com"),
        (_valid_payload(), None),
        (_valid_payload(), "https://attacker.example.com"),
    ],
)
def test_session_rejects_invalid_shape_mode_surface_and_origin(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
    origin: str | None,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    with pytest.raises(AppError):
        _post_session(app, payload, origin=origin)


@pytest.mark.parametrize("api_base_url", ["", "https://proxy.example.com/google/"])
def test_session_mints_constrained_token_and_returns_no_internal_ws_or_cookie(
    monkeypatch: pytest.MonkeyPatch,
    api_base_url: str,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    monkeypatch.setattr(
        routes,
        "get_config",
        lambda name, default=None: {
            "GEMINI_API_KEY": "test-gemini-key",
            "GEMINI_API_URL": api_base_url,
        }.get(name, default),
    )
    minted: list[dict[str, object]] = []
    admitted: list[dict[str, object]] = []
    stored: list[StoredLiveFollowUpSession] = []
    issued_at = datetime.fromtimestamp(_admission().issued_at_ms / 1000, tz=UTC)
    monkeypatch.setattr(
        routes,
        "begin_admission",
        lambda *_args, **kwargs: admitted.append(kwargs) or _admission(),
    )
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **kwargs: minted.append(kwargs) or _token(kwargs["current_time"]),
    )
    monkeypatch.setattr(
        routes,
        "complete_admission",
        lambda *_args, session_payload: (
            stored.append(session_store._decode_session(session_payload)) or True
        ),
    )

    response = _post_session(
        app,
        _valid_payload(api_base_url="https://untrusted.example.com"),
    )
    body = json.loads(response.get_data(as_text=True))["data"]

    assert body["session_bid"] == "session-1"
    assert body["ephemeral_token"] == "auth_tokens/ephemeral"
    assert body["websocket_url"] == GEMINI_LIVE_CONSTRAINED_ENDPOINT
    assert body["heartbeat_interval_ms"] == 15_000
    assert "ws_path" not in body
    assert response.headers.get("Set-Cookie") is None
    assert response.headers["Cache-Control"] == "no-store"
    assert response.mimetype == "application/json"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "systemInstruction" not in body["setup"]["setup"]
    assert "proxy.example.com" not in response.get_data(as_text=True)
    assert "untrusted.example.com" not in response.get_data(as_text=True)
    assert "test-gemini-key" not in response.get_data(as_text=True)
    assert body["history"]["clientContent"]["turns"][0]["parts"][0]["text"] == (
        "Earlier question"
    )
    assert minted == [
        {
            "api_key": "test-gemini-key",
            "api_base_url": api_base_url,
            "model": routes.GEMINI_LIVE_MODEL_ID,
            "voice_name": "Kore",
            "system_instruction": "private system instruction",
            "include_initial_history": True,
            "current_time": issued_at,
        }
    ]
    assert admitted == [
        {"session_bid": "session-1", "rotation_enabled": False, "legacy": True}
    ]
    assert stored[0].binding.origin == "https://learn.example.com"
    assert (
        stored[0].binding.expires_at_epoch
        == (issued_at + timedelta(minutes=15)).timestamp()
    )


@pytest.mark.parametrize(
    "failure",
    [
        GeminiLiveTokenError("failed"),
        LiveFollowUpSessionStoreUnavailableError("redis_unavailable"),
    ],
)
def test_session_releases_capacity_when_token_or_redis_fails(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    lease = _stored_session().lease
    released: list[LiveFollowUpCapacityLease] = []
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **kwargs: (
            (_ for _ in ()).throw(failure)
            if isinstance(failure, GeminiLiveTokenError)
            else _token(kwargs["current_time"])
        ),
    )
    monkeypatch.setattr(
        routes,
        "complete_admission",
        lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(failure)
            if isinstance(failure, LiveFollowUpSessionStoreUnavailableError)
            else True
        ),
    )
    monkeypatch.setattr(
        routes,
        "fail_admission",
        lambda _app, _request, result, **_kwargs: released.append(result.lease),
    )

    with pytest.raises(AppError):
        _post_session(app, _valid_payload())
    assert released == [lease]


@pytest.mark.parametrize("changed_field", ["expires_at", "new_session_expires_at"])
def test_session_rejects_a_token_outside_its_reserved_deadlines(
    monkeypatch: pytest.MonkeyPatch,
    changed_field: str,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    lease = _stored_session().lease
    released: list[LiveFollowUpCapacityLease] = []

    def mismatched_token(**kwargs: object) -> GeminiLiveEphemeralToken:
        token = _token(kwargs["current_time"])
        return replace(
            token,
            **{changed_field: getattr(token, changed_field) + timedelta(seconds=1)},
        )

    monkeypatch.setattr(routes, "mint_gemini_live_ephemeral_token", mismatched_token)
    monkeypatch.setattr(
        routes,
        "complete_admission",
        lambda *_args, **_kwargs: pytest.fail("mismatched credential was stored"),
    )
    monkeypatch.setattr(
        routes,
        "fail_admission",
        lambda _app, _request, result, **_kwargs: released.append(result.lease),
    )

    with pytest.raises(AppError):
        _post_session(app, _valid_payload())
    assert released == [lease]


def test_capacity_limit_is_bounded_before_token_mint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    monkeypatch.setattr(
        routes,
        "begin_admission",
        lambda *_args, **_kwargs: AdmissionResult(
            {
                "operation_status": "rejected",
                "error_code": "capacity_exceeded",
                "retry_after_ms": 1000,
            }
        ),
    )
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **_kwargs: pytest.fail("capacity rejection reached token mint"),
    )
    with pytest.raises(AppError) as raised:
        _post_session(app, _valid_payload())
    assert raised.value.code == 4018


def _stub_active_direct_session(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _stored_session()
    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_args, **_kwargs: session,
    )
    monkeypatch.setattr(
        routes,
        "touch_live_follow_up_session",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        routes,
        "reserve_live_follow_up_turn",
        lambda _app, *, session_bid, turn_index, **_kwargs: LiveFollowUpTurnReservation(
            session_bid=session_bid,
            turn_index=turn_index,
            claim="claim-1",
        ),
    )
    monkeypatch.setattr(
        routes,
        "commit_live_follow_up_turn_reservation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        routes,
        "release_live_follow_up_turn_reservation",
        lambda *_args, **_kwargs: None,
    )


def test_heartbeat_validates_binding_without_extending_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    touched: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        routes,
        "touch_live_follow_up_session",
        lambda _app, *, session_bid, finalizing: touched.append(
            (session_bid, finalizing)
        ),
    )

    response = _post_action(app, "heartbeat")
    body = json.loads(response.get_data(as_text=True))["data"]
    assert body["session_bid"] == "session-1"
    assert touched == [("session-1", False)]


@pytest.mark.parametrize("action", ["heartbeat", "turn", "end", "finalize"])
def test_direct_session_rejects_changed_user_or_origin_before_touch(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    app = _route_app(monkeypatch)
    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_args, **_kwargs: _stored_session(user_bid="user-2"),
    )
    monkeypatch.setattr(
        routes,
        "touch_live_follow_up_session",
        lambda *_args, **_kwargs: pytest.fail("rejected binding was touched"),
    )
    with pytest.raises(AppError):
        _post_action(app, action)


@pytest.mark.parametrize("finalizing", [False, True])
def test_disabled_flag_allows_an_issued_session_to_finish(
    monkeypatch: pytest.MonkeyPatch,
    finalizing: bool,
) -> None:
    app = _route_app(monkeypatch, enabled=False)
    _stub_active_direct_session(monkeypatch)

    def load_session(
        _app: Flask, *, session_bid: str, allow_finalization: bool
    ) -> StoredLiveFollowUpSession:
        assert session_bid == "session-1"
        if finalizing and not allow_finalization:
            raise LiveFollowUpSessionRejectedError
        return _stored_session()

    monkeypatch.setattr(routes, "load_live_follow_up_session", load_session)
    result = LiveTurnPersistenceResult(
        ask_element_bid="ask-1",
        answer_element_bid="answer-1",
        history_saved=True,
    )
    monkeypatch.setattr(routes, "LiveFollowUpTrace", _FakeTrace)
    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        lambda *_args, **_kwargs: result,
    )
    monkeypatch.setattr(
        routes,
        "consume_live_follow_up_session",
        lambda *_args, **_kwargs: _stored_session(),
    )

    if finalizing:
        with pytest.raises(AppError):
            _post_action(app, "heartbeat")
    else:
        heartbeat = _post_action(app, "heartbeat")
        assert heartbeat.status_code == 200
    turn = _post_action(
        app,
        "turn",
        {
            "turn_index": 1,
            "user_transcript": "Final question",
            "played_answer_transcript": "Final answer",
            "interrupted": False,
            "usage_metadata": None,
            "latency_ms": 100,
        },
    )
    end = _post_action(app, "end", {"reason": "ended_by_user"})

    assert turn.status_code == 200
    assert end.status_code == 200


def test_turn_report_is_bounded_persisted_and_marked_non_billable_downstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    _FakeTrace.instances.clear()
    monkeypatch.setattr(routes, "LiveFollowUpTrace", _FakeTrace)
    persisted: list[tuple[object, object]] = []
    reservations: list[LiveFollowUpTurnReservation] = []
    result = LiveTurnPersistenceResult(
        ask_element_bid="ask-1",
        answer_element_bid="answer-1",
        history_saved=True,
    )
    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        lambda _app, context, turn: persisted.append((context, turn)) or result,
    )
    monkeypatch.setattr(
        routes,
        "commit_live_follow_up_turn_reservation",
        lambda _app, *, reservation: reservations.append(reservation),
    )

    response = _post_action(
        app,
        "turn",
        {
            "turn_index": 1,
            "user_transcript": " Question ",
            "played_answer_transcript": " Answer ",
            "interrupted": True,
            "usage_metadata": {"totalTokenCount": 5},
            "latency_ms": 321,
        },
    )
    body = json.loads(response.get_data(as_text=True))["data"]
    context, turn = persisted[0]
    assert context.user_bid == "user-1"
    assert context.trace_id == "a" * 32
    assert turn.user_transcript == "Question"
    assert turn.played_answer_transcript == "Answer"
    assert turn.interrupted is True
    assert body == {
        "session_bid": "session-1",
        "turn_index": 1,
        "history_saved": True,
        "ask_element_bid": "ask-1",
        "answer_element_bid": "answer-1",
    }
    assert _FakeTrace.instances[0].recorded == [(turn, result)]
    assert _FakeTrace.instances[0].closed == ["turn_committed"]
    assert [(item.session_bid, item.turn_index) for item in reservations] == [
        ("session-1", 1)
    ]


def test_failed_turn_persistence_releases_only_its_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    released: list[LiveFollowUpTurnReservation] = []

    def fail_persistence(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        fail_persistence,
    )
    monkeypatch.setattr(
        routes,
        "release_live_follow_up_turn_reservation",
        lambda _app, *, reservation: released.append(reservation),
    )

    with pytest.raises(AppError):
        _post_action(
            app,
            "turn",
            {
                "turn_index": 1,
                "user_transcript": "Question",
                "played_answer_transcript": "",
                "interrupted": True,
                "usage_metadata": None,
                "latency_ms": 100,
            },
        )

    assert [(item.session_bid, item.turn_index) for item in released] == [
        ("session-1", 1)
    ]


@pytest.mark.parametrize("history_saved", [False, True])
def test_duplicate_turn_acknowledges_durable_state_without_repeating_writes(
    monkeypatch: pytest.MonkeyPatch, history_saved: bool
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    _FakeTrace.instances.clear()
    monkeypatch.setattr(routes, "LiveFollowUpTrace", _FakeTrace)
    state = LiveFollowUpTurnState(
        last_committed_index=2, pending_index=3, pending_claim="next-turn"
    )
    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_a, **_k: replace(_stored_session(), turn_state=state),
    )
    monkeypatch.setattr(
        routes,
        "reserve_live_follow_up_turn",
        lambda *_a, **_k: pytest.fail("duplicate reserved again"),
    )
    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        lambda *_a, **_k: pytest.fail("duplicate persisted again"),
    )
    result = LiveTurnPersistenceResult(
        ask_element_bid="original-ask" if history_saved else "",
        answer_element_bid="original-answer" if history_saved else "",
        history_saved=history_saved,
    )
    loaded: list[tuple[str, int]] = []
    monkeypatch.setattr(
        routes,
        "load_persisted_live_follow_up_turn",
        lambda session_bid, turn_index: (
            loaded.append((session_bid, turn_index)) or result
        ),
    )
    response = _post_action(app, "turn", _turn_report(1))
    assert json.loads(response.get_data(as_text=True))["data"] == {
        "session_bid": "session-1",
        "turn_index": 1,
        "history_saved": history_saved,
        "ask_element_bid": result.ask_element_bid,
        "answer_element_bid": result.answer_element_bid,
    }
    assert loaded == [("session-1", 1)]
    assert _FakeTrace.instances == []


@pytest.mark.parametrize(
    "payload",
    [
        {"turn_index": "1"},
        {
            "turn_index": 1,
            "user_transcript": "x" * 32_001,
            "played_answer_transcript": "",
            "interrupted": False,
            "usage_metadata": None,
            "latency_ms": 0,
        },
        {
            "turn_index": 1,
            "user_transcript": "Question",
            "played_answer_transcript": "Answer",
            "interrupted": False,
            "usage_metadata": {"raw": "x" * (64 * 1024)},
            "latency_ms": 0,
        },
    ],
)
def test_turn_report_rejects_unbounded_or_invalid_client_data(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        lambda *_args, **_kwargs: pytest.fail("invalid report was persisted"),
    )
    if len(json.dumps(payload).encode()) > routes._MAX_DIRECT_TURN_REPORT_BYTES:
        assert _post_action(app, "turn", payload).status_code == 413
        return
    with pytest.raises(AppError):
        _post_action(app, "turn", payload)


@pytest.mark.parametrize("known_length", [True, False])
def test_oversized_turn_body_is_rejected_without_unbounded_buffering(
    known_length: bool,
) -> None:
    app = Flask("bounded-live-body-test")
    limit = routes._MAX_DIRECT_TURN_REPORT_BYTES
    body = BytesIO(b"x" * (limit * 2))
    environment: dict[str, object] = {
        "wsgi.input": body,
        "CONTENT_TYPE": "application/json",
        "wsgi.input_terminated": True,
    }
    if known_length:
        environment["CONTENT_LENGTH"] = str(limit * 2)
    with (
        app.test_request_context(method="POST", environ_overrides=environment),
        pytest.raises(AppError),
    ):
        routes._read_bounded_turn_payload()

    assert body.tell() == (0 if known_length else limit + 1)


def _turn_report(index: int) -> dict[str, object]:
    return {
        "turn_index": index,
        "user_transcript": "Question",
        "played_answer_transcript": "Answer",
        "interrupted": False,
        "usage_metadata": None,
        "latency_ms": 10,
    }


@pytest.mark.parametrize("in_flight", [False, True])
def test_finalize_skips_durable_turns_and_saves_remaining_reports_in_order(
    monkeypatch: pytest.MonkeyPatch,
    in_flight: bool,
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    session = _stored_session(
        expires_at_epoch=int(datetime.now(tz=UTC).timestamp()) + 900.123456
    )
    state = LiveFollowUpTurnState(
        last_committed_index=0 if in_flight else 1,
        pending_index=1 if in_flight else None,
        pending_claim="normal-request" if in_flight else "",
    )
    persisted: list[int] = []
    consumed: list[str] = []

    def commit_reservation(
        _app: Flask, *, reservation: LiveFollowUpTurnReservation
    ) -> None:
        nonlocal state
        state = LiveFollowUpTurnState(last_committed_index=reservation.turn_index)

    @contextmanager
    def wait_for_predecessor(_app: Flask, _session_bid: str) -> object:
        nonlocal session, state
        # A predecessor's Redis Lua write round-trips numbers at 14 digits.
        rounded_expiry = float(format(session.binding.expires_at_epoch, ".14g"))
        assert rounded_expiry != session.binding.expires_at_epoch
        session = replace(
            session,
            binding=replace(session.binding, expires_at_epoch=rounded_expiry),
        )
        state = LiveFollowUpTurnState(last_committed_index=1)
        yield

    def persist(
        _app: Flask, _context: object, turn: object
    ) -> LiveTurnPersistenceResult:
        persisted.append(turn.turn_index)
        return LiveTurnPersistenceResult(history_saved=True)

    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_a, **_k: replace(session, turn_state=state),
    )
    monkeypatch.setattr(
        routes, "commit_live_follow_up_turn_reservation", commit_reservation
    )
    monkeypatch.setattr(routes, "live_follow_up_persistence_lock", wait_for_predecessor)
    monkeypatch.setattr(routes, "persist_live_follow_up_turn", persist)
    monkeypatch.setattr(routes, "LiveFollowUpTrace", _FakeTrace)
    monkeypatch.setattr(
        routes,
        "consume_live_follow_up_session",
        lambda _app, *, session_bid: consumed.append(session_bid),
    )

    response = _post_action(
        app,
        "finalize",
        {
            "turns": [_turn_report(index) for index in (1, 2, 3)],
            "reason": "page_hidden",
        },
    )

    assert response.status_code == 200
    assert persisted == [2, 3]
    assert state.last_committed_index == 3
    assert consumed == ["session-1"]


@pytest.mark.parametrize("boundary", ["redis_ttl", "admission_deadline"])
def test_accepted_finalization_outlives_binding_and_admission_deadlines(
    monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    clock = [1_000.0]
    session = _stored_session(
        expires_at_epoch=971 if boundary == "admission_deadline" else 1_015
    )
    retained_until = [
        session.binding.expires_at_epoch
        + session_store.LIVE_FOLLOW_UP_SESSION_FINALIZATION_GRACE_SECONDS
    ]
    consumed: list[str] = []
    persisted: list[int] = []
    renewals: list[bool] = []

    def get_binding(_key: str) -> str | None:
        if consumed or clock[0] >= retained_until[0]:
            return None
        return session_store._serialize_session(session)

    def touch(_app: Flask, *, session_bid: str, finalizing: bool = False) -> None:
        assert session_bid == "session-1"
        assert get_binding("") is not None
        renewals.append(finalizing)
        ttl = (
            session_store.LIVE_FOLLOW_UP_SESSION_FINALIZATION_LEASE_SECONDS
            if finalizing
            else 0
        )
        retained_until[0] = max(retained_until[0], clock[0] + ttl)

    @contextmanager
    def wait_for_lock(_app: Flask, _session_bid: str) -> object:
        clock[0] += 2  # An accepted request can cross its grace deadline waiting.
        yield

    def persist(
        _app: Flask, context: object, turn: object
    ) -> LiveTurnPersistenceResult:
        assert context.user_bid == "user-1"
        assert context.shifu_bid == "course-1"
        clock[0] += 150  # Each write exceeds 45s; the batch exceeds one 300s lease.
        assert get_binding("") is not None
        if boundary == "admission_deadline":
            # Retention is not new authority, even while an accepted batch runs.
            with pytest.raises(AppError):
                _post_action(app, "finalize", {"turns": [], "admitted_at": 1_000})
            with pytest.raises(AppError):
                _post_action(app, "heartbeat")
        persisted.append(turn.turn_index)
        return LiveTurnPersistenceResult(history_saved=True)

    def acknowledge(_app: Flask, *, reservation: LiveFollowUpTurnReservation) -> None:
        nonlocal session
        assert get_binding("") is not None
        session = replace(
            session,
            turn_state=LiveFollowUpTurnState(
                last_committed_index=reservation.turn_index
            ),
        )

    monkeypatch.setattr(routes, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(session_store, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(
        session_store, "_redis_client", lambda: SimpleNamespace(get=get_binding)
    )
    monkeypatch.setattr(
        routes, "load_live_follow_up_session", session_store.load_live_follow_up_session
    )
    monkeypatch.setattr(routes, "touch_live_follow_up_session", touch)
    monkeypatch.setattr(routes, "live_follow_up_persistence_lock", wait_for_lock)
    monkeypatch.setattr(routes, "persist_live_follow_up_turn", persist)
    monkeypatch.setattr(routes, "commit_live_follow_up_turn_reservation", acknowledge)
    monkeypatch.setattr(routes, "LiveFollowUpTrace", _FakeTrace)
    monkeypatch.setattr(
        routes,
        "consume_live_follow_up_session",
        lambda _app, *, session_bid: consumed.append(session_bid),
    )

    result = _post_action(
        app, "finalize", {"turns": [_turn_report(index) for index in (1, 2, 3)]}
    )

    assert result.status_code == 200
    assert persisted == [1, 2, 3]
    assert consumed == ["session-1"]
    assert renewals == [True, True, True, True]
    assert get_binding("") is None


@pytest.mark.parametrize(
    "field",
    [
        "session_bid",
        "user_bid",
        "origin",
        "shifu_bid",
        "outline_bid",
        "anchor_element_bid",
        "progress_record_bid",
        "preview_mode",
        "model",
        "voice_name",
        "language",
        "learning_mode",
        "expires_at_epoch",
    ],
)
def test_finalization_rejects_a_replaced_binding_under_the_write_lock(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    session = _stored_session()
    replacement = {
        "preview_mode": True,
        "expires_at_epoch": session.binding.expires_at_epoch + 0.01,
    }.get(field, "changed")
    locked = False

    @contextmanager
    def replace_binding(_app: Flask, _session_bid: str) -> object:
        nonlocal locked
        locked = True
        yield

    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_a, **_k: (
            replace(session, binding=replace(session.binding, **{field: replacement}))
            if locked
            else session
        ),
    )
    monkeypatch.setattr(routes, "live_follow_up_persistence_lock", replace_binding)
    monkeypatch.setattr(
        routes,
        "reserve_live_follow_up_turn",
        lambda *_a, **_k: pytest.fail("replaced binding was reserved"),
    )
    with pytest.raises(AppError):
        _post_action(app, "finalize", {"turns": [_turn_report(1)]})


@pytest.mark.parametrize("indices", [[1, 1], [1, 3], [2, 1], list(range(1, 202))])
def test_finalize_rejects_invalid_batches_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
    indices: list[int],
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        lambda *_a, **_k: pytest.fail("invalid batch was persisted"),
    )
    with pytest.raises(AppError):
        _post_action(
            app, "finalize", {"turns": [_turn_report(index) for index in indices]}
        )


@pytest.mark.parametrize("action", ["turn", "finalize", "end"])
def test_direct_writes_do_not_steal_an_active_database_lock(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    session = replace(
        _stored_session(),
        turn_state=LiveFollowUpTurnState(
            pending_index=1, pending_claim="normal-request"
        ),
    )
    monkeypatch.setattr(
        routes, "load_live_follow_up_session", lambda *_a, **_k: session
    )

    @contextmanager
    def busy_lock(_app: Flask, _session_bid: str) -> object:
        raise LiveFollowUpPersistenceError
        yield  # pragma: no cover - contextmanager signature

    monkeypatch.setattr(routes, "live_follow_up_persistence_lock", busy_lock)
    monkeypatch.setattr(
        routes,
        "reserve_live_follow_up_turn",
        lambda *_a, **_k: pytest.fail("claim recovered before acquiring DB lock"),
    )
    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        lambda *_a, **_k: pytest.fail("in-flight claim was stolen"),
    )
    monkeypatch.setattr(
        routes,
        "consume_live_follow_up_session",
        lambda *_a, **_k: pytest.fail("unfinished session was consumed"),
    )
    payload = {"turns": [_turn_report(1)]} if action == "finalize" else _turn_report(1)
    with pytest.raises(AppError):
        _post_action(app, action, payload)


@pytest.mark.parametrize("action", ["turn", "finalize"])
def test_direct_writes_recover_abandoned_claims_only_under_database_lock(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    session = _stored_session()
    locked = False
    state = LiveFollowUpTurnState(pending_index=1, pending_claim="abandoned")
    events: list[str] = []

    @contextmanager
    def database_lock(_app: Flask, _session_bid: str) -> object:
        nonlocal locked
        locked = True
        events.append("locked")
        try:
            yield
        finally:
            locked = False
            events.append("unlocked")

    def recover(
        _app: Flask, *, session_bid: str, turn_index: int, recover_pending: bool
    ) -> LiveFollowUpTurnReservation:
        assert locked
        assert recover_pending
        assert state.pending_claim == "abandoned"
        events.append("recovered")
        return LiveFollowUpTurnReservation(session_bid, turn_index, "new-owner")

    def persist(*_args: object) -> LiveTurnPersistenceResult:
        assert locked
        events.append("persisted")
        return LiveTurnPersistenceResult(history_saved=True)

    def acknowledge(_app: Flask, *, reservation: LiveFollowUpTurnReservation) -> None:
        assert locked
        assert reservation.claim == "new-owner"
        events.append("acknowledged")

    monkeypatch.setattr(routes, "live_follow_up_persistence_lock", database_lock)
    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_a, **_k: replace(session, turn_state=state),
    )
    monkeypatch.setattr(routes, "reserve_live_follow_up_turn", recover)
    monkeypatch.setattr(routes, "persist_live_follow_up_turn", persist)
    monkeypatch.setattr(routes, "commit_live_follow_up_turn_reservation", acknowledge)
    monkeypatch.setattr(
        routes, "consume_live_follow_up_session", lambda *_a, **_k: None
    )
    monkeypatch.setattr(routes, "LiveFollowUpTrace", _FakeTrace)

    payload = {"turns": [_turn_report(1)]} if action == "finalize" else _turn_report(1)
    assert _post_action(app, action, payload).status_code == 200
    assert events == ["locked", "recovered", "persisted", "acknowledged", "unlocked"]


def test_end_consumes_binding_but_retains_capacity_until_token_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    consumed: list[str] = []
    monkeypatch.setattr(
        routes,
        "consume_live_follow_up_session",
        lambda _app, *, session_bid: consumed.append(session_bid) or _stored_session(),
    )
    monkeypatch.setattr(
        routes,
        "fail_admission",
        lambda *_args, **_kwargs: pytest.fail("disclosed token capacity released"),
    )

    response = _post_action(app, "end", {"reason": "ended_by_user"})
    body = json.loads(response.get_data(as_text=True))["data"]
    assert body == {"session_bid": "session-1", "reason": "ended_by_user"}
    assert consumed == ["session-1"]


def _v2_payload(**overrides: object) -> dict[str, object]:
    return _valid_payload(request_bid=_admission().data["request_bid"], **overrides)


@pytest.mark.parametrize(
    "status", ["pending", "issued", "failed", "cancelled", "missing"]
)
def test_status_only_reads_original_bound_metadata_even_when_live_disabled(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    app = _route_app(monkeypatch, enabled=False)
    _stub_session_validation(monkeypatch)
    seen: list[AdmissionRequest] = []
    for name in (
        "_require_course_access",
        "_load_anchor",
        "_resolve_live_config",
        "_build_conversation",
        "begin_admission",
        "mint_gemini_live_ephemeral_token",
    ):
        monkeypatch.setattr(
            routes,
            name,
            lambda *_a, **_k: pytest.fail("status reached mint/content preparation"),
        )
    monkeypatch.setattr(
        routes,
        "admission_status",
        lambda _app, operation, **_k: (
            seen.append(operation)
            or {
                "request_bid": operation.request_bid,
                "operation_status": status,
                "ownership_current": False,
                "rotation_enabled": False,
            }
        ),
    )
    response = _post_session(
        app,
        {
            "operation": "status",
            "request_bid": _admission().data["request_bid"],
            "target": _valid_payload(
                replace_session_bid="previous",
                expected_admission_revision="old-revision",
            ),
        },
    )
    data = response.get_json()["data"]
    assert data["operation_status"] == status
    assert set(data) == {
        "request_bid",
        "operation_status",
        "ownership_current",
        "rotation_enabled",
    }
    assert seen[0].origin == "https://learn.example.com"
    assert seen[0].user_bid == "user-1"
    assert seen[0].replace_session_bid == "previous"
    assert seen[0].expected_admission_revision == "old-revision"


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "status", "request_bid": "bad", "target": _valid_payload()},
        {"operation": "status", "request_bid": _admission().data["request_bid"]},
        {
            "operation": "status",
            "request_bid": _admission().data["request_bid"],
            "target": _valid_payload(),
            "anchor_element_bid": "unsafe-legacy-fallback",
        },
        {
            "operation": "status",
            "request_bid": _admission().data["request_bid"],
            "target": _valid_payload(replace_session_bid="partial-predecessor"),
        },
    ],
)
def test_status_rejects_malformed_or_legacy_mint_compatible_shape(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    app = _route_app(monkeypatch)
    monkeypatch.setattr(
        routes,
        "admission_status",
        lambda *_a, **_k: pytest.fail("invalid status reached Redis"),
    )
    with pytest.raises(AppError):
        _post_session(app, payload)


@pytest.mark.parametrize(
    "error_code",
    [
        "capacity_exceeded",
        "ownership_conflict",
        "stale_request",
        "operation_conflict",
        "admission_unavailable",
    ],
)
def test_v2_admission_rejection_is_bounded_data_without_provider_call(
    monkeypatch: pytest.MonkeyPatch, error_code: str
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    expected = {
        "request_bid": _admission().data["request_bid"],
        "operation_status": "rejected",
        "error_code": error_code,
        "rotation_enabled": True,
        "retry_after_ms": 1000,
    }
    monkeypatch.setattr(
        routes, "begin_admission", lambda *_a, **_k: AdmissionResult(expected)
    )
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **_k: pytest.fail("rejection minted token"),
    )
    response = _post_session(app, _v2_payload())
    assert response.get_json()["code"] == 0
    assert response.get_json()["data"] == expected


def test_v2_success_binds_metadata_before_returning_one_original_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    operations: list[AdmissionRequest] = []
    stored: list[StoredLiveFollowUpSession] = []
    monkeypatch.setattr(routes, "is_gemini_live_rotation_enabled", lambda: True)
    monkeypatch.setattr(
        routes,
        "begin_admission",
        lambda _app, operation, **_k: operations.append(operation) or _admission(),
    )
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **kwargs: _token(kwargs["current_time"]),
    )
    monkeypatch.setattr(
        routes,
        "complete_admission",
        lambda *_a, session_payload: (
            stored.append(session_store._decode_session(session_payload)) or True
        ),
    )
    response = _post_session(
        app,
        _v2_payload(
            replace_session_bid="prior", expected_admission_revision="prior-revision"
        ),
    )
    data = response.get_json()["data"]
    assert data["rotation_enabled"] is True
    assert data["operation_status"] == "issued"
    assert data["admission_revision"] == "revision-1"
    assert data["request_bid"] == _admission().data["request_bid"]
    assert stored[0].admission == operations[0]
    assert stored[0].admission_revision == "revision-1"
    assert stored[0].admission.replace_session_bid == "prior"
    assert "auth_tokens" not in routes.serialize_live_follow_up_session(stored[0])


def test_v2_late_provider_cannot_disclose_after_operation_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **kwargs: _token(kwargs["current_time"]),
    )
    monkeypatch.setattr(routes, "complete_admission", lambda *_a, **_k: False)
    data = _post_session(app, _v2_payload()).get_json()["data"]
    assert data["operation_status"] == "failed"
    assert data["ownership_current"] is True
    assert "ephemeral_token" not in data


def test_provider_wait_timeout_preserves_uncertain_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    failures: list[dict[str, object]] = []
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **_k: (_ for _ in ()).throw(GeminiLiveTokenTimeoutError("bounded")),
    )
    monkeypatch.setattr(
        routes, "fail_admission", lambda *_a, **kwargs: failures.append(kwargs)
    )
    data = _post_session(app, _v2_payload()).get_json()["data"]
    assert data["operation_status"] == "failed"
    assert failures == [{"undisclosed": False}]


def test_ambiguous_admission_failure_does_not_claim_pre_admission_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    from flaskr.service.learn.live_follow_up_capacity import (
        LiveFollowUpCapacityUnavailableError,
    )

    monkeypatch.setattr(
        routes,
        "begin_admission",
        lambda *_a, **_k: (_ for _ in ()).throw(
            LiveFollowUpCapacityUnavailableError("bounded")
        ),
    )
    monkeypatch.setattr(
        routes,
        "admission_status",
        lambda *_a, **_k: (_ for _ in ()).throw(
            LiveFollowUpCapacityUnavailableError("bounded")
        ),
    )
    with pytest.raises(AppError):
        _post_session(app, _v2_payload())


def test_failed_successor_response_preserves_its_revision_for_the_next_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **_k: (_ for _ in ()).throw(GeminiLiveTokenError("bounded")),
    )
    data = _post_session(
        app,
        _v2_payload(
            replace_session_bid="predecessor-a",
            expected_admission_revision="revision-a",
        ),
    ).get_json()["data"]
    assert data["operation_status"] == "failed"
    assert data["session_bid"] == "session-1"
    assert data["admission_revision"] == "revision-1"
    assert data["ownership_current"] is True
    seen: list[AdmissionRequest] = []
    monkeypatch.setattr(
        routes,
        "begin_admission",
        lambda _app, operation, **_k: seen.append(operation) or _admission(),
    )
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **kwargs: _token(kwargs["current_time"]),
    )
    payload = _v2_payload(
        replace_session_bid=str(data["session_bid"]),
        expected_admission_revision=str(data["admission_revision"]),
    )
    payload["request_bid"] = "01990000-0000-7000-8000-000000000002"
    assert (
        _post_session(app, payload).get_json()["data"]["operation_status"] == "issued"
    )
    assert seen[0].replace_session_bid == "session-1"
    assert seen[0].expected_admission_revision == "revision-1"


def _v2_session() -> StoredLiveFollowUpSession:
    return replace(
        _stored_session(),
        admission=AdmissionRequest(
            request_bid=str(_admission().data["request_bid"]),
            user_bid="user-1",
            origin="https://learn.example.com",
            shifu_bid="course-1",
            outline_bid="chapter-1",
            anchor_element_bid="element-1",
            preview_mode=False,
            learning_mode="read",
            surface="read_content",
        ),
        admission_revision="revision-1",
    )


def test_heartbeat_rejects_retired_owner_without_extending_or_replacing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    monkeypatch.setattr(
        routes, "load_live_follow_up_session", lambda *_a, **_k: _v2_session()
    )
    monkeypatch.setattr(routes, "current_admission", lambda *_a, **_k: False)
    monkeypatch.setattr(
        routes,
        "touch_live_follow_up_session",
        lambda *_a, **_k: pytest.fail("retired owner touched"),
    )
    assert _post_action(app, "heartbeat", {}).get_json()["data"] == {
        "session_bid": "session-1",
        "operation_status": "rejected",
        "error_code": "ownership_conflict",
    }


@pytest.mark.parametrize("action", ["end", "finalize"])
def test_consumed_binding_receipt_acknowledges_only_previously_committed_history(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    app = _route_app(monkeypatch)
    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_a, **_k: (_ for _ in ()).throw(LiveFollowUpSessionRejectedError()),
    )
    monkeypatch.setattr(
        routes,
        "retirement_receipt",
        lambda *_a, **_k: {
            "admission_revision": "old-revision",
            "last_committed_index": 2,
        },
    )
    monkeypatch.setattr(
        routes,
        "persist_live_follow_up_turn",
        lambda *_a, **_k: pytest.fail("receipt granted new write"),
    )
    payload = (
        {"turns": [_turn_report(1), _turn_report(2)]}
        if action == "finalize"
        else {"reason": "ended_by_user"}
    )
    data = _post_action(app, action, payload).get_json()["data"]
    assert data["admission_revision"] == "old-revision"
    if action == "finalize":
        with pytest.raises(AppError):
            _post_action(app, action, {"turns": [_turn_report(3)]})


def test_end_receipt_uses_latest_cursor_under_database_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    session = _v2_session()
    calls: list[dict[str, object]] = []
    loads = iter(
        [
            session,
            replace(session, turn_state=LiveFollowUpTurnState(last_committed_index=2)),
        ]
    )
    monkeypatch.setattr(
        routes, "load_live_follow_up_session", lambda *_a, **_k: next(loads)
    )
    monkeypatch.setattr(routes, "admission_time", lambda: 100)
    monkeypatch.setattr(routes, "touch_live_follow_up_session", lambda *_a, **_k: None)
    monkeypatch.setattr(
        routes, "retire_admission", lambda *_a, **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(
        routes, "consume_live_follow_up_session", lambda *_a, **_k: None
    )
    data = _post_action(app, "end", {"reason": "ended_by_user"}).get_json()["data"]
    assert data["admission_revision"] == "revision-1"
    assert calls[0]["last_committed_index"] == 2

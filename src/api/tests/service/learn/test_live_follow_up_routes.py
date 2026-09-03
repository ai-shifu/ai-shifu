"""Security, token, and persistence contracts for direct Gemini Live routes."""

from __future__ import annotations

import json
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
from flaskr.service.learn.gemini_live_token import (
    GEMINI_LIVE_CONSTRAINED_ENDPOINT,
    GeminiLiveEphemeralToken,
    GeminiLiveHistoryTurn,
    GeminiLiveTokenError,
)
from flaskr.service.learn.live_follow_up_capacity import (
    LiveFollowUpCapacityLease,
    LiveFollowUpCapacityLimitError,
)
from flaskr.service.learn.live_follow_up_persistence import (
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
    routes.register_live_follow_up_routes(app)
    return app


def _stub_session_validation(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _token() -> GeminiLiveEphemeralToken:
    now = datetime.now(tz=UTC)
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
    return app.test_client().post(
        f"/api/learn/live-follow-up/session/session-1/{action}",
        json=payload if payload is not None else {},
        headers={"Origin": origin},
        base_url="https://learn.example.com",
    )


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


def test_session_mints_constrained_token_and_returns_no_internal_ws_or_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_session_validation(monkeypatch)
    minted: list[dict[str, object]] = []
    stored: list[StoredLiveFollowUpSession] = []
    lease = _stored_session().lease
    monkeypatch.setattr(
        routes,
        "acquire_live_follow_up_capacity",
        lambda *_args, **_kwargs: lease,
    )
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **kwargs: minted.append(kwargs) or _token(),
    )
    monkeypatch.setattr(
        routes,
        "store_live_follow_up_session",
        lambda _app, *, session: stored.append(session),
    )

    response = _post_session(app, _valid_payload())
    body = json.loads(response.get_data(as_text=True))["data"]

    assert body["session_bid"] == "session-1"
    assert body["ephemeral_token"] == "auth_tokens/ephemeral"
    assert body["websocket_url"] == GEMINI_LIVE_CONSTRAINED_ENDPOINT
    assert body["heartbeat_interval_ms"] == 15_000
    assert "ws_path" not in body
    assert response.headers.get("Set-Cookie") is None
    assert response.headers["Cache-Control"] == "no-store"
    assert "systemInstruction" not in body["setup"]["setup"]
    assert body["history"]["clientContent"]["turns"][0]["parts"][0]["text"] == (
        "Earlier question"
    )
    assert minted == [
        {
            "api_key": "test-gemini-key",
            "model": routes.GEMINI_LIVE_MODEL_ID,
            "voice_name": "Kore",
            "system_instruction": "private system instruction",
            "include_initial_history": True,
        }
    ]
    assert stored[0].binding.origin == "https://learn.example.com"
    assert stored[0].binding.expires_at_epoch > 0


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
        "acquire_live_follow_up_capacity",
        lambda *_args, **_kwargs: lease,
    )
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **_kwargs: (
            (_ for _ in ()).throw(failure)
            if isinstance(failure, GeminiLiveTokenError)
            else _token()
        ),
    )
    monkeypatch.setattr(
        routes,
        "store_live_follow_up_session",
        lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(failure)
            if isinstance(failure, LiveFollowUpSessionStoreUnavailableError)
            else None
        ),
    )
    monkeypatch.setattr(
        routes,
        "release_live_follow_up_capacity",
        lambda _app, *, lease: released.append(lease),
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
        "acquire_live_follow_up_capacity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            LiveFollowUpCapacityLimitError("user")
        ),
    )
    monkeypatch.setattr(
        routes,
        "mint_gemini_live_ephemeral_token",
        lambda **_kwargs: pytest.fail("capacity rejection reached token mint"),
    )
    with pytest.raises(AppError):
        _post_session(app, _valid_payload())


def _stub_active_direct_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_args, **_kwargs: _stored_session(),
    )
    monkeypatch.setattr(
        routes,
        "touch_live_follow_up_session",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        routes,
        "reserve_live_follow_up_turn",
        lambda _app, *, session_bid, turn_index: LiveFollowUpTurnReservation(
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


def test_heartbeat_renews_only_the_control_plane_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    touched: list[str] = []
    monkeypatch.setattr(
        routes,
        "touch_live_follow_up_session",
        lambda _app, *, session_bid: touched.append(session_bid),
    )

    response = _post_action(app, "heartbeat")
    body = json.loads(response.get_data(as_text=True))["data"]
    assert body["session_bid"] == "session-1"
    assert touched == ["session-1"]


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

    def finish_predecessor(_seconds: float) -> None:
        nonlocal state
        state = LiveFollowUpTurnState(last_committed_index=1)

    def persist(
        _app: Flask, _context: object, turn: object
    ) -> LiveTurnPersistenceResult:
        persisted.append(turn.turn_index)
        return LiveTurnPersistenceResult(history_saved=True)

    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        lambda *_a, **_k: replace(_stored_session(), turn_state=state),
    )
    monkeypatch.setattr(
        routes, "commit_live_follow_up_turn_reservation", commit_reservation
    )
    monkeypatch.setattr(routes.time, "sleep", finish_predecessor)
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


def test_finalize_does_not_steal_an_in_flight_claim_or_wait_without_a_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _route_app(monkeypatch)
    _stub_active_direct_session(monkeypatch)
    session = replace(
        _stored_session(),
        turn_state=LiveFollowUpTurnState(
            pending_index=1, pending_claim="normal-request"
        ),
    )
    times = iter([0.0, 6.0])
    monkeypatch.setattr(
        routes, "load_live_follow_up_session", lambda *_a, **_k: session
    )
    monkeypatch.setattr(routes.time, "monotonic", lambda: next(times))
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
    with pytest.raises(AppError):
        _post_action(app, "finalize", {"turns": [_turn_report(1)]})


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
        "release_live_follow_up_capacity",
        lambda *_args, **_kwargs: pytest.fail("disclosed token capacity released"),
    )

    response = _post_action(app, "end", {"reason": "ended_by_user"})
    body = json.loads(response.get_data(as_text=True))["data"]
    assert body == {"session_bid": "session-1", "reason": "ended_by_user"}
    assert consumed == ["session-1"]

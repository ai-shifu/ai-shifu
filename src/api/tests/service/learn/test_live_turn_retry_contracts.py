"""Reject unavailable live sessions and replay only durable retired turns."""

import json
from unittest.mock import Mock

import pytest
from flask import request
from flaskr.service.common.models import AppError
from flaskr.service.learn import live_follow_up_routes as routes
from flaskr.service.learn.live_follow_up_capacity import (
    LiveFollowUpCapacityUnavailableError,
)
from flaskr.service.learn.live_follow_up_persistence import LiveTurnPersistenceResult
from flaskr.service.learn.live_follow_up_session_store import (
    LiveFollowUpSessionRejectedError,
    LiveFollowUpSessionStoreUnavailableError,
)

from . import test_live_follow_up_routes as existing

prevent_background_startup_threads = existing.prevent_background_startup_threads


@pytest.mark.parametrize("turn_index", [1, 2, 3])
def test_retirement_receipt_replays_durable_turn_without_authorizing_new_writes(
    monkeypatch: pytest.MonkeyPatch, turn_index: int
) -> None:
    app = existing._route_app(monkeypatch)
    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        Mock(side_effect=LiveFollowUpSessionRejectedError()),
    )
    receipt = Mock(return_value={"last_committed_index": 2})
    monkeypatch.setattr(routes, "retirement_receipt", receipt)
    replay = Mock(
        return_value=LiveTurnPersistenceResult(
            history_saved=True,
            ask_element_bid="ask-saved",
            answer_element_bid="answer-saved",
        )
    )
    monkeypatch.setattr(routes, "load_persisted_live_follow_up_turn", replay)
    persist, touch, reserve = Mock(), Mock(), Mock()
    monkeypatch.setattr(routes, "persist_live_follow_up_turn", persist)
    monkeypatch.setattr(routes, "touch_live_follow_up_session", touch)
    monkeypatch.setattr(routes, "reserve_live_follow_up_turn", reserve)
    if turn_index > 2:
        with pytest.raises(AppError):
            existing._post_action(app, "turn", existing._turn_report(turn_index))
        replay.assert_not_called()
    else:
        response = existing._post_action(app, "turn", existing._turn_report(turn_index))
        assert response.get_json()["data"] == {
            "session_bid": "session-1",
            "turn_index": turn_index,
            "history_saved": True,
            "ask_element_bid": "ask-saved",
            "answer_element_bid": "answer-saved",
        }
        replay.assert_called_once_with("session-1", turn_index)
    receipt.assert_called_once_with(
        app,
        user_bid="user-1",
        origin="https://learn.example.com",
        session_bid="session-1",
    )
    persist.assert_not_called()
    touch.assert_not_called()
    reserve.assert_not_called()


def test_heartbeat_admission_outage_reports_unavailable_without_touching_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = existing._route_app(monkeypatch)
    session = existing._v2_session()
    monkeypatch.setattr(
        routes, "load_live_follow_up_session", Mock(return_value=session)
    )
    current = Mock(side_effect=LiveFollowUpCapacityUnavailableError())
    monkeypatch.setattr(routes, "current_admission", current)
    touch = Mock()
    monkeypatch.setattr(routes, "touch_live_follow_up_session", touch)
    assert existing._post_action(app, "heartbeat").get_json()["data"] == {
        "session_bid": "session-1",
        "operation_status": "rejected",
        "error_code": "admission_unavailable",
    }
    current.assert_called_once_with(
        app,
        session.admission,
        session_bid="session-1",
        admission_revision="revision-1",
    )
    touch.assert_not_called()


@pytest.mark.parametrize("action", ["heartbeat", "turn", "finalize", "end"])
@pytest.mark.parametrize(
    "error",
    [LiveFollowUpCapacityUnavailableError, LiveFollowUpSessionStoreUnavailableError],
)
def test_session_touch_failure_stops_turn_writes_and_retirement(
    monkeypatch: pytest.MonkeyPatch, action: str, error: type[Exception]
) -> None:
    app = existing._route_app(monkeypatch)
    monkeypatch.setattr(
        routes,
        "load_live_follow_up_session",
        Mock(return_value=existing._v2_session()),
    )
    monkeypatch.setattr(
        routes, "touch_live_follow_up_session", Mock(side_effect=error())
    )
    monkeypatch.setattr(routes, "current_admission", Mock(return_value=True))
    monkeypatch.setattr(routes, "admission_time", lambda: 100)
    persist, consume, reserve = Mock(), Mock(), Mock()
    monkeypatch.setattr(routes, "persist_live_follow_up_turn", persist)
    monkeypatch.setattr(routes, "consume_live_follow_up_session", consume)
    monkeypatch.setattr(routes, "reserve_live_follow_up_turn", reserve)
    payload = {
        "heartbeat": {},
        "turn": existing._turn_report(1),
        "finalize": {"turns": [existing._turn_report(1)]},
        "end": {"reason": "ended_by_user"},
    }[action]
    with pytest.raises(AppError):
        existing._post_action(app, action, payload)
    persist.assert_not_called()
    consume.assert_not_called()
    reserve.assert_not_called()


@pytest.mark.parametrize("raw", [b"\xff", b"{broken", b"[]", b"null"])
def test_malformed_turn_payload_is_rejected_before_session_lookup(
    monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    app = existing._route_app(monkeypatch)
    load = Mock()
    monkeypatch.setattr(routes, "load_live_follow_up_session", load)
    with pytest.raises(AppError):
        app.test_client().post(
            "/api/learn/live-follow-up/session/session-1/turn",
            data=raw,
            content_type="application/json",
            base_url="https://learn.example.com",
            headers={"Origin": "https://learn.example.com"},
        )
    load.assert_not_called()


def test_oversized_usage_metadata_is_rejected_before_session_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = existing._route_app(monkeypatch)
    load = Mock()
    monkeypatch.setattr(routes, "load_live_follow_up_session", load)
    payload = existing._turn_report(1)
    # UTF-8 fits the body limit while escaped metadata exceeds its own budget.
    payload["usage_metadata"] = {"extra": "文" * 11000}
    raw = json.dumps(payload, ensure_ascii=False).encode()
    assert len(raw) < routes._MAX_DIRECT_TURN_REPORT_BYTES
    with pytest.raises(AppError):
        app.test_client().post(
            "/api/learn/live-follow-up/session/session-1/turn",
            data=raw,
            content_type="application/json",
            base_url="https://learn.example.com",
            headers={"Origin": "https://learn.example.com"},
        )
    load.assert_not_called()


@pytest.mark.parametrize("case", ["missing-user", "long-session"])
def test_direct_session_requires_authenticated_user_and_bounded_identifier(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    app = existing._route_app(monkeypatch)
    if case == "missing-user":

        @app.before_request
        def remove_user() -> None:
            request.user = None

    load = Mock()
    monkeypatch.setattr(routes, "load_live_follow_up_session", load)
    session_bid = "x" * 65 if case == "long-session" else "session-1"
    with pytest.raises(AppError):
        app.test_client().post(
            f"/api/learn/live-follow-up/session/{session_bid}/heartbeat",
            json={},
            base_url="https://learn.example.com",
            headers={"Origin": "https://learn.example.com"},
        )
    load.assert_not_called()

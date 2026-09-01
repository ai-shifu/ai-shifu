"""Verify one-time, Redis-only Gemini Live WebSocket tickets."""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from flaskr import dao
from flaskr.service.learn import live_follow_up_security as security


class FakeRedis:
    """Minimal Redis implementation for ticket issue and atomic consume."""

    def __init__(self) -> None:
        """Initialize the stored ticket records and SET call history."""
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int, bool]] = []

    def set(
        self,
        key: str,
        value: str,
        *,
        ex: int,
        nx: bool,
    ) -> bool:
        self.set_calls.append((key, value, ex, nx))
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script: object, numkeys: int, *args: object) -> str | None:
        assert script == security._CONSUME_TICKET_SCRIPT
        assert numkeys == 1
        return self.values.pop(str(args[0]), None)


class ExplodingRedis:
    """Simulate Redis being unavailable for both supported operations."""

    def set(self, *_args: object, **_kwargs: object) -> None:
        message = "redis unavailable"
        raise RuntimeError(message)

    def eval(self, *_args: object, **_kwargs: object) -> None:
        message = "redis unavailable"
        raise RuntimeError(message)


def _binding(**overrides: object) -> security.LiveFollowUpTicketBinding:
    values: dict[str, object] = {
        "session_bid": "session-1",
        "user_bid": "user-1",
        "shifu_bid": "course-1",
        "outline_bid": "chapter-1",
        "anchor_element_bid": "element-1",
        "progress_record_bid": "progress-1",
        "preview_mode": False,
        "origin": "https://learn.example.com",
        "model": "gemini-3.1-flash-live-preview",
        "voice_name": "Kore",
        "language": "zh-CN",
        "learning_mode": "read",
    }
    values.update(overrides)
    return security.LiveFollowUpTicketBinding(**values)  # type: ignore[arg-type]


def test_ticket_is_256_bit_hashed_and_short_lived(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)

    issued = security.issue_live_follow_up_ticket(app, binding=_binding())

    padded = issued.token + "=" * (-len(issued.token) % 4)
    assert len(base64.urlsafe_b64decode(padded)) == 32
    assert len(fake.set_calls) == 1
    _key, stored, ttl, nx = fake.set_calls[0]
    assert ttl == security.LIVE_FOLLOW_UP_TICKET_TTL_SECONDS
    assert nx is True
    assert issued.token not in stored
    record = json.loads(stored)
    assert (
        record["ticket_hash"]
        == hashlib.sha256(issued.token.encode("utf-8")).hexdigest()
    )
    assert record["binding"]["origin"] == "https://learn.example.com"


def test_ticket_consumption_returns_exact_binding_and_is_single_use(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    expected = _binding(preview_mode=True)
    issued = security.issue_live_follow_up_ticket(app, binding=expected)

    actual = security.consume_live_follow_up_ticket(
        app,
        session_bid=expected.session_bid,
        token=issued.token,
        origin=expected.origin,
    )

    assert actual == expected
    with pytest.raises(security.LiveFollowUpTicketRejectedError):
        security.consume_live_follow_up_ticket(
            app,
            session_bid=expected.session_bid,
            token=issued.token,
            origin=expected.origin,
        )


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [
        ("origin", "https://other.example.com"),
        ("token", "wrong-ticket"),
        ("session_bid", "other-session"),
    ],
)
def test_ticket_rejects_mismatched_handshake_binding(
    app: object,
    monkeypatch: object,
    field: str,
    wrong_value: str,
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    binding = _binding()
    issued = security.issue_live_follow_up_ticket(app, binding=binding)
    values = {
        "session_bid": binding.session_bid,
        "token": issued.token,
        "origin": binding.origin,
    }
    values[field] = wrong_value

    with pytest.raises(security.LiveFollowUpTicketRejectedError):
        security.consume_live_follow_up_ticket(app, **values)


def test_origin_mismatch_consumes_ticket_atomically(
    app: object, monkeypatch: object
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake)
    binding = _binding()
    issued = security.issue_live_follow_up_ticket(app, binding=binding)

    with pytest.raises(security.LiveFollowUpTicketRejectedError):
        security.consume_live_follow_up_ticket(
            app,
            session_bid=binding.session_bid,
            token=issued.token,
            origin="https://other.example.com",
        )
    with pytest.raises(security.LiveFollowUpTicketRejectedError):
        security.consume_live_follow_up_ticket(
            app,
            session_bid=binding.session_bid,
            token=issued.token,
            origin=binding.origin,
        )


@pytest.mark.parametrize(
    "origin",
    ["", "null", "https://user@example.com", "https://example.com/path"],
)
def test_ticket_issue_rejects_non_origin_values(app: object, origin: str) -> None:
    with pytest.raises(security.LiveFollowUpTicketRejectedError):
        security.issue_live_follow_up_ticket(
            app,
            binding=_binding(origin=origin),
        )


@pytest.mark.parametrize("redis_client", [None, ExplodingRedis()])
def test_ticket_issue_fails_closed_without_redis(
    app: object, monkeypatch: object, redis_client: object
) -> None:
    monkeypatch.setattr(dao._redis_state, "client", redis_client)
    with pytest.raises(security.LiveFollowUpSecurityUnavailableError):
        security.issue_live_follow_up_ticket(app, binding=_binding())


@pytest.mark.parametrize("redis_client", [None, ExplodingRedis()])
def test_ticket_consume_fails_closed_without_redis(
    app: object, monkeypatch: object, redis_client: object
) -> None:
    monkeypatch.setattr(dao._redis_state, "client", redis_client)
    with pytest.raises(security.LiveFollowUpSecurityUnavailableError):
        security.consume_live_follow_up_ticket(
            app,
            session_bid="session-1",
            token="ticket",
            origin="https://learn.example.com",
        )

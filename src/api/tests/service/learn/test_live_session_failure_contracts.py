"""Reject corrupt session bindings and fail closed on uncertain Redis writes."""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.learn import live_follow_up_session_store as store
from flaskr.service.learn.live_follow_up_admission import AdmissionRequest
from flaskr.service.learn.live_follow_up_capacity import LiveFollowUpCapacityLease


@pytest.fixture
def storage(monkeypatch: object) -> object:
    binding = store.LiveFollowUpSessionBinding(
        session_bid="session",
        user_bid="user",
        shifu_bid="course",
        outline_bid="outline",
        anchor_element_bid="anchor",
        progress_record_bid="progress",
        preview_mode=False,
        origin="https://learn.example.test",
        model="live-model",
        voice_name="Kore",
        language="en-US",
        learning_mode="read",
        expires_at_epoch=2000,
    )
    session = store.StoredLiveFollowUpSession(
        binding=binding,
        lease=LiveFollowUpCapacityLease(
            lease_id="lease", user_bid="user", worker_id="worker"
        ),
    )
    redis = Mock()
    monkeypatch.setattr(store, "_redis_client", lambda: redis)
    return SimpleNamespace(app=Flask(__name__), session=session, redis=redis)


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        b"\xff",
        "[]",
        "null",
        "{}",
        '{"version": 1}',
        '{"version": 2, "binding": []}',
    ],
)
def test_invalid_cached_session_is_rejected_without_refreshing_it(
    storage: object, raw: object
) -> None:
    storage.redis.get.return_value = raw
    with pytest.raises(store.LiveFollowUpSessionRejectedError, match="invalid_session"):
        store.load_live_follow_up_session(
            storage.app, session_bid="session", current_time=1000
        )
    storage.redis.set.assert_not_called()
    storage.redis.eval.assert_not_called()


@pytest.mark.parametrize(
    ("group", "field", "invalid"),
    [
        ("binding", "session_bid", "another-session"),
        ("binding", "user_bid", ""),
        ("binding", "preview_mode", 1),
        ("binding", "expires_at_epoch", "2000"),
        ("lease", "lease_id", ""),
        ("turn_state", "last_committed_index", True),
        ("turn_state", "last_committed_index", -1),
        ("turn_state", "last_committed_index", 201),
        ("turn_state", "pending_claim", "orphaned-claim"),
        ("turn_state", "pending_claim", 1),
        ("turn_state", "pending_claim", "x" * 129),
        ("turn_state", "pending_index", 1),
        ("turn_state", "pending_index", True),
    ],
)
def test_session_schema_rejects_corrupt_identity_and_turn_order(
    storage: object, group: str, field: str, invalid: object
) -> None:
    record = json.loads(store.serialize_live_follow_up_session(storage.session))
    record[group][field] = invalid
    storage.redis.get.return_value = json.dumps(record)
    with pytest.raises(store.LiveFollowUpSessionRejectedError, match="invalid_session"):
        store.load_live_follow_up_session(
            storage.app, session_bid="session", current_time=1000
        )


def test_valid_pending_turn_round_trips_without_losing_its_claim(
    storage: object,
) -> None:
    pending = replace(
        storage.session,
        turn_state=store.LiveFollowUpTurnState(
            last_committed_index=3, pending_index=4, pending_claim="claim"
        ),
    )
    storage.redis.get.return_value = store.serialize_live_follow_up_session(
        pending
    ).encode()
    assert (
        store.load_live_follow_up_session(
            storage.app, session_bid="session", current_time=1000
        )
        == pending
    )


def test_empty_session_identifier_fails_before_reading_redis(storage: object) -> None:
    with pytest.raises(store.LiveFollowUpSessionRejectedError, match="invalid_session"):
        store.load_live_follow_up_session(storage.app, session_bid="")
    storage.redis.get.assert_not_called()


@pytest.mark.parametrize(
    "operation", ["store", "load", "touch", "reserve", "commit", "release", "consume"]
)
@pytest.mark.parametrize("failure", ["transport", "missing-client"])
def test_redis_uncertainty_is_exposed_as_store_unavailability(
    storage: object, monkeypatch: object, operation: str, failure: str
) -> None:
    if failure == "missing-client":
        monkeypatch.setattr(store, "_redis_client", lambda: None)
    else:
        for method in (storage.redis.set, storage.redis.get, storage.redis.eval):
            method.side_effect = ConnectionError("unreachable")
    reservation = store.LiveFollowUpTurnReservation("session", 1, "claim")
    actions = {
        "store": lambda: store.store_live_follow_up_session(
            storage.app, session=storage.session
        ),
        "load": lambda: store.load_live_follow_up_session(
            storage.app, session_bid="session"
        ),
        "touch": lambda: store.touch_live_follow_up_session(
            storage.app, session_bid="session"
        ),
        "reserve": lambda: store.reserve_live_follow_up_turn(
            storage.app, session_bid="session", turn_index=1
        ),
        "commit": lambda: store.commit_live_follow_up_turn_reservation(
            storage.app, reservation=reservation
        ),
        "release": lambda: store.release_live_follow_up_turn_reservation(
            storage.app, reservation=reservation
        ),
        "consume": lambda: store.consume_live_follow_up_session(
            storage.app, session_bid="session"
        ),
    }
    with pytest.raises(
        store.LiveFollowUpSessionStoreUnavailableError, match="redis_unavailable"
    ):
        actions[operation]()


@pytest.mark.parametrize("result", [None, "bad-status", []])
def test_malformed_redis_reservation_result_cannot_advance_a_turn(
    storage: object, result: object
) -> None:
    storage.redis.eval.return_value = result
    with pytest.raises(
        store.LiveFollowUpSessionStoreUnavailableError, match="redis_unavailable"
    ):
        store.reserve_live_follow_up_turn(
            storage.app, session_bid="session", turn_index=1
        )


def test_existing_session_key_is_not_overwritten(storage: object) -> None:
    storage.redis.set.return_value = False
    with pytest.raises(
        store.LiveFollowUpSessionStoreUnavailableError, match="session_not_stored"
    ):
        store.store_live_follow_up_session(storage.app, session=storage.session)
    assert storage.redis.set.call_args.kwargs["nx"] is True


def test_admitted_session_uses_redis_clock_and_rejects_uncertain_time(
    storage: object, monkeypatch: object
) -> None:
    admitted = replace(
        storage.session,
        admission=AdmissionRequest(
            request_bid="request",
            user_bid="user",
            origin="https://learn.example.test",
            shifu_bid="course",
            outline_bid="outline",
            anchor_element_bid="anchor",
            preview_mode=False,
            learning_mode="read",
            surface="read_content",
        ),
        admission_revision="revision",
    )
    storage.redis.get.return_value = store.serialize_live_follow_up_session(admitted)
    clock = Mock(side_effect=[1000, ConnectionError("clock unavailable")])
    monkeypatch.setattr(store, "admission_time", clock)
    assert (
        store.load_live_follow_up_session(storage.app, session_bid="session")
        == admitted
    )
    with pytest.raises(
        store.LiveFollowUpSessionStoreUnavailableError, match="redis_unavailable"
    ):
        store.load_live_follow_up_session(storage.app, session_bid="session")
    assert clock.call_count == 2

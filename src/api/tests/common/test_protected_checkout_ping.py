"""Protected checkout liveness ping (pool_pre_ping replacement).

The stock pre-ping path has no BaseException protection: a GreenletExit in
COM_PING's recv leaks the checkout and the leaked fairy's GC finalizer later
emits a ROLLBACK that consumes the stale PING OK, leaving the connection
permanently off by one response. The checkout-event ping must invalidate the
record BEFORE any interruption propagates.
"""

import socket

import pytest
from flaskr import dao
from sqlalchemy.exc import DisconnectionError


class _FakeRecord:
    def __init__(self) -> None:
        self.invalidated_with = []

    def invalidate(self, e: object = None):
        self.invalidated_with.append(e)


class _FakeGreenletExit(BaseException):
    pass


def _make_conn(sock: object, ping_exc: object = None):
    class _Conn:
        _sock = sock

        def ping(self, reconnect: object):
            assert reconnect is False
            if ping_exc is not None:
                raise ping_exc

    return _Conn()


@pytest.fixture
def clean_sock() -> object:
    left, right = socket.socketpair()
    yield left
    left.close()
    right.close()


def test_healthy_ping_passes(clean_sock: object) -> None:
    record = _FakeRecord()
    dao._reject_desynced_connection_on_checkout(_make_conn(clean_sock), record, None)
    assert record.invalidated_with == []


def test_dead_connection_ping_invalidates_and_retries(clean_sock: object) -> None:
    record = _FakeRecord()
    ping_exc = OSError("dead")
    with pytest.raises(DisconnectionError):
        dao._reject_desynced_connection_on_checkout(
            _make_conn(clean_sock, ping_exc), record, None
        )
    assert record.invalidated_with == [ping_exc]


def test_interrupted_ping_invalidates_before_propagating(clean_sock: object) -> None:
    record = _FakeRecord()
    with pytest.raises(_FakeGreenletExit):
        dao._reject_desynced_connection_on_checkout(
            _make_conn(clean_sock, _FakeGreenletExit()), record, None
        )
    # Record invalidated (with e=None for non-Exception) BEFORE the
    # interruption propagates: the GC finalizer then sees an invalidated
    # record and never emits a ROLLBACK on the desynced wire.
    assert record.invalidated_with == [None]


def test_connections_without_ping_are_skipped(clean_sock: object) -> None:
    class _NoPing:
        _sock = clean_sock

    record = _FakeRecord()
    dao._reject_desynced_connection_on_checkout(_NoPing(), record, None)
    assert record.invalidated_with == []


def test_pre_ping_engine_option_defaults_off(app: object) -> None:
    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"].get("pool_pre_ping") is False

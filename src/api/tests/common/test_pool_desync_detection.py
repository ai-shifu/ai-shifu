"""Pool-level detection of desynced MySQL connections.

A connection whose protocol stream is desynced (an interrupted operation left
an unread response buffered) has readable bytes on its socket while idle.
The pool listeners in flaskr.dao must drop such connections instead of
recirculating them.
"""

import socket
from collections.abc import Iterator

import pytest
from flaskr import dao
from sqlalchemy.pool import QueuePool


class _FakePyMySQLConnection:
    """Minimal stand-in exposing the pymysql `_sock` attribute."""

    def __init__(self, sock: object) -> None:
        self._sock = sock
        self.closed = False

    # QueuePool reset/close hooks
    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
        self._sock.close()


@pytest.fixture
def sock_pair() -> Iterator[tuple[socket.socket, socket.socket]]:
    left, right = socket.socketpair()
    left.setblocking(False)  # noqa: FBT003 -- stdlib socket API
    yield left, right
    left.close()
    right.close()


def test_unread_data_detected(sock_pair: object) -> None:
    left, right = sock_pair
    conn = _FakePyMySQLConnection(left)
    assert dao._socket_has_unread_data(conn) is False

    right.sendall(b"\x01stale-packet")
    assert dao._socket_has_unread_data(conn) is True


def test_connection_without_socket_is_ignored() -> None:
    class _NoSock:
        pass

    assert dao._socket_has_unread_data(_NoSock()) is False


def test_unusable_socket_object_is_ignored() -> None:
    class _BadSock:
        # No fileno(): select.select raises TypeError for such objects.
        _sock = object()

    assert dao._socket_has_unread_data(_BadSock()) is False


def test_pool_discards_connection_desynced_during_use(sock_pair: object) -> None:
    left, right = sock_pair
    dirty_conn = _FakePyMySQLConnection(left)
    clean_sock_a, clean_sock_b = socket.socketpair()
    connections = [
        dirty_conn,
        _FakePyMySQLConnection(clean_sock_a),
    ]
    made = []

    def _creator() -> object:
        conn = connections[len(made) % len(connections)]
        made.append(conn)
        return conn

    pool = QueuePool(_creator, pool_size=1, max_overflow=0, reset_on_return=None)
    try:
        # First checkout hands out the (still clean) dirty_conn.
        fairy = pool.connect()
        assert fairy.dbapi_connection is dirty_conn

        # Simulate an interrupted exchange: the server response arrives but
        # is never consumed before the connection goes back to the pool.
        right.sendall(b"\x02unconsumed-response")
        fairy.close()  # checkin fires -> listener must invalidate

        # The poisoned connection must not be handed out again.
        fairy2 = pool.connect()
        assert fairy2.dbapi_connection is not dirty_conn
        fairy2.close()
        assert dirty_conn.closed is True
    finally:
        pool.dispose()
        clean_sock_b.close()


def test_checkout_rejects_connection_that_became_dirty_in_pool(
    sock_pair: object,
) -> None:
    left, right = sock_pair
    dirty_conn = _FakePyMySQLConnection(left)
    clean_sock_a, clean_sock_b = socket.socketpair()
    connections = [dirty_conn, _FakePyMySQLConnection(clean_sock_a)]
    made = []

    def _creator() -> object:
        conn = connections[len(made) % len(connections)]
        made.append(conn)
        return conn

    pool = QueuePool(_creator, pool_size=1, max_overflow=0, reset_on_return=None)
    try:
        fairy = pool.connect()
        fairy.close()  # goes back clean

        # Data arrives while the connection is parked in the pool (e.g. a
        # server-side abort). Checkout must reject it and hand out a fresh
        # connection transparently.
        right.sendall(b"\x03server-abort")
        fairy2 = pool.connect()
        assert fairy2.dbapi_connection is not dirty_conn
        fairy2.close()
        assert dirty_conn.closed is True
    finally:
        pool.dispose()
        clean_sock_b.close()


def test_probe_timeout_waits_for_in_flight_data(sock_pair: object) -> None:
    """A timed probe must catch data that arrives DURING the wait window: the zero-timeout probe misses an owed response still in flight, which is exactly how a just-interrupted exchange poisons the pool.

    A generous test window (far larger than any CI scheduler delay) keeps this
    deterministic; the early-return assertion proves the probe wakes on arrival rather than
    sleeping out the timeout.
    """
    import threading
    import time as time_module

    left, right = sock_pair
    conn = _FakePyMySQLConnection(left)

    # Zero-timeout probe sees nothing yet.
    assert dao._socket_has_unread_data(conn) is False

    def _late_send() -> None:
        time_module.sleep(0.001)
        right.sendall(b"\x05late-owed-response")

    sender = threading.Thread(target=_late_send)
    started = time_module.monotonic()
    sender.start()
    try:
        assert dao._socket_has_unread_data(conn, timeout=0.5) is True
        # Returned on arrival, not by exhausting the window.
        assert time_module.monotonic() - started < 0.5
    finally:
        sender.join()


def test_checkin_grace_window_is_a_short_positive_interval() -> None:
    # The production checkin window must stay a small positive value: zero
    # reintroduces the arrival race, and anything larger taxes every
    # transaction end. The bound is pinned to the current 2ms on purpose -
    # enlarging the window must be an explicit two-place change backed by a
    # latency budget, not a silent constant bump.
    assert 0 < dao._CHECKIN_PROBE_GRACE_SECONDS <= 0.002


class _FakePingablePyMySQLConnection(_FakePyMySQLConnection):
    """Fake with a healthy ping - the pymysql-shaped checkout path."""

    def __init__(self, sock: object) -> None:
        super().__init__(sock)
        self.pings = 0

    def ping(self, reconnect: object) -> None:
        _ = reconnect
        self.pings += 1


def test_checkout_appends_a_journal_boundary_marker() -> None:
    clean_a, clean_b = socket.socketpair()
    conn = _FakePingablePyMySQLConnection(clean_a)

    pool = QueuePool(lambda: conn, pool_size=1, max_overflow=0, reset_on_return=None)
    try:
        fairy = pool.connect()
        journal = list(fairy.info.get(dao._STATEMENT_JOURNAL_KEY, ()))
        # The journal survives checkin/checkout, so without boundary markers
        # one dump can silently mix statements from different requests.
        assert any(
            str(entry[0]).startswith(dao._CHECKOUT_BOUNDARY_MARKER) for entry in journal
        ), journal
        fairy.close()

        fairy2 = pool.connect()
        journal2 = list(fairy2.info.get(dao._STATEMENT_JOURNAL_KEY, ()))
        markers = [
            entry
            for entry in journal2
            if str(entry[0]).startswith(dao._CHECKOUT_BOUNDARY_MARKER)
        ]
        assert len(markers) == 2
        # The pymysql-shaped path reaches the marker AFTER a healthy ping.
        assert conn.pings == 2
        fairy2.close()
    finally:
        pool.dispose()
        clean_b.close()

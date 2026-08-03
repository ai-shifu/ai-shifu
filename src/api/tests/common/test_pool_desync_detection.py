"""Pool-level detection of desynced MySQL connections.

A connection whose protocol stream is desynced (an interrupted operation left
an unread response buffered) has readable bytes on its socket while idle.
The pool listeners in flaskr.dao must drop such connections instead of
recirculating them.
"""

import socket

import pytest
from sqlalchemy.pool import QueuePool

import flaskr.dao as dao


class _FakePyMySQLConnection:
    """Minimal stand-in exposing the pymysql `_sock` attribute."""

    def __init__(self, sock):
        self._sock = sock
        self.closed = False

    # QueuePool reset/close hooks
    def rollback(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture()
def sock_pair():
    left, right = socket.socketpair()
    left.setblocking(False)
    yield left, right
    left.close()
    right.close()


def test_unread_data_detected(sock_pair):
    left, right = sock_pair
    conn = _FakePyMySQLConnection(left)
    assert dao._socket_has_unread_data(conn) is False

    right.sendall(b"\x01stale-packet")
    assert dao._socket_has_unread_data(conn) is True


def test_connection_without_socket_is_ignored():
    class _NoSock:
        pass

    assert dao._socket_has_unread_data(_NoSock()) is False


def test_unusable_socket_object_is_ignored():
    class _BadSock:
        # No fileno(): select.select raises TypeError for such objects.
        _sock = object()

    assert dao._socket_has_unread_data(_BadSock()) is False


def test_pool_discards_connection_desynced_during_use(sock_pair):
    left, right = sock_pair
    dirty_conn = _FakePyMySQLConnection(left)
    clean_sock_a, clean_sock_b = socket.socketpair()
    connections = [
        dirty_conn,
        _FakePyMySQLConnection(clean_sock_a),
    ]
    made = []

    def _creator():
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


def test_checkout_rejects_connection_that_became_dirty_in_pool(sock_pair):
    left, right = sock_pair
    dirty_conn = _FakePyMySQLConnection(left)
    clean_sock_a, clean_sock_b = socket.socketpair()
    connections = [dirty_conn, _FakePyMySQLConnection(clean_sock_a)]
    made = []

    def _creator():
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

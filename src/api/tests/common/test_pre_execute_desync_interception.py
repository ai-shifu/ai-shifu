"""Pre-execute interception of off-by-one protocol desync.

Production forensics proved the desync arises within one connection: a
statement's response goes unread and every later command consumes the
previous command's response. The engine-level listeners must catch the
off-by-one at the first statement after it arises and name the interrupted
statement via the per-connection journal.
"""

import socket
from typing import ClassVar

import pytest
from flaskr import dao
from flaskr.dao import db
from sqlalchemy import text
from sqlalchemy.exc import DisconnectionError


def test_statement_journal_records_recent_statements(app):
    with app.app_context():
        db.session.execute(text("SELECT 1"))
        db.session.execute(text("SELECT 2"))
        connection = db.session.connection()
        journal = list(connection.info.get(dao._STATEMENT_JOURNAL_KEY) or [])
        db.session.rollback()

    statements = [entry[0] for entry in journal]
    assert any("SELECT 1" in s for s in statements)
    assert any("SELECT 2" in s for s in statements)


def test_pre_execute_probe_blocks_desynced_connection():
    left, right = socket.socketpair()
    try:

        class _FakeRaw:
            _sock = left

        class _FakeFairy:
            dbapi_connection = _FakeRaw()

        class _FakeConn:
            connection = _FakeFairy()
            info: ClassVar[dict[str, object]] = {}
            invalidated_count = 0

            def invalidate(self):
                type(self).invalidated_count += 1

        conn = _FakeConn()

        # Clean socket: probe passes.
        dao._intercept_desync_before_execute(
            conn, None, "SELECT 1", None, None, executemany=False
        )

        # An unread response appears (interrupted previous exchange): the
        # next execute must be refused and the connection invalidated.
        right.sendall(b"\x07\x00\x00\x01\x00stale")
        with pytest.raises(DisconnectionError):
            dao._intercept_desync_before_execute(
                conn, None, "SELECT id FROM t", None, None, executemany=False
            )
        assert _FakeConn.invalidated_count == 1
    finally:
        left.close()
        right.close()


def test_pre_execute_probe_ignores_drivers_without_socket(app):
    # SQLite connections expose no _sock; the whole suite running on SQLite
    # exercises this path implicitly, but assert the direct call is a no-op.
    with app.app_context():
        connection = db.session.connection()
        dbapi_connection = connection.connection.dbapi_connection
        assert dao._socket_has_unread_data(dbapi_connection) is False
        db.session.rollback()

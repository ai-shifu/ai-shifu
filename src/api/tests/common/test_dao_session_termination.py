"""Termination classification and session invalidation contract.

Core of the connection-desync fix: terminations that may have interrupted a
DB exchange must discard the connection (Session.invalidate), while
server-delivered errors keep the legacy rollback. Also pins the
scoped_session proxy gap that silently no-op'ed the first version of this
fix in production: scoped_session does NOT forward ``invalidate``, so the
helper must resolve the real Session via the registry call form.
"""

import logging

import pytest
from sqlalchemy import text
from sqlalchemy.exc import (
    DisconnectionError,
    IntegrityError,
    OperationalError,
    ResourceClosedError,
)

from flaskr.dao import (
    cleanup_session_after,
    db,
    invalidate_session,
    is_abnormal_stream_termination,
    is_protocol_interrupt_error,
)


class _FakeGreenletExit(BaseException):
    pass


def _operational(errno: int) -> OperationalError:
    exc = OperationalError("STMT", {}, Exception())
    exc.orig.args = (errno, "message")
    return exc


@pytest.mark.parametrize(
    "exc,expected",
    [
        (GeneratorExit(), True),
        (_FakeGreenletExit(), True),
        (ResourceClosedError("no rows"), True),
        (DisconnectionError("desynced"), True),
        (_operational(2013), True),
        (_operational(2014), True),
        (Exception(2014, "raw pymysql Command Out of Sync"), True),
        (None, False),
        (ValueError("business"), False),
        (IntegrityError("STMT", {}, Exception()), False),
        (_operational(1213), False),
        (_operational(1205), False),
    ],
)
def test_abnormal_termination_classification(exc, expected):
    assert is_abnormal_stream_termination(exc) is expected


def test_protocol_interrupt_checks_orig_and_self():
    assert is_protocol_interrupt_error(_operational(2014)) is True
    assert is_protocol_interrupt_error(Exception(2013, "raw")) is True
    assert is_protocol_interrupt_error(_operational(1213)) is False


def test_scoped_session_does_not_proxy_invalidate():
    # This gap is WHY invalidate_session must resolve the real Session via
    # the registry call form: db.session.invalidate() raises AttributeError
    # and, wrapped in a broad except, silently does nothing (the production
    # no-op that kept the desync alive through an entire fix generation).
    assert not hasattr(db.session, "invalidate")


def test_invalidate_session_works_on_real_scoped_session(app, caplog):
    with app.app_context():
        db.session.execute(text("SELECT 1"))
        with caplog.at_level(logging.WARNING):
            assert invalidate_session(source="test real scoped") is True
    assert "invalidate failed" not in caplog.text


def test_invalidate_session_uses_fake_sessions_directly():
    calls = []

    class _Fake:
        def invalidate(self):
            calls.append(1)

    assert invalidate_session(source="test fake", session=_Fake()) is True
    assert calls == [1]


def test_cleanup_rolls_back_on_server_delivered_errors():
    events = []

    class _Fake:
        def invalidate(self):
            events.append("invalidate")

        def rollback(self):
            events.append("rollback")

    outcome = cleanup_session_after(ValueError("business"), source="t", session=_Fake())
    assert outcome == "rolled_back"
    assert events == ["rollback"]


def test_cleanup_invalidates_on_interrupting_terminations():
    events = []

    class _Fake:
        def invalidate(self):
            events.append("invalidate")

        def rollback(self):
            events.append("rollback")

    outcome = cleanup_session_after(GeneratorExit(), source="t", session=_Fake())
    assert outcome == "invalidated"
    assert events == ["invalidate"]


def test_cleanup_escalates_to_invalidate_when_rollback_fails():
    events = []

    class _Fake:
        def invalidate(self):
            events.append("invalidate")

        def rollback(self):
            events.append("rollback")
            raise RuntimeError("rollback broke")

    outcome = cleanup_session_after(ValueError("business"), source="t", session=_Fake())
    assert outcome == "invalidated"
    assert events == ["rollback", "invalidate"]

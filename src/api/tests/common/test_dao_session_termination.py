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
from flaskr.dao import (
    cleanup_session_after,
    db,
    invalidate_session,
    is_abnormal_stream_termination,
    is_protocol_interrupt_error,
)
from sqlalchemy import text
from sqlalchemy.exc import (
    DisconnectionError,
    IntegrityError,
    OperationalError,
    ResourceClosedError,
)
from sqlalchemy.orm.exc import FlushError


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
        # An INSERT that "succeeds" without an autoincrement id read some
        # other statement's response: off-by-one evidence, must invalidate.
        (FlushError("Instance <X> has a NULL identity key."), True),
        (FlushError("New instance with identity key already present"), False),
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


def test_teardown_hook_invalidates_before_session_removal(app, monkeypatch):
    """The global teardown guard must fire on abnormal context exits and run
    BEFORE Flask-SQLAlchemy's remove (reverse registration order).
    """
    import flaskr.dao as dao

    order = []
    monkeypatch.setattr(
        dao,
        "invalidate_session",
        lambda *, source, session=None: order.append(f"invalidate:{source}") or True,
    )
    original_remove = db.session.remove

    def _tracking_remove():
        order.append("remove")
        return original_remove()

    monkeypatch.setattr(db.session, "remove", _tracking_remove)

    class _Interrupt(BaseException):
        pass

    with pytest.raises(_Interrupt):
        with app.app_context():
            raise _Interrupt()

    assert order[0] == "invalidate:appcontext teardown interrupt"
    assert "remove" in order


def test_teardown_hook_ignores_ordinary_exceptions(app, monkeypatch):
    import flaskr.dao as dao

    invalidations = []
    monkeypatch.setattr(
        dao,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
    )

    with pytest.raises(ValueError):
        with app.app_context():
            raise ValueError("business")

    assert invalidations == []


def test_release_session_classified_invalidates_during_propagating_interrupt(
    app, monkeypatch
):
    import flaskr.dao as dao

    order = []
    monkeypatch.setattr(
        dao,
        "invalidate_session",
        lambda *, source, session=None: order.append("invalidate") or True,
    )
    original_remove = db.session.remove
    monkeypatch.setattr(
        db.session,
        "remove",
        lambda: order.append("remove") or original_remove(),
    )

    class _Interrupt(BaseException):
        pass

    with app.app_context():
        try:
            raise _Interrupt()
        except _Interrupt:
            pass
        # No in-flight exception here: plain removal, no invalidate.
        dao.release_session_classified(source="t-clean")
        assert order == ["remove"]
        order.clear()

        try:
            try:
                raise _Interrupt()
            finally:
                # In-flight BaseException visible via sys.exc_info in finally:
                # invalidate must run BEFORE removal, otherwise remove() emits
                # a ROLLBACK on the desynced stream.
                dao.release_session_classified(source="t-interrupt")
        except _Interrupt:
            pass

        # Assert inside the context: the context exit's own teardown removes
        # would otherwise append extra entries.
        assert order == ["invalidate", "remove"]


def test_release_session_classified_ignores_ordinary_exceptions(app, monkeypatch):
    import flaskr.dao as dao

    invalidations = []
    monkeypatch.setattr(
        dao,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
    )

    with app.app_context():
        try:
            try:
                raise ValueError("business")
            finally:
                dao.release_session_classified(source="t-ordinary")
        except ValueError:
            pass

    assert invalidations == []


def test_classifier_covers_driver_interface_and_socket_errors():
    class _DriverInterfaceError(Exception):
        pass

    _DriverInterfaceError.__name__ = "InterfaceError"

    from sqlalchemy.exc import InterfaceError as SAInterfaceError

    assert (
        is_protocol_interrupt_error(SAInterfaceError("stmt", {}, Exception())) is True
    )
    assert is_protocol_interrupt_error(_DriverInterfaceError()) is True
    assert is_protocol_interrupt_error(BrokenPipeError(32, "broken pipe")) is True
    assert is_protocol_interrupt_error(ConnectionResetError(104, "reset")) is True
    wrapped = OperationalError("stmt", {}, BrokenPipeError(32, "broken pipe"))
    assert is_protocol_interrupt_error(wrapped) is True
    assert is_protocol_interrupt_error(ValueError("business")) is False

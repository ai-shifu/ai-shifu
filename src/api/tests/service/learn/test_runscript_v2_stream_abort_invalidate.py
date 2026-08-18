"""Abnormal stream termination must discard the DB connection, not pool it.

The pool-level desync detector (flaskr/dao checkin/checkout probes) caught a
production connection returned with unread protocol data from exactly this
path: producer ``res.close()`` -> ``except GeneratorExit`` ->
``db.session.rollback()``. Rolling back on a connection whose protocol state
is unknown consumes stale packets and re-pools a poisoned stream; the probes
only see stale bytes that have already arrived at the socket, so they cannot
close the arrival race. These tests pin the deterministic fix: GeneratorExit
and protocol-desync errors invalidate the session's connection instead of
rolling back on it.
"""

import types

import pytest
from flaskr.service.learn import runscript_v2
from flaskr.service.learn.runscript_v2 import (
    _is_protocol_desync_error,
    run_script_inner,
)
from sqlalchemy.exc import OperationalError, ResourceClosedError


class _FakeSession:
    def __init__(self):
        self.rollbacks = 0
        self.commits = 0
        self.invalidations = 0
        self.removed = 0

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        self.commits += 1

    def invalidate(self):
        self.invalidations += 1

    def remove(self):
        self.removed += 1


class _StubRunContext:
    """Yields scripted items (or raises) through run(); has_next() once."""

    script: list = []

    def __init__(self, **_kwargs):
        self._steps = iter([True, False])

    def set_input(self, *_args, **_kwargs):
        pass

    def has_next(self):
        return next(self._steps, False)

    def run(self, _app):
        for item in type(self).script:
            if isinstance(item, BaseException):
                raise item
            yield item


def _patch_run_dependencies(monkeypatch, script):
    session = _FakeSession()

    class _FakeDb:
        pass

    _FakeDb.session = session
    monkeypatch.setattr(runscript_v2, "db", _FakeDb)
    monkeypatch.setattr(
        runscript_v2, "_ensure_healthy_db_connection", lambda _app: None
    )
    monkeypatch.setattr(
        runscript_v2,
        "load_user_aggregate",
        lambda _bid: types.SimpleNamespace(user_id="user-1"),
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_outline_item_dto",
        lambda _app, _bid, _preview: types.SimpleNamespace(
            bid="outline-1", shifu_bid="shifu-1", __json__=dict
        ),
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_shifu_dto",
        lambda _app, _bid, _preview: types.SimpleNamespace(bid="shifu-1", price=0),
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_shifu_struct",
        lambda _app, _bid, _preview: types.SimpleNamespace(bid="shifu-1"),
    )
    _StubRunContext.script = list(script)
    monkeypatch.setattr(runscript_v2, "RunScriptContextV2", _StubRunContext)
    return session


def _start_stream(app):
    generator = run_script_inner(
        app=app,
        user_bid="user-1",
        shifu_bid="shifu-1",
        outline_bid="outline-1",
        manage_app_context=False,
    )
    assert next(generator) == "chunk-1"
    return generator


def test_generator_exit_invalidates_connection_instead_of_rollback(app, monkeypatch):
    session = _patch_run_dependencies(monkeypatch, ["chunk-1", "chunk-2"])

    with app.app_context():
        generator = _start_stream(app)
        generator.close()

    assert session.invalidations == 1
    assert session.rollbacks == 0
    assert session.removed == 1


def test_desync_error_invalidates_connection_instead_of_rollback(app, monkeypatch):
    session = _patch_run_dependencies(
        monkeypatch,
        [
            "chunk-1",
            ResourceClosedError(
                "This result object does not return rows. "
                "It has been closed automatically."
            ),
        ],
    )

    with app.app_context():
        generator = _start_stream(app)
        with pytest.raises(ResourceClosedError):
            next(generator)

    # Exactly two invalidations - one from the desync except branch, one
    # from the classified finally-release (idempotent defense in depth). A
    # drop to one means one of the two layers regressed; zero rollbacks on
    # the desynced stream is the hard contract.
    assert session.invalidations == 2
    assert session.rollbacks == 0
    assert session.removed == 1


def test_ordinary_error_still_rolls_back_pooled_connection(app, monkeypatch):
    session = _patch_run_dependencies(
        monkeypatch, ["chunk-1", ValueError("business failure")]
    )

    with app.app_context():
        generator = _start_stream(app)
        with pytest.raises(ValueError):
            next(generator)

    assert session.invalidations == 0
    assert session.rollbacks == 1
    assert session.removed == 1


def test_desync_error_classifier_covers_symptom_family():
    assert _is_protocol_desync_error(ResourceClosedError("no rows"))
    wrapped_2013 = OperationalError(
        "INSERT ...",
        {},
        Exception(2013, "Lost connection to MySQL server during query"),
    )
    wrapped_2013.orig.args = (2013, "Lost connection to MySQL server during query")
    assert _is_protocol_desync_error(wrapped_2013)
    raw_2014 = Exception(2014, "Command Out of Sync")
    assert _is_protocol_desync_error(raw_2014)
    assert not _is_protocol_desync_error(ValueError("boom"))
    wrapped_deadlock = OperationalError("UPDATE ...", {}, Exception())
    wrapped_deadlock.orig.args = (1213, "Deadlock found")
    assert not _is_protocol_desync_error(wrapped_deadlock)


def test_stop_event_cancellation_invalidates_instead_of_rollback(app, monkeypatch):
    import threading

    session = _patch_run_dependencies(monkeypatch, ["chunk-1"])

    class _TwoRoundContext(_StubRunContext):
        # Two has_next rounds so the stop_event check at the loop boundary
        # fires between them.
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            # Each loop round consumes TWO steps: the while condition and the
            # has_next() call inside the log line.
            self._steps = iter([True, True, True, True, False])

    monkeypatch.setattr(runscript_v2, "RunScriptContextV2", _TwoRoundContext)
    stop_event = threading.Event()

    with app.app_context():
        generator = run_script_inner(
            app=app,
            user_bid="user-1",
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            manage_app_context=False,
            stop_event=stop_event,
        )
        assert next(generator) == "chunk-1"
        # Cancellation between events: semantically a client walk-away.
        stop_event.set()
        with pytest.raises(StopIteration):
            next(generator)

    assert session.invalidations == 1
    assert session.rollbacks == 0


def test_natural_exhaustion_never_invalidates(app, monkeypatch):
    session = _patch_run_dependencies(monkeypatch, ["chunk-1", "chunk-2"])

    with app.app_context():
        generator = _start_stream(app)
        remaining = list(generator)

    assert remaining == ["chunk-2"]
    assert session.invalidations == 0
    assert session.rollbacks == 0
    assert session.commits >= 1


def test_discard_helper_works_on_real_scoped_session(app, caplog):
    import logging

    from flaskr.service.learn.runscript_v2 import _discard_session_connection

    with app.app_context():
        with caplog.at_level(logging.WARNING):
            _discard_session_connection(app, source="real session smoke")
    assert "invalidate failed" not in caplog.text

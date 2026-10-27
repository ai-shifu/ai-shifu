"""Abnormal stream termination must discard the DB connection, not pool it.

The pool-level desync detector (flaskr/dao checkin/checkout probes) caught a
production connection returned with unread protocol data after a closed stream
rolled back on it. Rolling back on a connection whose protocol state is unknown
consumes stale packets and re-pools a poisoned stream. The lesson producer and
the follow-up path therefore discard the connection on these errors; these tests
pin the classifier and the discard helper they share.
"""

from flaskr.dao import is_protocol_interrupt_error
from sqlalchemy.exc import OperationalError, ResourceClosedError


def test_desync_error_classifier_covers_symptom_family() -> None:
    assert is_protocol_interrupt_error(ResourceClosedError("no rows"))
    wrapped_2013 = OperationalError(
        "INSERT ...",
        {},
        Exception(2013, "Lost connection to MySQL server during query"),
    )
    wrapped_2013.orig.args = (2013, "Lost connection to MySQL server during query")
    assert is_protocol_interrupt_error(wrapped_2013)
    raw_2014 = Exception(2014, "Command Out of Sync")
    assert is_protocol_interrupt_error(raw_2014)
    assert not is_protocol_interrupt_error(ValueError("boom"))
    wrapped_deadlock = OperationalError("UPDATE ...", {}, Exception())
    wrapped_deadlock.orig.args = (1213, "Deadlock found")
    assert not is_protocol_interrupt_error(wrapped_deadlock)


def test_discard_helper_works_on_real_scoped_session(
    app: object, caplog: object
) -> None:
    import logging

    from flaskr.service.learn.runscript_v2 import _discard_session_connection

    with app.app_context(), caplog.at_level(logging.WARNING):
        _discard_session_connection(source="real session smoke")
    assert "invalidate failed" not in caplog.text

import pytest
from flaskr.service.learn import runscript_v2
from flaskr.service.learn.runscript_v2 import _ensure_healthy_db_connection
from sqlalchemy.exc import OperationalError


class _EchoResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar(self):
        return self._value


class _FakeConnection:
    def __init__(self) -> None:
        self.invalidated = 0

    def invalidate(self):
        self.invalidated += 1


class _FakeSession:
    """Scripted session: each execute() consumes the next behaviour."""

    def __init__(self, behaviours) -> None:
        # behaviours: list of "ok" | "raise" | any-fixed-echo-value
        self._behaviours = list(behaviours)
        self.executed = 0
        self.rollbacks = 0
        self.invalidations = 0
        self._connection = _FakeConnection()

    def invalidate(self):
        self.invalidations += 1

    def execute(self, _statement, params):
        self.executed += 1
        behaviour = self._behaviours.pop(0)
        if behaviour == "ok":
            return _EchoResult(params["nonce"])
        if behaviour == "raise":
            raise OperationalError(
                "SELECT :nonce",
                params,
                Exception("(2014, 'Command Out of Sync')"),
            )
        return _EchoResult(behaviour)

    def connection(self):
        return self._connection

    def rollback(self):
        self.rollbacks += 1


def _patch_session(monkeypatch, behaviours):
    session = _FakeSession(behaviours)

    class _FakeDb:
        pass

    _FakeDb.session = session
    monkeypatch.setattr(runscript_v2, "db", _FakeDb)
    return session


def test_probe_passes_on_healthy_connection(app):
    with app.app_context():
        _ensure_healthy_db_connection(app)


def test_probe_invalidates_desynced_connection_and_retries(app, monkeypatch):
    session = _patch_session(monkeypatch, ["raise", "ok"])

    _ensure_healthy_db_connection(app)

    assert session.executed == 2
    assert session.invalidations == 1
    assert session.rollbacks == 0


def test_probe_detects_mismatched_echo_and_retries(app, monkeypatch):
    session = _patch_session(monkeypatch, ["stale-packet-value", "ok"])

    _ensure_healthy_db_connection(app)

    assert session.executed == 2
    assert session.invalidations == 1


def test_probe_raises_after_exhausting_attempts(app, monkeypatch):
    session = _patch_session(monkeypatch, ["raise", "raise", "raise"])

    with pytest.raises(OperationalError):
        _ensure_healthy_db_connection(app)

    assert session.executed == 3
    assert session.invalidations == 3
    assert session.rollbacks == 0


def test_probe_raises_on_persistent_echo_mismatch(app, monkeypatch):
    _patch_session(monkeypatch, ["bad-1", "bad-2", "bad-3"])

    with pytest.raises(RuntimeError):
        _ensure_healthy_db_connection(app)

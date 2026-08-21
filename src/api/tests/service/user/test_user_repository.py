"""transactional_session termination-classification behavior."""


def test_transactional_session_classifies_before_savepoint_rollback(app, monkeypatch):
    """Abnormal terminations must invalidate WITHOUT any savepoint rollback reaching the wire; ordinary errors keep the legacy full-rollback path."""
    _ = app
    import flaskr.service.user.repository as repo_module
    from sqlalchemy.exc import ResourceClosedError

    events = []

    def invalidate(*, source, session=None):
        del session
        events.append(("invalidate", source))
        return True

    def cleanup(exc, *, source, session=None):
        del exc, session
        events.append(("cleanup", source))
        return "rolled_back"

    monkeypatch.setattr(
        repo_module,
        "invalidate_session",
        invalidate,
    )
    monkeypatch.setattr(
        repo_module,
        "cleanup_session_after",
        cleanup,
    )

    class _Nested:
        def __init__(self) -> None:
            self.rollbacks = 0
            self.commits = 0

        def rollback(self):
            self.rollbacks += 1

        def commit(self):
            self.commits += 1

    nested = _Nested()
    monkeypatch.setattr(
        repo_module.db.session, "begin_nested", lambda: nested, raising=False
    )

    import pytest

    # Desync inside the body: invalidate only, savepoint untouched.
    message = "desynced"
    with pytest.raises(ResourceClosedError), repo_module.transactional_session():
        raise ResourceClosedError(message)
    assert events == [("invalidate", "transactional_session desync")]
    assert nested.rollbacks == 0
    events.clear()

    # Ordinary error: savepoint rollback then classified session cleanup.
    message = "business"
    with (
        pytest.raises(ValueError, match="business"),
        repo_module.transactional_session(),
    ):
        raise ValueError(message)
    assert events == [("cleanup", "transactional_session")]
    assert nested.rollbacks == 1
    events.clear()

    # Success commits the savepoint.
    with repo_module.transactional_session():
        pass
    assert nested.commits == 1

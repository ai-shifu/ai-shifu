"""transactional_session termination-classification behavior."""


def test_transactional_session_classifies_before_savepoint_rollback(app, monkeypatch):
    """Abnormal terminations must invalidate WITHOUT any savepoint rollback
    reaching the wire; ordinary errors keep the legacy full-rollback path.
    """
    import flaskr.service.user.repository as repo_module
    from sqlalchemy.exc import ResourceClosedError

    events = []
    monkeypatch.setattr(
        repo_module,
        "invalidate_session",
        lambda *, source, session=None: events.append(("invalidate", source)) or True,
    )
    monkeypatch.setattr(
        repo_module,
        "cleanup_session_after",
        lambda exc, *, source, session=None: (
            events.append(("cleanup", source)) or "rolled_back"
        ),
    )

    class _Nested:
        def __init__(self):
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
    with pytest.raises(ResourceClosedError), repo_module.transactional_session():
        raise ResourceClosedError("desynced")
    assert events == [("invalidate", "transactional_session desync")]
    assert nested.rollbacks == 0
    events.clear()

    # Ordinary error: savepoint rollback then classified session cleanup.
    with (
        pytest.raises(ValueError, match="business"),
        repo_module.transactional_session(),
    ):
        raise ValueError("business")
    assert events == [("cleanup", "transactional_session")]
    assert nested.rollbacks == 1
    events.clear()

    # Success commits the savepoint.
    with repo_module.transactional_session():
        pass
    assert nested.commits == 1

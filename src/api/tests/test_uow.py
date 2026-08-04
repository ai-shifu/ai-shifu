"""unit_of_work termination-classification behavior."""

import pytest


def test_unit_of_work_invalidates_on_base_exception(app, monkeypatch):
    import flaskr.dao as dao
    from flaskr.dao.uow import unit_of_work

    invalidations = []
    monkeypatch.setattr(
        dao,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
    )

    class _Interrupt(BaseException):
        pass

    with app.app_context():
        with pytest.raises(_Interrupt):
            with unit_of_work():
                raise _Interrupt()

    assert invalidations == ["unit_of_work interrupt"]


def test_unit_of_work_classifies_desync_exceptions(app, monkeypatch):
    import flaskr.dao as dao
    from flaskr.dao.uow import unit_of_work

    outcomes = []
    monkeypatch.setattr(
        dao,
        "cleanup_session_after",
        lambda exc, *, source, session=None: (
            outcomes.append((type(exc).__name__, source)) or "invalidated"
        ),
    )

    from sqlalchemy.exc import ResourceClosedError

    with app.app_context():
        with pytest.raises(ResourceClosedError):
            with unit_of_work():
                raise ResourceClosedError("desynced")

    assert outcomes == [("ResourceClosedError", "unit_of_work")]

"""unit_of_work termination-classification behavior."""

from typing import Never

import pytest


def test_unit_of_work_invalidates_on_base_exception(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> Never:
    from flaskr import dao
    from flaskr.dao.uow import unit_of_work

    invalidations = []
    monkeypatch.setattr(
        dao,
        "invalidate_session",
        lambda *, source, _session=None: invalidations.append(source) or True,
    )

    class _Interrupt(BaseException):
        pass

    with app.app_context(), pytest.raises(_Interrupt), unit_of_work():
        raise _Interrupt

    assert invalidations == ["unit_of_work interrupt"]


def test_unit_of_work_classifies_desync_exceptions(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> Never:
    from flaskr import dao
    from flaskr.dao.uow import unit_of_work

    outcomes = []
    monkeypatch.setattr(
        dao,
        "cleanup_session_after",
        lambda exc, *, source, _session=None: (
            outcomes.append((type(exc).__name__, source)) or "invalidated"
        ),
    )

    from sqlalchemy.exc import ResourceClosedError

    message = "desynced"
    with app.app_context(), pytest.raises(ResourceClosedError), unit_of_work():
        raise ResourceClosedError(message)

    assert outcomes == [("ResourceClosedError", "unit_of_work")]

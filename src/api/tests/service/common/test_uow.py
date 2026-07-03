"""Tests for the unit-of-work transaction boundary (flaskr/dao/uow.py)."""

import threading

import pytest

from flaskr import dao
from flaskr.dao import uow
from flaskr.service.shifu.models import PublishedShifu


def _make_shifu(bid: str) -> PublishedShifu:
    return PublishedShifu(
        shifu_bid=bid,
        title="UOW Test",
        description="",
        keywords="",
    )


def _count(bid: str) -> int:
    return PublishedShifu.query.filter_by(shifu_bid=bid).count()


def test_outermost_commits_on_clean_exit(app):
    with app.app_context():
        with uow.unit_of_work():
            dao.db.session.add(_make_shifu("uow-commit-1"))
        dao.db.session.expire_all()
        assert _count("uow-commit-1") == 1


def test_outermost_rolls_back_on_exception(app):
    with app.app_context():
        with pytest.raises(RuntimeError):
            with uow.unit_of_work():
                dao.db.session.add(_make_shifu("uow-rollback-1"))
                dao.db.session.flush()
                raise RuntimeError("boom")
        assert _count("uow-rollback-1") == 0


def test_nested_block_joins_outer_transaction(app):
    with app.app_context():

        def helper():
            with uow.unit_of_work():
                dao.db.session.add(_make_shifu("uow-nested-inner-1"))

        with pytest.raises(RuntimeError):
            with uow.unit_of_work():
                helper()
                dao.db.session.add(_make_shifu("uow-nested-outer-1"))
                raise RuntimeError("outer fails after helper 'completed'")

        # The helper's write must be gone too: nested blocks do not commit.
        assert _count("uow-nested-inner-1") == 0
        assert _count("uow-nested-outer-1") == 0


def test_nested_clean_exit_commits_once_at_outermost(app):
    with app.app_context():
        with uow.unit_of_work():
            with uow.unit_of_work():
                dao.db.session.add(_make_shifu("uow-nested-clean-1"))
            # Not yet committed: still inside the outer unit of work.
            assert uow.in_unit_of_work()
        dao.db.session.expire_all()
        assert _count("uow-nested-clean-1") == 1


def test_in_unit_of_work_flag(app):
    with app.app_context():
        assert not uow.in_unit_of_work()
        with uow.unit_of_work():
            assert uow.in_unit_of_work()
        assert not uow.in_unit_of_work()


def test_depth_is_isolated_per_thread(app):
    """The /run producer runs in its own thread; depth must not leak across."""
    seen = {}

    def worker():
        seen["inside_thread"] = uow.in_unit_of_work()

    with app.app_context():
        with uow.unit_of_work():
            t = threading.Thread(target=worker)
            t.start()
            t.join()
    assert seen["inside_thread"] is False


def test_depth_resets_after_exception(app):
    with app.app_context():
        with pytest.raises(RuntimeError):
            with uow.unit_of_work():
                raise RuntimeError("boom")
        assert not uow.in_unit_of_work()

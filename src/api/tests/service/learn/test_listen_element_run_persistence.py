import pytest
from sqlalchemy.exc import ResourceClosedError

from flaskr.dao import db
from flaskr.service.learn import listen_element_run_persistence
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.models import LearnGeneratedElement


def _make_row(
    *,
    element_bid: str,
    target_element_bid: str = "",
    run_event_seq: int,
    status: int = 1,
):
    return LearnGeneratedElement(
        element_bid=element_bid,
        target_element_bid=target_element_bid,
        progress_record_bid="progress-a",
        user_bid="user-a",
        generated_block_bid="block-a",
        outline_item_bid="outline-a",
        shifu_bid="shifu-a",
        run_session_bid="run-a",
        run_event_seq=run_event_seq,
        event_type="element",
        role="teacher",
        element_index=0,
        deleted=0,
        status=status,
    )


def test_find_active_element_row_ids_returns_sorted_ids_from_both_bid_columns(app):
    with app.app_context():
        LearnGeneratedElement.query.delete()
        db.session.commit()

        db.session.add_all(
            [
                _make_row(element_bid="element-a", run_event_seq=3),
                _make_row(
                    element_bid="patch-row",
                    target_element_bid="element-a",
                    run_event_seq=1,
                ),
                _make_row(element_bid="element-b", run_event_seq=2),
            ]
        )
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid="shifu-a",
            outline_bid="outline-a",
            user_bid="user-a",
            run_session_bid="run-a",
        )

        row_ids = adapter._find_active_element_row_ids(
            generated_block_bid="block-a",
            element_bids=["element-a"],
        )

        rows = LearnGeneratedElement.query.order_by(
            LearnGeneratedElement.id.asc()
        ).all()
        expected_ids = [
            row.id
            for row in rows
            if row.element_bid == "element-a" or row.target_element_bid == "element-a"
        ]
        assert row_ids == expected_ids


def test_find_active_element_row_ids_sees_rows_flushed_in_current_transaction(app):
    with app.app_context():
        LearnGeneratedElement.query.delete()
        db.session.commit()

        db.session.add(_make_row(element_bid="element-a", run_event_seq=1))
        db.session.flush()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid="shifu-a",
            outline_bid="outline-a",
            user_bid="user-a",
            run_session_bid="run-a",
        )

        row_ids = adapter._find_active_element_row_ids(
            generated_block_bid="block-a",
            element_bids=["element-a"],
        )

        assert len(row_ids) == 1
        assert row_ids[0] == LearnGeneratedElement.query.first().id
        db.session.rollback()


def test_find_active_element_row_ids_invalidates_desynced_connection(app, monkeypatch):
    class _DesyncedResult:
        def fetchall(self):
            raise ResourceClosedError(
                "This result object does not return rows. "
                "It has been closed automatically."
            )

        def close(self):
            pass

    class _FakeConnection:
        def __init__(self):
            self.invalidated = 0

        def execute(self, *_args, **_kwargs):
            return _DesyncedResult()

        def invalidate(self):
            self.invalidated += 1

    class _FakeSession:
        def __init__(self, connection):
            self._connection = connection

        def connection(self):
            return self._connection

    fake_connection = _FakeConnection()

    class _FakeDb:
        session = _FakeSession(fake_connection)

    monkeypatch.setattr(listen_element_run_persistence, "db", _FakeDb)

    with app.app_context():
        adapter = ListenElementRunAdapter(
            app,
            shifu_bid="shifu-a",
            outline_bid="outline-a",
            user_bid="user-a",
            run_session_bid="run-a",
        )

        with pytest.raises(ResourceClosedError):
            adapter._find_active_element_row_ids(
                generated_block_bid="block-a",
                element_bids=["element-a"],
            )

    assert fake_connection.invalidated == 1


def test_deactivate_active_element_rows_retires_rows_without_touching_others(app):
    with app.app_context():
        LearnGeneratedElement.query.delete()
        db.session.commit()

        db.session.add_all(
            [
                _make_row(element_bid="element-a", run_event_seq=1),
                _make_row(
                    element_bid="patch-row",
                    target_element_bid="element-a",
                    run_event_seq=2,
                ),
                _make_row(element_bid="element-b", run_event_seq=3),
            ]
        )
        db.session.commit()

        adapter = ListenElementRunAdapter(
            app,
            shifu_bid="shifu-a",
            outline_bid="outline-a",
            user_bid="user-a",
            run_session_bid="run-a",
        )

        adapter._deactivate_active_element_rows(
            generated_block_bid="block-a",
            element_bids=["element-a"],
        )
        db.session.commit()

        rows = LearnGeneratedElement.query.order_by(
            LearnGeneratedElement.id.asc()
        ).all()

        assert [row.status for row in rows] == [0, 0, 1]


def test_desync_forensics_capture_fingerprints_the_stale_response():
    from flaskr.service.learn.listen_element_run_persistence import (
        _describe_desynced_connection,
    )

    class _FakeCursor:
        rowcount = 1
        lastrowid = 4242
        description = None

    class _FakeResult:
        cursor = _FakeCursor()

    class _FakePrevResult:
        affected_rows = 1
        insert_id = 4242
        server_status = 3
        unbuffered_active = False
        field_count = 0

    class _FakeRaw:
        _next_seq_id = 7
        _result = _FakePrevResult()
        _sock = None

        def thread_id(self):
            return 555001

    class _FakeConnection:
        class connection:
            dbapi_connection = _FakeRaw()

    described = _describe_desynced_connection(_FakeResult(), _FakeConnection())

    assert "cursor.rowcount=1" in described
    assert "cursor.lastrowid=4242" in described
    assert "cursor.description=None" in described
    assert "server_thread_id=555001" in described
    assert "next_seq_id=7" in described
    assert "insert_id=4242" in described


def test_desync_forensics_survives_missing_raw_connection():
    from flaskr.service.learn.listen_element_run_persistence import (
        _describe_desynced_connection,
    )

    class _FakeResult:
        cursor = None

    class _FakeConnection:
        connection = None

    described = _describe_desynced_connection(_FakeResult(), _FakeConnection())
    assert "raw_connection=unavailable" in described

from flaskr.dao import db
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

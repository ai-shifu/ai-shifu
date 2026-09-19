"""Keep course selection trace metadata independent from cleanup storage."""

from uuid import uuid4

from flaskr.api.llm.tiers import selection_metadata
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, PublishedShifu
from sqlalchemy import event


def test_selection_metadata_needs_no_sql_after_loading_course_revisions(
    app: object,
) -> None:
    """Numbered and historical choices retain identity without SQL reads or writes."""
    with app.app_context():
        with unit_of_work():
            courses = [
                model_type(shifu_bid=uuid4().hex, llm=selection, ask_llm=selection)
                for model_type in (DraftShifu, PublishedShifu)
                for selection in ("1", "3", "7", "legacy-model", "")
            ]
            outline = DraftOutlineItem(outline_item_bid=uuid4().hex)
            db.session.add_all([*courses, outline])
        expected = []
        for record in [*courses, outline]:
            # Committing expires ORM attributes. Load the actual rows
            # before observing SQL so the test measures metadata extraction.
            db.session.refresh(record)
            expected.extend(
                (record, follow_up, selection_metadata(record, follow_up=follow_up))
                for follow_up in (False, True)
            )
        queries = []

        def record_query(
            _conn: object,
            _cursor: object,
            statement: str,
            _params: object,
            _context: object,
            _many: object,
        ) -> None:
            queries.append(statement)

        event.listen(db.engine, "before_cursor_execute", record_query)
        try:
            for _request in range(2):
                with app.test_request_context():
                    for _repeat in range(3):
                        for record, follow_up, metadata in expected:
                            assert (
                                selection_metadata(record, follow_up=follow_up)
                                == metadata
                            )
            assert queries == []
        finally:
            event.remove(db.engine, "before_cursor_execute", record_query)

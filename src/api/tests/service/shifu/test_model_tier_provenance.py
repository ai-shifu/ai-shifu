"""Keep course selection trace metadata independent from cleanup storage."""

from uuid import uuid4

from flaskr.api.llm.tiers import MODEL_TIERS, selection_metadata
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu.model_tier_migration import migrate_default_model_tiers
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, PublishedShifu
from sqlalchemy import event


def test_selection_metadata_needs_no_sql_after_loading_course_revisions(
    app: object,
) -> None:
    """All tiers, legacy names and cleaned defaults retain identity without reads."""
    with app.app_context():
        with unit_of_work():
            courses = [
                model_type(shifu_bid=uuid4().hex, llm=selection, ask_llm=selection)
                for model_type in (DraftShifu, PublishedShifu)
                for selection in (*MODEL_TIERS, "legacy-model", "")
            ]
            outline = DraftOutlineItem(outline_item_bid=uuid4().hex)
            db.session.add_all([*courses, outline])
        migrate_default_model_tiers(app, apply=True)
        expected = []
        for record in [*courses, outline]:
            # Committing cleanup expires ORM attributes. Load the actual rows
            # before observing SQL so the test measures metadata extraction.
            db.session.refresh(record)
            for follow_up in (False, True):
                field = "ask_llm" if follow_up else "llm"
                selected = getattr(record, field, "")
                tier = selected if selected in MODEL_TIERS else None
                expected.append(
                    (
                        record,
                        follow_up,
                        {
                            "model_tier": tier,
                            "model_selection_origin": "tier"
                            if tier
                            else "legacy_model",
                            "model_selection_field": field,
                            "model_selection_table": record.__tablename__,
                            "model_selection_record_id": record.id,
                        },
                    )
                )
        assert all(course.llm and course.ask_llm for course in courses)
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

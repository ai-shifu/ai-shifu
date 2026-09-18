"""Bound migration-provenance reads without losing course selection history."""

from uuid import uuid4

from flaskr.api.llm.tiers import selection_metadata
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu.model_tier_migration import migrate_default_model_tiers
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    ModelTierMigrationAudit,
    PublishedShifu,
)
from sqlalchemy import event


def test_provenance_queries_once_per_course_field_and_request(app: object) -> None:
    """Cache hits and misses per request; outlines and other tiers need no lookup."""
    with app.app_context():
        with unit_of_work():
            migrated = PublishedShifu(shifu_bid=uuid4().hex, llm="", ask_llm="")
            selected = DraftShifu(shifu_bid=uuid4().hex, llm="fast")
            outline = DraftOutlineItem(
                outline_item_bid=uuid4().hex, llm="fast", ask_llm="fast"
            )
            other_tier = DraftShifu(shifu_bid=uuid4().hex, llm="ultimate")
            db.session.add_all([migrated, selected, outline, other_tier])
            db.session.flush()
            # This case requires a cache miss. SQLite row IDs may have been
            # reused after another test deleted courses but kept audit rows.
            ModelTierMigrationAudit.query.filter_by(
                table_name=DraftShifu.__tablename__,
                row_id=selected.id,
                field_name="llm",
            ).delete(synchronize_session=False)
        result = migrate_default_model_tiers(app, apply=True)
        db.session.expire_all()
        queries = []

        def record_query(
            _conn: object,
            _cursor: object,
            statement: str,
            _params: object,
            _context: object,
            _many: object,
        ) -> None:
            if (
                statement.lstrip().upper().startswith("SELECT")
                and "shifu_model_tier_migration_audit" in statement
            ):
                queries.append(statement)

        event.listen(db.engine, "before_cursor_execute", record_query)
        try:
            for request_number in range(2):
                with app.test_request_context():
                    for _repeat in range(3):
                        for follow_up in (False, True):
                            metadata = selection_metadata(migrated, follow_up=follow_up)
                            assert (
                                metadata["model_selection_origin"] == "migrated_default"
                            )
                            assert (
                                metadata["model_migration_batch"] == result["batch_bid"]
                            )
                            assert (
                                selection_metadata(outline, follow_up=follow_up)[
                                    "model_selection_origin"
                                ]
                                == "tier"
                            )
                        assert (
                            selection_metadata(selected)["model_selection_origin"]
                            == "tier"
                        )
                        assert (
                            selection_metadata(other_tier)["model_selection_origin"]
                            == "tier"
                        )
                assert len(queries) == 3 * (request_number + 1)
        finally:
            event.remove(db.engine, "before_cursor_execute", record_query)


def test_provenance_uses_latest_batch_after_cleanup_recovery(app: object) -> None:
    """A restored and remigrated revision must point at its newest cleanup."""
    with app.app_context():
        with unit_of_work():
            row = DraftShifu(shifu_bid=uuid4().hex, llm="", ask_llm="")
            db.session.add(row)
        original = migrate_default_model_tiers(app, apply=True)
        with unit_of_work():
            row.llm = ""
            row.ask_llm = ""
        latest = migrate_default_model_tiers(app, apply=True)
        assert original["batch_bid"] != latest["batch_bid"]
        db.session.expire_all()
        with app.test_request_context():
            for follow_up in (False, True):
                metadata = selection_metadata(row, follow_up=follow_up)
                assert metadata["model_migration_batch"] == latest["batch_bid"]

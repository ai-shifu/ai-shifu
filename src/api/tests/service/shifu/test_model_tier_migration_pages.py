"""Page historical cleanup reads while retaining atomic recovery."""

from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu import model_tier_migration as migration
from flaskr.service.shifu.models import DraftShifu, ModelTierMigrationAudit
from sqlalchemy import event


@pytest.mark.parametrize("fail_last_page", [False, True])
def test_cleanup_pages_without_skipping_rows_or_partial_commits(
    app: object, monkeypatch: pytest.MonkeyPatch, fail_last_page: bool
) -> None:
    monkeypatch.setattr(migration, "_MIGRATION_PAGE_SIZE", 2)
    with app.app_context():
        with unit_of_work():
            rows = [
                DraftShifu(shifu_bid=uuid4().hex, llm="", ask_llm="") for _ in range(5)
            ]
            db.session.add_all(rows)
        row_ids = [row.id for row in rows]
        queries = []

        def capture(
            _conn: object,
            _cursor: object,
            statement: str,
            _params: object,
            _context: object,
            _many: object,
        ) -> None:
            if (
                statement.lstrip().upper().startswith("SELECT")
                and "ORDER BY shifu_draft_shifus.id" in statement
            ):
                queries.append(statement)

        original_add = db.session.add

        def add(value: object) -> None:
            if (
                fail_last_page
                and isinstance(value, ModelTierMigrationAudit)
                and value.row_id == row_ids[-1]
                and value.table_name == DraftShifu.__tablename__
            ):
                message = "last page audit failure"
                raise RuntimeError(message)
            original_add(value)

        monkeypatch.setattr(db.session, "add", add)
        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            preview = migration.migrate_default_model_tiers(app)
            selected = [
                c
                for c in preview["changes"]
                if c["table"] == DraftShifu.__tablename__ and c["row_id"] in row_ids
            ]
            assert len(selected) == 10
            if fail_last_page:
                with pytest.raises(RuntimeError, match="last page audit failure"):
                    migration.migrate_default_model_tiers(app, apply=True)
            else:
                migration.migrate_default_model_tiers(app, apply=True)
                assert (
                    migration.migrate_default_model_tiers(app, apply=True)["count"] == 0
                )
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
        assert len(queries) >= 6
        assert all("LIMIT" in query for query in queries)
        db.session.expire_all()
        for row in rows:
            assert row.llm_tier == (None if fail_last_page else "fast")
            assert row.ask_llm_tier == (None if fail_last_page else "fast")
        assert ModelTierMigrationAudit.query.filter(
            ModelTierMigrationAudit.table_name == DraftShifu.__tablename__,
            ModelTierMigrationAudit.row_id.in_(row_ids),
        ).count() == (0 if fail_last_page else 10)

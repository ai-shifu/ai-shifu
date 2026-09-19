"""Page historical cleanup reads while retaining atomic recovery."""

from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu import model_tier_migration as migration
from flaskr.service.shifu.models import DraftShifu
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
        original_updated = [row.updated_at for row in rows]
        queries = []
        updates = []

        def capture(
            _conn: object,
            _cursor: object,
            statement: str,
            _params: object,
            context: object,
            _many: object,
        ) -> None:
            if (
                statement.lstrip().upper().startswith("SELECT")
                and "ORDER BY shifu_draft_shifus.id" in statement
            ):
                queries.append(statement)
            if statement.lstrip().upper().startswith("UPDATE SHIFU_DRAFT_SHIFUS "):
                for parameters in context.compiled_parameters:
                    row_id = parameters.get("id_1")
                    if row_id not in row_ids:
                        continue
                    if fail_last_page and row_id == row_ids[-1]:
                        message = "last page update failure"
                        raise RuntimeError(message)
                    updates.append(row_id)

        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            preview = migration.migrate_default_model_tiers(app)
            selected = [
                c
                for c in preview["changes"]
                if c["table"] == DraftShifu.__tablename__ and c["row_id"] in row_ids
            ]
            assert len(selected) == 10
            assert updates == []
            if fail_last_page:
                with pytest.raises(RuntimeError, match="last page update failure"):
                    migration.migrate_default_model_tiers(app, apply=True)
            else:
                result = migration.migrate_default_model_tiers(app, apply=True)
                assert [
                    c
                    for c in result["changes"]
                    if c["table"] == DraftShifu.__tablename__ and c["row_id"] in row_ids
                ] == selected
                assert (
                    migration.migrate_default_model_tiers(app, apply=True)["count"] == 0
                )
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
        assert len(queries) >= 6
        assert all("LIMIT" in query for query in queries)
        assert updates == [
            row_id
            for row_id in (row_ids[:-1] if fail_last_page else row_ids)
            for _ in range(2)
        ]
        db.session.expire_all()
        for row, updated_at in zip(rows, original_updated, strict=True):
            assert row.llm == ("" if fail_last_page else "fast")
            assert row.ask_llm == ("" if fail_last_page else "fast")
            assert row.updated_at == updated_at

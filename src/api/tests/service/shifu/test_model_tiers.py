"""Verify numbered course defaults, revision preservation, and routing."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.api.llm import tiers
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, PublishedShifu


@pytest.fixture(autouse=True)
def numbered_slots(monkeypatch: pytest.MonkeyPatch) -> dict:
    mapping = {
        f"LLM_MODEL_{index}_{field}": value
        for index in ("1", "3", "7")
        for field, value in (("NAME", f"Option {index}"), ("ID", f"configured-{index}"))
    }
    monkeypatch.setattr(
        tiers, "get_config", lambda key, default=None: mapping.get(key, default)
    )
    monkeypatch.setattr(
        "flaskr.api.llm.get_litellm_params_and_model",
        lambda model: ({"api_key": "test"}, model, "provider"),
    )
    return mapping


@pytest.mark.parametrize("selection", ["", " \t", "old-model", "fast", "3", "9"])
def test_clone_preserves_original_course_selections(
    app: object, selection: str
) -> None:
    with app.app_context(), unit_of_work():
        row = DraftShifu(shifu_bid=uuid4().hex, llm=selection, ask_llm=selection)
        db.session.add(row)
        db.session.flush()
        clone = row.clone()
        assert clone.llm == selection
        assert clone.ask_llm == selection
        assert row.eq(clone)
        clone.llm = "7"
        assert not row.eq(clone)


def test_deleted_number_resumes_after_configuration_is_restored(
    numbered_slots: dict,
) -> None:
    record = SimpleNamespace(llm="3", id=42, __tablename__="shifu_draft_shifus")
    source = tiers.selection_metadata(record)
    first, snapshot = tiers.resolve_selection(record.llm, source)
    del numbered_slots["LLM_MODEL_3_ID"]
    fallback, fallback_metadata = tiers.resolve_selection(record.llm, source)
    numbered_slots["LLM_MODEL_3_ID"] = "replacement-3"
    restored, _ = tiers.resolve_selection(record.llm, source)
    assert (first, fallback, restored) == (
        "configured-3",
        "configured-1",
        "replacement-3",
    )
    assert fallback_metadata["model_selection_fallback"] is True
    assert snapshot["resolved_model"] == first
    assert tiers.resolve_selection(first, snapshot)[0] == first
    assert record.llm == "3"


@pytest.mark.parametrize("selection", ["", " \t", "old-model", "fast", "9"])
def test_preview_falls_back_without_modifying_original_values(
    app: object, selection: str
) -> None:
    from flaskr.service.learn.context_v2 import RunScriptPreviewContextV2

    with app.app_context(), unit_of_work():
        row = DraftShifu(
            shifu_bid=uuid4().hex, llm=selection, ask_llm=selection, llm_temperature=0.3
        )
        db.session.add(row)
        db.session.flush()
        updated = row.updated_at
        context = RunScriptPreviewContextV2(app)
        assert context._resolve_llm_settings(row)[0] == "configured-1"
        metadata = context._preview_model_selection_metadata
        assert metadata["model_selection_original"] == selection
        assert metadata["model_selection_record_id"] == row.id
        assert metadata["model_index"] == "1"
        assert metadata["model_selection_fallback"] is True
        assert (
            tiers.resolve_selection(
                row.ask_llm, tiers.selection_metadata(row, follow_up=True)
            )[0]
            == "configured-1"
        )
        assert row.llm == selection
        assert row.ask_llm == selection
        assert row.updated_at == updated
        assert row not in db.session.dirty


def test_audit_removal_migration_keeps_courses_and_supports_downgrade() -> None:
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = (
        Path(__file__).parents[3]
        / "migrations/versions/5ca8717e482f_add_course_model_cleanup_audit.py"
    )
    spec = importlib.util.spec_from_file_location("tier_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    removal_path = path.with_name("abbe9d73bdb1_remove_course_model_cleanup_audit.py")
    removal_spec = importlib.util.spec_from_file_location(
        "removal_revision", removal_path
    )
    removal = importlib.util.module_from_spec(removal_spec)
    removal_spec.loader.exec_module(removal)
    assert removal.down_revision == revision.revision
    engine = sa.create_engine("sqlite://")
    tables = [
        "shifu_draft_shifus",
        "shifu_published_shifus",
        "shifu_draft_outline_items",
        "shifu_published_outline_items",
    ]
    with engine.begin() as connection:
        for name in tables:
            table = sa.Table(
                name,
                sa.MetaData(),
                sa.Column("id", sa.Integer, primary_key=True),
                sa.Column("llm", sa.Text),
                sa.Column("ask_llm", sa.Text),
            )
            table.create(connection)
            connection.execute(table.insert().values(id=1, llm="legacy", ask_llm=""))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
            audit = sa.Table(
                "shifu_model_tier_migration_audit",
                sa.MetaData(),
                autoload_with=connection,
            )
            from datetime import datetime

            connection.execute(
                audit.insert().values(
                    id=1,
                    batch_bid="old-cleanup",
                    table_name=tables[0],
                    row_id=1,
                    field_name="ask_llm",
                    previous_model="",
                    new_model="fast",
                    created_at=datetime(2026, 9, 17),
                )
            )
            removal.upgrade()
            assert (
                "shifu_model_tier_migration_audit"
                not in sa.inspect(connection).get_table_names()
            )
            for table in tables:
                migrated = sa.table(
                    table,
                    sa.column("llm"),
                    sa.column("ask_llm"),
                )
                row = connection.execute(sa.select(migrated)).one()
                assert tuple(row) == ("legacy", "")
                assert {
                    c["name"] for c in sa.inspect(connection).get_columns(table)
                } == {"id", "llm", "ask_llm"}
            removal.downgrade()
            assert (
                "shifu_model_tier_migration_audit"
                in sa.inspect(connection).get_table_names()
            )
            assert (
                connection.execute(
                    sa.select(sa.func.count()).select_from(audit)
                ).scalar()
                == 0
            )
            # Fresh installs pass through the old revision and end without a ledger.
            removal.upgrade()
            assert (
                "shifu_model_tier_migration_audit"
                not in sa.inspect(connection).get_table_names()
            )
        for table in tables:
            assert {
                column["name"] for column in sa.inspect(connection).get_columns(table)
            } == {"id", "llm", "ask_llm"}


@pytest.mark.parametrize(("main_tier", "expected"), [(None, "1"), ("3", "3")])
def test_new_course_persists_independent_numbered_defaults(
    app: object, monkeypatch: pytest.MonkeyPatch, main_tier: str | None, expected: str
) -> None:
    from flaskr.service.shifu import shifu_draft_funcs as module

    monkeypatch.setattr(module, "check_text_with_risk_control", lambda *_args: None)
    result = module.create_shifu_draft(
        app, "tier-new-owner", "New course", "", "", shifu_model=main_tier
    )
    with app.app_context():
        row = DraftShifu.query.filter_by(shifu_bid=result.bid).one()
        assert row.llm == expected
        assert row.ask_llm == "1"


def test_course_tiers_drive_preview_learning_and_follow_up(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn import context_v2, utils_v2
    from flaskr.service.shifu.consts import ASK_MODE_DEFAULT, ASK_MODE_ENABLE
    from flaskr.service.shifu.shifu_history_manager import HistoryItem

    monkeypatch.setattr(tiers, "resolve_tier_model", lambda tier: f"configured-{tier}")
    with app.app_context():
        bid = uuid4().hex
        with unit_of_work():
            course = DraftShifu(
                shifu_bid=bid,
                llm="1",
                ask_llm="1",
                ask_enabled_status=ASK_MODE_ENABLE,
            )
            parent = DraftOutlineItem(
                shifu_bid=bid,
                outline_item_bid=uuid4().hex,
                ask_enabled_status=ASK_MODE_DEFAULT,
            )
            leaf = DraftOutlineItem(
                shifu_bid=bid,
                outline_item_bid=uuid4().hex,
                parent_bid=parent.outline_item_bid,
                ask_enabled_status=ASK_MODE_DEFAULT,
            )
            db.session.add_all([course, parent, leaf])
        # Even stale in-memory outline attributes cannot override course settings.
        parent.llm = "3"
        parent.ask_llm = "7"
        struct = HistoryItem(
            bid=bid,
            id=course.id,
            type="shifu",
            children=[
                HistoryItem(
                    bid=parent.outline_item_bid,
                    id=parent.id,
                    type="outline",
                    children=[
                        HistoryItem(
                            bid=leaf.outline_item_bid,
                            id=leaf.id,
                            type="outline",
                            children=[],
                        )
                    ],
                )
            ],
        )
        monkeypatch.setattr(context_v2, "get_shifu_struct", lambda *_args: struct)
        monkeypatch.setattr(utils_v2, "get_shifu_struct", lambda *_args: struct)
        runtime = context_v2.RunScriptContextV2.__new__(context_v2.RunScriptContextV2)
        runtime._struct = struct
        runtime._outline_model = DraftOutlineItem
        runtime._shifu_model = DraftShifu
        settings = runtime.get_llm_settings(leaf.outline_item_bid)
        assert (
            tiers.resolve_selection(settings.model, settings.usage_metadata)[0]
            == "configured-1"
        )
        preview = context_v2.RunScriptPreviewContextV2(app)
        assert preview._resolve_llm_settings(course)[0] == "configured-1"
        follow_up = utils_v2.get_follow_up_info_v2(
            app, bid, leaf.outline_item_bid, "", is_preview=True
        )
        assert follow_up.ask_mode == ASK_MODE_ENABLE
        assert (
            tiers.resolve_selection(follow_up.ask_model, follow_up.usage_metadata)[0]
            == "configured-1"
        )
        with unit_of_work():
            course.llm = "3"
            course.ask_llm = "7"
        settings = runtime.get_llm_settings(leaf.outline_item_bid)
        assert (
            tiers.resolve_selection(settings.model, settings.usage_metadata)[0]
            == "configured-3"
        )
        follow_up = utils_v2.get_follow_up_info_v2(
            app, bid, leaf.outline_item_bid, "", is_preview=True
        )
        assert (
            tiers.resolve_selection(follow_up.ask_model, follow_up.usage_metadata)[0]
            == "configured-7"
        )


def test_options_endpoint_keeps_missing_mapping_unavailable(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tiers, "get_config", lambda *_args: "")
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda *_args: SimpleNamespace(language="en-US", user_id="tier-teacher"),
    )
    response = app.test_client().get("/api/llm/model-tier-list")
    assert response.status_code == 200
    result = response.get_json(force=True)["data"]
    assert result == []


@pytest.mark.parametrize("model_type", [DraftShifu, PublishedShifu])
def test_new_course_rows_default_both_existing_fields_to_one(
    app: object, model_type: type
) -> None:
    """Both persistence paths use model 1 without adding any columns."""
    with app.app_context(), unit_of_work():
        row = model_type(shifu_bid=uuid4().hex)
        db.session.add(row)
        db.session.flush()
        assert row.llm == "1"
        assert row.ask_llm == "1"
        assert "llm_tier" not in model_type.__table__.columns
        assert "ask_llm_tier" not in model_type.__table__.columns

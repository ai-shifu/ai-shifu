"""Verify tier persistence, cleanup, revision safety and routing contracts."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.api.llm import tiers
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.shifu.model_tier_migration import migrate_default_model_tiers
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    ModelTierMigrationAudit,
    PublishedShifu,
)


def test_cleanup_persists_defaults_only_and_is_repeatable(app: object) -> None:
    with app.app_context():
        bid = uuid4().hex
        with unit_of_work():
            draft = DraftShifu(shifu_bid=bid, llm=" \t\n", ask_llm="old-ask", deleted=1)
            published = PublishedShifu(shifu_bid=bid, llm="old-main", ask_llm="")
            chosen = DraftShifu(
                shifu_bid=bid, llm="", llm_tier="ultimate", ask_llm="live-model"
            )
            outline = DraftOutlineItem(shifu_bid=bid, outline_item_bid=uuid4().hex)
            db.session.add_all([draft, published, chosen, outline])
        original_updated = draft.updated_at
        before = migrate_default_model_tiers(app)
        assert any(
            change["row_id"] == draft.id and change["field"] == "llm_tier"
            for change in before["changes"]
        )
        assert draft.llm_tier is None
        result = migrate_default_model_tiers(app, apply=True)
        db.session.expire_all()
        assert draft.llm_tier == "fast"
        assert draft.ask_llm_tier is None
        assert draft.llm == " \t\n"
        assert draft.updated_at == original_updated
        assert published.ask_llm_tier == "fast"
        assert published.llm_tier is None
        assert chosen.llm_tier == "ultimate"
        assert outline.llm_tier is None
        assert outline.ask_llm_tier is None
        audit = ModelTierMigrationAudit.query.filter_by(
            batch_bid=result["batch_bid"],
            table_name=DraftShifu.__tablename__,
            row_id=draft.id,
        ).one()
        assert audit.previous_tier is None
        assert audit.new_tier == "fast"
        assert audit.created_at is not None
        assert migrate_default_model_tiers(app, apply=True)["count"] == 0


def test_cleanup_failure_rolls_back_rows_and_audit(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        with unit_of_work():
            row = DraftShifu(shifu_bid=uuid4().hex, llm="", ask_llm="explicit")
            db.session.add(row)
        row_id = row.id
        original_add = db.session.add

        def fail_on_audit(value: object) -> None:
            if isinstance(value, ModelTierMigrationAudit):
                message = "audit failure"
                raise RuntimeError(message)  # noqa: TRY004 - simulate a storage failure, not invalid input.
            return original_add(value)

        monkeypatch.setattr(db.session, "add", fail_on_audit)
        with pytest.raises(RuntimeError, match="audit failure"):
            migrate_default_model_tiers(app, apply=True)
        db.session.expire_all()
        assert db.session.get(DraftShifu, row_id).llm_tier is None
        assert (
            ModelTierMigrationAudit.query.filter_by(
                table_name=DraftShifu.__tablename__, row_id=row_id
            ).count()
            == 0
        )


def test_tier_only_changes_survive_clone_and_equality(app: object) -> None:
    with app.app_context(), unit_of_work():
        for row in (
            DraftShifu(shifu_bid=uuid4().hex),
            DraftOutlineItem(outline_item_bid=uuid4().hex),
        ):
            db.session.add(row)
            db.session.flush()
            _assert_tier_clone(row)


def _assert_tier_clone(row: object) -> None:
    row.llm_tier = "fast"
    row.ask_llm_tier = "ultimate"
    clone = row.clone()
    assert clone.llm_tier == "fast"
    assert clone.ask_llm_tier == "ultimate"
    assert row.eq(clone)
    clone.llm_tier = "balanced"
    assert not row.eq(clone)


@pytest.mark.parametrize(
    ("legacy", "expected"), [("", "fast"), (" \t", "fast"), ("old", None)]
)
def test_course_writes_materialize_default(legacy: str, expected: str | None) -> None:
    assert tiers.normalize_course_tier(None, legacy) == expected


def test_legacy_client_cannot_overwrite_a_tier(app: object) -> None:
    with app.app_context(), pytest.raises(AppError):
        tiers.merge_course_tier(
            tiers.TIER_UNSET,
            current_tier="fast",
            current_model="old",
            incoming_model="new",
            field="llm_tier",
        )
    assert (
        tiers.merge_course_tier(
            tiers.TIER_UNSET,
            current_tier="fast",
            current_model="old",
            incoming_model="old",
            field="llm_tier",
        )
        == "fast"
    )
    assert (
        tiers.merge_course_tier(
            None,
            current_tier="fast",
            current_model="old",
            incoming_model=None,
            field="llm_tier",
        )
        is None
    )


def test_mapping_changes_new_calls_without_reinterpreting_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapping = {"LLM_TIER_FAST_MODEL": "provider/one"}
    monkeypatch.setattr(
        tiers, "get_config", lambda key, default=None: mapping.get(key, default)
    )
    monkeypatch.setattr(
        "flaskr.api.llm.get_litellm_params_and_model",
        lambda model: ({"api_key": "test"}, model, "provider"),
    )
    record = SimpleNamespace(
        llm="old-model", llm_tier="fast", id=42, __tablename__="shifu_draft_shifus"
    )
    source = tiers.selection_metadata(record)
    first, snapshot = tiers.resolve_selection(tiers.selection_model(record), source)
    mapping["LLM_TIER_FAST_MODEL"] = "provider/two"
    second, _ = tiers.resolve_selection(tiers.selection_model(record), source)
    assert first == "provider/one"
    assert second == "provider/two"
    assert snapshot["resolved_model"] == first
    assert snapshot["model_selection_record_id"] == 42
    assert tiers.resolve_selection(first, snapshot)[0] == first
    assert record.llm == "old-model"


def test_missing_tier_configuration_does_not_fall_back(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tiers, "get_config", lambda *_args: "")
    with app.app_context(), pytest.raises(AppError):
        tiers.resolve_selection("old-model", {"model_tier": "fast"})
    with app.app_context(), pytest.raises(AppError):
        tiers.resolve_selection("", {})


def test_tier_options_expose_no_physical_model(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.api import llm

    monkeypatch.setattr(
        tiers, "resolve_tier_model", lambda tier: f"secret-provider/{tier}"
    )
    monkeypatch.setattr(
        llm,
        "_attach_credit_multipliers",
        lambda _app, options: [
            {**item, "credit_multiplier": 2, "credit_multiplier_label": "2x"}
            for item in options
        ],
    )
    result = llm.get_model_tier_options(app)
    assert [item["tier"] for item in result] == ["fast", "balanced", "ultimate"]
    assert all(item["credit_multiplier"] == 2 for item in result)
    assert "secret-provider" not in str(result)
    assert all("model" not in item for item in result)


def test_cleaned_defaults_resolve_to_fast_and_keep_audit_provenance(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn.context_v2 import RunScriptPreviewContextV2
    from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest

    monkeypatch.setattr(tiers, "resolve_tier_model", lambda tier: f"configured-{tier}")
    with app.app_context():
        with unit_of_work():
            row = DraftShifu(
                shifu_bid=uuid4().hex, llm="", ask_llm="", llm_temperature=0.3
            )
            db.session.add(row)
        migrate_default_model_tiers(app, apply=True)
        db.session.expire_all()
        context = RunScriptPreviewContextV2(app)
        model, _ = context._resolve_llm_settings(
            PlaygroundPreviewRequest(block_index=0), None, row
        )
        assert model == "configured-fast"
        assert (
            context._preview_model_selection_metadata["model_selection_origin"]
            == "migrated_default"
        )
        assert (
            context._preview_model_selection_metadata["model_selection_record_id"]
            == row.id
        )
        assert context._preview_model_selection_metadata["model_migration_batch"]
        assert (
            tiers.resolve_selection(
                tiers.selection_model(row, follow_up=True),
                tiers.selection_metadata(row, follow_up=True),
            )[0]
            == "configured-fast"
        )


def test_preview_rejects_uncleaned_course_and_honors_explicit_tier(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn.context_v2 import RunScriptPreviewContextV2
    from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest

    monkeypatch.setattr(tiers, "resolve_tier_model", lambda tier: f"configured-{tier}")
    with app.app_context():
        context = RunScriptPreviewContextV2(app)
        with pytest.raises(AppError):
            context._resolve_llm_settings(
                PlaygroundPreviewRequest(block_index=0), None, DraftShifu()
            )
        model, _ = context._resolve_llm_settings(
            PlaygroundPreviewRequest(block_index=0, llm_tier="ultimate"),
            None,
            DraftShifu(llm_tier="fast"),
        )
        assert model == "configured-ultimate"


def test_schema_migration_keeps_legacy_rows_and_supports_downgrade() -> None:
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = (
        Path(__file__).parents[3]
        / "migrations/versions/5ca8717e482f_add_independent_course_model_tiers.py"
    )
    spec = importlib.util.spec_from_file_location("tier_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
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
            for table in tables:
                migrated = sa.table(
                    table,
                    sa.column("llm"),
                    sa.column("llm_tier"),
                    sa.column("ask_llm_tier"),
                )
                row = connection.execute(sa.select(migrated)).one()
                assert tuple(row) == ("legacy", None, None)
            assert (
                "shifu_model_tier_migration_audit"
                in sa.inspect(connection).get_table_names()
            )
            revision.downgrade()
        for table in tables:
            assert {
                column["name"] for column in sa.inspect(connection).get_columns(table)
            } == {"id", "llm", "ask_llm"}


@pytest.mark.parametrize(
    ("main_tier", "expected"), [(None, "fast"), ("ultimate", "ultimate")]
)
def test_new_course_persists_independent_fast_defaults(
    app: object, monkeypatch: pytest.MonkeyPatch, main_tier: str | None, expected: str
) -> None:
    from flaskr.service.shifu import shifu_draft_funcs as module

    monkeypatch.setattr(module, "check_text_with_risk_control", lambda *_args: None)
    result = module.create_shifu_draft(
        app, "tier-new-owner", "New course", "", "", llm_tier=main_tier
    )
    with app.app_context():
        row = DraftShifu.query.filter_by(shifu_bid=result.bid).one()
        assert row.llm_tier == expected
        assert row.ask_llm_tier == "fast"
        assert row.llm == ""
        assert row.ask_llm == ""


def test_outline_tiers_inherit_consistently_in_preview_learning_and_follow_up(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn import context_v2, utils_v2
    from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest
    from flaskr.service.shifu.consts import ASK_MODE_DEFAULT, ASK_MODE_ENABLE
    from flaskr.service.shifu.shifu_history_manager import HistoryItem

    monkeypatch.setattr(tiers, "resolve_tier_model", lambda tier: f"configured-{tier}")
    with app.app_context():
        bid = uuid4().hex
        with unit_of_work():
            course = DraftShifu(
                shifu_bid=bid,
                llm_tier="fast",
                ask_llm_tier="fast",
                ask_enabled_status=ASK_MODE_ENABLE,
            )
            parent = DraftOutlineItem(
                shifu_bid=bid,
                outline_item_bid=uuid4().hex,
                llm_tier="balanced",
                ask_llm_tier="ultimate",
                ask_enabled_status=ASK_MODE_DEFAULT,
            )
            leaf = DraftOutlineItem(
                shifu_bid=bid,
                outline_item_bid=uuid4().hex,
                parent_bid=parent.outline_item_bid,
                ask_enabled_status=ASK_MODE_DEFAULT,
            )
            db.session.add_all([course, parent, leaf])
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
            == "configured-balanced"
        )
        preview = context_v2.RunScriptPreviewContextV2(app)
        assert (
            preview._resolve_llm_settings(
                PlaygroundPreviewRequest(block_index=0), leaf, course
            )[0]
            == "configured-balanced"
        )
        follow_up = utils_v2.get_follow_up_info_v2(
            app, bid, leaf.outline_item_bid, "", is_preview=True
        )
        assert follow_up.ask_mode == ASK_MODE_ENABLE
        assert (
            tiers.resolve_selection(follow_up.ask_model, follow_up.usage_metadata)[0]
            == "configured-ultimate"
        )
        with unit_of_work():
            parent.llm_tier = None
            parent.ask_llm_tier = None
        settings = runtime.get_llm_settings(leaf.outline_item_bid)
        assert (
            tiers.resolve_selection(settings.model, settings.usage_metadata)[0]
            == "configured-fast"
        )
        follow_up = utils_v2.get_follow_up_info_v2(
            app, bid, leaf.outline_item_bid, "", is_preview=True
        )
        assert (
            tiers.resolve_selection(follow_up.ask_model, follow_up.usage_metadata)[0]
            == "configured-fast"
        )


def test_outline_patch_preserves_omitted_tiers_and_null_restores_inheritance(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.shifu import shifu_outline_funcs as module

    monkeypatch.setattr(module, "save_outline_history", lambda *_args: None)
    monkeypatch.setattr(module, "cleanup_outline_history_versions", lambda *_args: None)
    with app.app_context():
        with unit_of_work():
            outline = DraftOutlineItem(
                shifu_bid=uuid4().hex,
                outline_item_bid=uuid4().hex,
                position="1",
                llm_tier="balanced",
                ask_llm_tier="ultimate",
            )
            db.session.add(outline)
        result = module.modify_unit(
            app, "teacher", outline.outline_item_bid, ask_llm_tier="fast"
        )
        assert result.llm_tier == "balanced"
        assert result.ask_llm_tier == "fast"
        result = module.modify_unit(
            app, "teacher", outline.outline_item_bid, llm_tier=None
        )
        assert result.llm_tier is None
        assert result.ask_llm_tier == "fast"
        with pytest.raises(AppError):
            module.modify_unit(
                app, "teacher", outline.outline_item_bid, llm_tier="unknown"
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
    assert [item["tier"] for item in result] == ["fast", "balanced", "ultimate"]
    assert all(item["available"] is False for item in result)
    assert result[0]["is_default"] is True
    assert all("model" not in item for item in result)

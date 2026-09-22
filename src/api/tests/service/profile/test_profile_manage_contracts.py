"""Verify variable-definition scope, usage discovery, and persisted edits."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.profile import profile_manage as profiles
from flaskr.service.profile.models import Variable
from flaskr.service.shifu.models import DraftOutlineItem
from sqlalchemy import event, text


@pytest.fixture
def variables(app: object) -> object:
    identity = uuid.uuid4().hex
    keys = {name: f"{name}_{identity}" for name in ("used", "unused", "old", "system")}
    with app.app_context(), unit_of_work():
        for name, key in keys.items():
            db.session.add(
                Variable(
                    variable_bid=uuid.uuid4().hex,
                    shifu_bid="" if name == "system" else identity,
                    key=key,
                    is_hidden=0,
                    deleted=0,
                )
            )
        for outline, content, deleted in (
            ("updated", "{{" + keys["old"] + "}}", 0),
            ("updated", "{{" + keys["used"] + "}}", 0),
            ("removed", "{{" + keys["unused"] + "}}", 1),
            ("blank", "", 0),
        ):
            db.session.add(
                DraftOutlineItem(
                    shifu_bid=identity,
                    outline_item_bid=f"{identity}-{outline}",
                    content=content,
                    position=0,
                    deleted=deleted,
                )
            )
    yield SimpleNamespace(course=identity, keys=keys)
    with app.app_context(), unit_of_work():
        Variable.query.filter(
            (Variable.shifu_bid == identity) | Variable.key.in_(list(keys.values()))
        ).delete(synchronize_session=False)
        DraftOutlineItem.query.filter_by(shifu_bid=identity).delete()


def test_usage_scan_uses_latest_active_outline_and_hides_only_unused_custom_keys(
    app: object, variables: object
) -> None:
    usage = profiles.get_profile_variable_usage(app, variables.course)
    assert set(usage["used_keys"]) == {variables.keys["used"]}
    assert set(usage["unused_keys"]) == {
        variables.keys["unused"],
        variables.keys["old"],
    }
    result = profiles.hide_unused_profile_items(app, variables.course, "teacher")
    hidden = {item.profile_key: item.is_hidden for item in result}
    assert hidden[variables.keys["used"]] is False
    assert hidden[variables.keys["system"]] is False
    assert hidden[variables.keys["unused"]] is True
    assert hidden[variables.keys["old"]] is True
    with app.app_context():
        row = Variable.query.filter_by(
            shifu_bid=variables.course, key=variables.keys["unused"]
        ).one()
        assert row.updated_user_bid == "teacher"
        assert row.updated_at is not None


def test_hiding_without_any_unused_keys_preserves_existing_visibility(
    app: object, variables: object
) -> None:
    with app.app_context(), unit_of_work():
        DraftOutlineItem.query.filter_by(shifu_bid=variables.course, deleted=0).update(
            {"content": " ".join("{{" + key + "}}" for key in variables.keys.values())},
            synchronize_session=False,
        )
    result = profiles.hide_unused_profile_items(app, variables.course, "teacher")
    assert all(
        item.is_hidden is False
        for item in result
        if item.profile_key in variables.keys.values()
    )


def test_empty_hidden_selection_is_a_read_and_missing_course_is_rejected(
    app: object, variables: object
) -> None:
    result = profiles.update_profile_item_hidden_state(
        app, variables.course, [], hidden=True, user_id="teacher"
    )
    assert all(
        item.is_hidden is False
        for item in result
        if item.profile_key in variables.keys.values()
    )
    with pytest.raises(AppError):
        profiles.update_profile_item_hidden_state(
            app, "", [variables.keys["used"]], hidden=True, user_id="teacher"
        )
    with pytest.raises(AppError):
        profiles.get_profile_variable_usage(app, "")


@pytest.mark.parametrize(
    "conflict", ["system", "course", "missing", "other-course", "empty-key"]
)
def test_variable_rename_rejects_collisions_and_out_of_scope_ids_without_writes(
    app: object, variables: object, conflict: str
) -> None:
    with app.app_context():
        row = Variable.query.filter_by(
            shifu_bid=variables.course, key=variables.keys["used"]
        ).one()
        bid = row.variable_bid
    key = variables.keys[conflict] if conflict == "system" else variables.keys["unused"]
    if conflict == "empty-key":
        key = ""
    with pytest.raises(AppError):
        profiles.save_profile_item(
            app,
            "missing" if conflict == "missing" else bid,
            "other-course" if conflict == "other-course" else variables.course,
            "teacher",
            key,
        )
    with app.app_context():
        assert (
            Variable.query.filter_by(variable_bid=bid).one().key
            == variables.keys["used"]
        )


def test_variable_rename_keeps_identity_and_records_editor(
    app: object, variables: object
) -> None:
    with app.app_context():
        bid = (
            Variable.query.filter_by(
                shifu_bid=variables.course, key=variables.keys["used"]
            )
            .one()
            .variable_bid
        )
    result = profiles.save_profile_item(app, bid, variables.course, "editor", "renamed")
    assert result.profile_key == "renamed"
    with app.app_context():
        row = Variable.query.filter_by(variable_bid=bid).one()
        assert row.key == "renamed"
        assert row.updated_user_bid == "editor"


def test_quick_add_reuses_system_definition_and_validates_required_fields(
    app: object, variables: object
) -> None:
    result = profiles.add_profile_item_quick(
        app, variables.course, variables.keys["system"], "teacher"
    )
    assert result.profile_key == variables.keys["system"]
    with app.app_context():
        assert (
            Variable.query.filter_by(
                shifu_bid=variables.course, key=variables.keys["system"]
            ).count()
            == 0
        )
    for course, key in (("", "key"), (variables.course, "")):
        with pytest.raises(AppError):
            profiles.add_profile_item_quick(app, course, key, "teacher")


@pytest.mark.parametrize("system", [False, True])
def test_delete_soft_deletes_custom_definitions_and_protects_system_variables(
    app: object, variables: object, system: bool
) -> None:
    key = variables.keys["system" if system else "used"]
    with app.app_context():
        bid = Variable.query.filter_by(key=key).one().variable_bid
    if system:
        with pytest.raises(AppError):
            profiles.delete_profile_item(app, "teacher", bid)
    else:
        assert profiles.delete_profile_item(app, "teacher", bid) is True
        with pytest.raises(AppError):
            profiles.delete_profile_item(app, "teacher", bid)
    with app.app_context():
        row = Variable.query.filter_by(variable_bid=bid).one()
        assert row.deleted == int(not system)
        if not system:
            assert row.updated_user_bid == "teacher"


def test_system_variable_cannot_be_updated_by_a_teacher(app: object) -> None:
    with pytest.raises(AppError):
        profiles.save_profile_item(app, "", "", "teacher", "new-system-key")


@pytest.fixture
def legacy_app(tmp_path: Path) -> object:
    app = Flask("legacy-profile-contracts")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'legacy.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={},
    )
    db.init_app(app)
    with app.app_context():
        event.listen(
            db.engine,
            "connect",
            lambda connection, _record: connection.create_function(
                "NOW", 0, lambda: "2026-09-20 00:00:00"
            ),
        )
        fields = [
            "profile_id",
            "parent_id",
            "profile_key",
            "profile_type",
            "profile_value_type",
            "profile_show_type",
            "profile_remark",
            "profile_prompt_type",
            "profile_raw_prompt",
            "profile_prompt",
            "profile_prompt_model",
            "profile_prompt_model_args",
            "profile_color_setting",
            "profile_script_id",
            "created",
            "updated",
            "created_by",
            "updated_by",
        ]
        db.session.execute(
            text(
                "CREATE TABLE profile_item (id INTEGER PRIMARY KEY, "
                "profile_index INTEGER, status INTEGER, "
                + ", ".join(f"{field} TEXT" for field in fields)
                + ")"
            )
        )
        db.session.execute(
            text(
                "CREATE TABLE profile_item_i18n (id INTEGER PRIMARY KEY, "
                "parent_id TEXT, conf_type INTEGER, language TEXT, "
                "profile_item_remark TEXT, created TEXT, updated TEXT, "
                "status INTEGER, created_by TEXT, updated_by TEXT)"
            )
        )
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize("parent", ["course", ""])
def test_legacy_quick_add_reuses_active_identity_and_increments_index(
    legacy_app: object, parent: str
) -> None:
    with legacy_app.app_context(), unit_of_work():
        first = profiles.add_profile_item_quick_internal(
            legacy_app, parent, "first", "teacher"
        )
        duplicate = profiles.add_profile_item_quick_internal(
            legacy_app, parent, "first", "other-editor"
        )
        second = profiles.add_profile_item_quick_internal(
            legacy_app, parent, "second", "teacher"
        )
        assert first.profile_id == duplicate.profile_id
        assert second.profile_id != first.profile_id
        assert first.profile_scope == (
            profiles.CONST_PROFILE_SCOPE_USER
            if parent
            else profiles.CONST_PROFILE_SCOPE_SYSTEM
        )
        rows = (
            db.session.execute(
                text("SELECT * FROM profile_item ORDER BY profile_index")
            )
            .mappings()
            .all()
        )
        assert [row["profile_index"] for row in rows] == [1, 2]
        assert [row["profile_key"] for row in rows] == ["first", "second"]
        assert all(row["created_by"] == "teacher" for row in rows)
        assert all(row["status"] == 1 and row["parent_id"] == parent for row in rows)


def test_legacy_i18n_is_idempotent_per_language_and_preserves_first_remark(
    legacy_app: object,
) -> None:
    with legacy_app.app_context(), unit_of_work():
        for language, remark in (
            ("en-US", "First"),
            ("en-US", "Ignored"),
            ("zh-CN", ""),
        ):
            profiles.add_profile_i18n(
                legacy_app, "profile-id", 1, language, remark, "teacher"
            )
        rows = (
            db.session.execute(text("SELECT * FROM profile_item_i18n ORDER BY id"))
            .mappings()
            .all()
        )
        assert [(row["language"], row["profile_item_remark"]) for row in rows] == [
            ("en-US", "First"),
            ("zh-CN", ""),
        ]
        assert all(
            row["created_by"] == "teacher" and row["status"] == 1 for row in rows
        )

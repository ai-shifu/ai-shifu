"""Verify variable-definition scope, usage discovery, and persisted edits."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.profile import profile_manage as profiles
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.shifu.models import DraftOutlineItem
from markdownflow.syntax.parser.interaction import InteractionParser, InteractionType
from sqlalchemy import MetaData, String, event, text


@pytest.fixture
def variables(app: object) -> object:
    identity = uuid.uuid4().hex
    keys = {name: f"{name}_{identity}" for name in ("used", "unused", "old", "system")}
    keys["system"] = "sys_user_language"
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
        VariableValue.query.filter_by(shifu_bid=identity).delete(
            synchronize_session=False
        )
        Variable.query.filter(
            (Variable.shifu_bid == identity) | Variable.key.in_(list(keys.values()))
        ).delete(synchronize_session=False)
        DraftOutlineItem.query.filter_by(shifu_bid=identity).delete()


def test_definition_list_preserves_fixed_text_fields_and_scope(
    app: object, variables: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(profiles, "_", lambda key: f"label:{key}")
    definitions = {
        item.profile_key: item.__json__()
        for item in profiles.get_profile_item_definition_list(app, variables.course)
        if item.profile_key in variables.keys.values()
    }

    assert set(definitions) == set(variables.keys.values())
    assert {item["profile_type"] for item in definitions.values()} == {"text"}
    assert {item["profile_type_str"] for item in definitions.values()} == {
        "label:PROFILE.PROFILE_TYPE_TEXT"
    }
    assert definitions[variables.keys["system"]]["profile_scope"] == "system"
    assert definitions[variables.keys["used"]]["profile_scope"] == "user"


@pytest.mark.parametrize(
    ("body", "expected_type"),
    [
        ("First//first | Second//second", InteractionType.BUTTONS_ONLY),
        ("First//first || Second//second", InteractionType.BUTTONS_MULTI_SELECT),
        ("...Write your answer", InteractionType.TEXT_ONLY),
    ],
)
def test_definition_reuse_preserves_answers_and_authored_question_types(
    app: object, variables: object, body: str, expected_type: InteractionType
) -> None:
    key = variables.keys["used"]
    content = "?[%{{ " + key + " }} " + body + "]"
    identity = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        definition = Variable.query.filter_by(shifu_bid=variables.course, key=key).one()
        definition_id = definition.variable_bid
        db.session.add(
            VariableValue(
                variable_value_bid=identity,
                variable_bid=definition_id,
                user_bid=identity,
                shifu_bid=variables.course,
                key=key,
                value="Previously accepted answer",
            )
        )
        outline = DraftOutlineItem(
            shifu_bid=variables.course,
            outline_item_bid=identity,
            content=content,
            position=0,
            deleted=0,
        )
        db.session.add(outline)
        db.session.flush()
        outline_id = outline.id

    parser = InteractionParser()
    original_control = parser.parse(content)
    assert original_control["type"] is expected_type
    if expected_type is not InteractionType.TEXT_ONLY:
        assert original_control["buttons"] == [
            {"display": "First", "value": "first"},
            {"display": "Second", "value": "second"},
        ]

    with app.app_context(), unit_of_work():
        reused = profiles.add_profile_item_quick_internal(
            app, variables.course, key, "teacher"
        )
    assert reused.profile_id == definition_id
    assert reused.profile_type == "text"
    with app.app_context():
        answer = VariableValue.query.filter_by(variable_value_bid=identity).one()
        assert answer.value == "Previously accepted answer"
        assert answer.key == key
        assert answer.variable_bid == definition_id
        stored_outline = db.session.get(DraftOutlineItem, outline_id)
        assert stored_outline is not None
        assert stored_outline.content == content
        assert parser.parse(stored_outline.content) == original_control


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


def test_course_definition_rejects_trimmed_registered_system_key(
    app: object, variables: object
) -> None:
    with app.app_context(), pytest.raises(AppError) as exc, unit_of_work():
        profiles.add_profile_item_quick_internal(
            app, variables.course, f"  {variables.keys['system']}  ", "teacher"
        )
    assert exc.value.code == ERROR_CODE["server.profile.keyReserved"]
    with app.app_context():
        assert (
            Variable.query.filter_by(
                shifu_bid=variables.course, key=variables.keys["system"]
            ).count()
            == 0
        )


@pytest.mark.parametrize(
    "raw_key",
    [
        "  Your name?  ",
        "\u00a0你的[性别] | 是//什么...？\u3000",
        "user  name",
        '"quoted" \\path',
        "a{b}c",
        "a}",
        "\ufeff key \ufeff",
    ],
)
def test_definition_creation_uses_the_script_key_after_trimming_only_its_edges(
    app: object, variables: object, raw_key: str
) -> None:
    expected = raw_key.strip()
    with app.app_context(), unit_of_work():
        result = profiles.add_profile_item_quick_internal(
            app, variables.course, raw_key, "teacher"
        )
    assert result.profile_key == expected
    with app.app_context():
        assert (
            Variable.query.filter_by(variable_bid=result.profile_id).one().key
            == expected
        )


@pytest.mark.parametrize(
    "key", ["  ", "a}}b", "a\x00b", "a\tb", "a\nb", "a\u2028b", 42]
)
def test_definition_creation_rejects_unrepresentable_keys_without_writes(
    app: object, variables: object, key: object
) -> None:
    with app.app_context():
        before = Variable.query.filter_by(shifu_bid=variables.course).count()
    with app.app_context(), pytest.raises(AppError), unit_of_work():
        profiles.add_profile_item_quick_internal(app, variables.course, key, "teacher")
    with app.app_context():
        assert Variable.query.filter_by(shifu_bid=variables.course).count() == before


@pytest.mark.parametrize(
    "key",
    [
        "sys_",
        "sys_custom_question",
        "sys_user_language",
        "sys_user_style",
        "\u00a0sys_name\u3000",
    ],
)
def test_course_definition_rejects_system_prefix_without_writes(
    app: object, variables: object, key: str
) -> None:
    with app.app_context():
        before = Variable.query.filter_by(shifu_bid=variables.course).count()
    with app.app_context(), pytest.raises(AppError) as exc, unit_of_work():
        profiles.add_profile_item_quick_internal(app, variables.course, key, "teacher")
    assert exc.value.code == ERROR_CODE["server.profile.keyReserved"]
    with app.app_context():
        assert Variable.query.filter_by(shifu_bid=variables.course).count() == before


def test_course_definition_cannot_reuse_a_system_prefixed_definition(
    app: object, variables: object
) -> None:
    key = f"sys_global_{uuid.uuid4().hex}"
    definition_bid = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        db.session.add(Variable(variable_bid=definition_bid, shifu_bid="", key=key))
    try:
        with app.app_context(), pytest.raises(AppError) as exc, unit_of_work():
            profiles.add_profile_item_quick_internal(
                app, variables.course, key, "teacher"
            )
        assert exc.value.code == ERROR_CODE["server.profile.keyReserved"]
        with app.app_context():
            rows = Variable.query.filter_by(key=key).all()
            assert [(row.variable_bid, row.shifu_bid) for row in rows] == [
                (definition_bid, "")
            ]
    finally:
        with app.app_context(), unit_of_work():
            Variable.query.filter_by(variable_bid=definition_bid).delete()


@pytest.mark.parametrize(
    "key",
    [
        "sys_",
        "sys_custom_question",
        "sys_user_language",
        "sys_user_nickname",
        "sys_user_background",
    ],
)
def test_legacy_runtime_option_never_allows_other_system_definitions(
    app: object, variables: object, key: str
) -> None:
    with app.app_context(), pytest.raises(AppError) as exc, unit_of_work():
        profiles.add_profile_item_quick_internal(
            app, variables.course, key, "learner", allow_legacy_runtime_profile=True
        )
    assert exc.value.code == ERROR_CODE["server.profile.keyReserved"]
    with app.app_context():
        assert (
            Variable.query.filter_by(shifu_bid=variables.course, key=key).count() == 0
        )


def test_legacy_runtime_option_never_creates_a_global_retired_definition(
    app: object,
) -> None:
    with app.app_context():
        before = Variable.query.filter_by(shifu_bid="", key="sys_user_style").count()
    with app.app_context(), pytest.raises(AppError), unit_of_work():
        profiles.add_profile_item_quick_internal(
            app, "", "sys_user_style", "learner", allow_legacy_runtime_profile=True
        )
    with app.app_context():
        assert (
            Variable.query.filter_by(shifu_bid="", key="sys_user_style").count()
            == before
        )


@pytest.mark.parametrize("prefix", ["SYS_", "course_sys_"])
def test_course_definition_reserves_only_the_exact_leading_system_prefix(
    app: object, variables: object, prefix: str
) -> None:
    key = f"{prefix}{uuid.uuid4().hex}"
    with app.app_context(), unit_of_work():
        result = profiles.add_profile_item_quick_internal(
            app, variables.course, key, "teacher"
        )
    with app.app_context():
        definition = Variable.query.filter_by(variable_bid=result.profile_id).one()
        assert definition.key == key
        assert definition.shifu_bid == variables.course


@pytest.fixture
def case_folding_app(tmp_path: Path) -> object:
    app = Flask("case-folding-variable-contracts")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'case-folding.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={},
    )
    db.init_app(app)
    table = Variable.__table__.to_metadata(MetaData())
    table.c.key.type = String(255, collation="NOCASE")
    with app.app_context():
        table.create(db.engine)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_definition_identity_remains_exact_under_a_case_folding_database(
    case_folding_app: object,
) -> None:
    app = case_folding_app
    with app.app_context(), unit_of_work():
        db.session.add(
            Variable(variable_bid="system-Name", shifu_bid="", key="Name", deleted=0)
        )
    with app.app_context(), unit_of_work():
        lower = profiles.add_profile_item_quick_internal(
            app, "course", " name ", "teacher"
        )
        upper = profiles.add_profile_item_quick_internal(
            app, "course", " Name ", "teacher"
        )
        duplicate = profiles.add_profile_item_quick_internal(
            app, "course", " name ", "other-editor"
        )
    assert duplicate.profile_id == lower.profile_id
    assert lower.profile_key == "name"
    assert upper.profile_key == "Name"
    assert lower.profile_id != upper.profile_id
    with app.app_context():
        assert [row.key for row in Variable.query.filter_by(shifu_bid="course")] == [
            "name",
            "Name",
        ]


@pytest.mark.parametrize("hidden", [False, True])
def test_hidden_updates_select_exact_keys_under_a_case_folding_database(
    case_folding_app: object, hidden: bool
) -> None:
    app = case_folding_app
    with app.app_context(), unit_of_work():
        for key in ("Goal?", "goal?"):
            profiles.add_profile_item_quick_internal(app, "course", key, "teacher")
    with app.app_context(), unit_of_work():
        for row in Variable.query.filter_by(shifu_bid="course"):
            row.is_hidden = int(not hidden)

    result = profiles.update_profile_item_hidden_state(
        app, "course", ["goal?"], hidden, "teacher"
    )
    assert {item.profile_key: item.is_hidden for item in result} == {
        "Goal?": not hidden,
        "goal?": hidden,
    }
    with app.app_context():
        assert {
            row.key: bool(row.is_hidden)
            for row in Variable.query.filter_by(shifu_bid="course")
        } == {"Goal?": not hidden, "goal?": hidden}


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
                + ", ".join(
                    f"{field} TEXT COLLATE NOCASE"
                    if field == "profile_key"
                    else f"{field} TEXT"
                    for field in fields
                )
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
    first_key = "first" if parent else "sys_user_nickname"
    second_key = "second" if parent else "sys_user_language"
    with legacy_app.app_context(), unit_of_work():
        first = profiles.add_profile_item_quick_internal(
            legacy_app, parent, first_key, "teacher"
        )
        duplicate = profiles.add_profile_item_quick_internal(
            legacy_app, parent, first_key, "other-editor"
        )
        second = profiles.add_profile_item_quick_internal(
            legacy_app, parent, second_key, "teacher"
        )
        assert first.profile_id == duplicate.profile_id
        assert second.profile_id != first.profile_id
        assert (
            first.profile_type
            == duplicate.profile_type
            == second.profile_type
            == "text"
        )
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
        assert [row["profile_key"] for row in rows] == [first_key, second_key]
        assert all(row["created_by"] == "teacher" for row in rows)
        assert all(row["status"] == 1 and row["parent_id"] == parent for row in rows)
        assert all(
            int(row["profile_type"]) == profiles.PROFILE_TYPE_INPUT_TEXT for row in rows
        )


def test_legacy_definition_reuse_uses_exact_keys_with_a_case_folding_column(
    legacy_app: object,
) -> None:
    with legacy_app.app_context(), unit_of_work():
        upper = profiles.add_profile_item_quick_internal(
            legacy_app, "course", "Name", "teacher"
        )
        lower = profiles.add_profile_item_quick_internal(
            legacy_app, "course", " name ", "teacher"
        )
        duplicate = profiles.add_profile_item_quick_internal(
            legacy_app, "course", " Name ", "teacher"
        )
        assert upper.profile_key == "Name"
        assert lower.profile_key == "name"
        assert upper.profile_id != lower.profile_id
        assert duplicate.profile_id == upper.profile_id

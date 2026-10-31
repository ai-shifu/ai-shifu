"""Retire built-in fields without changing their historical stored records."""

from datetime import date
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn.memory.reader import load_course_variables
from flaskr.service.profile import funcs, profile_manage
from flaskr.service.profile.constants import ACTIVE_SYSTEM_PROFILE_KEYS
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.repository import (
    UserEntity,
    create_user_entity,
    load_user_aggregate,
)


@pytest.fixture
def retired_profile_user(app: object) -> object:
    identity = uuid4().hex
    with app.app_context(), unit_of_work():
        create_user_entity(
            user_bid=identity,
            identify=identity,
            nickname="Current nickname",
            language="en-US",
            avatar="current-avatar.png",
            birthday=date(2000, 1, 2),
        )
    yield SimpleNamespace(app=app, bid=identity, course=f"course-{identity}")
    with app.app_context(), unit_of_work():
        VariableValue.query.filter_by(user_bid=identity).delete()
        Variable.query.filter(
            (Variable.shifu_bid == f"course-{identity}")
            | Variable.variable_bid.like(f"{identity}-%")
        ).delete(synchronize_session=False)
        UserEntity.query.filter_by(user_bid=identity).delete()


@pytest.mark.parametrize(
    "key", ["sex", "birth", "avatar", "language", "sys_user_style", "favorite_color"]
)
@pytest.mark.parametrize("writer", ["runtime", "settings"])
def test_custom_course_values_do_not_use_or_change_global_definitions(
    retired_profile_user: object,
    key: str,
    writer: str,
) -> None:
    user = retired_profile_user
    global_definition_bid = f"{user.bid}-global-{key}"
    local_definition_bid = f"{user.bid}-local-{key}"
    with user.app.app_context(), unit_of_work():
        db.session.add(
            Variable(variable_bid=global_definition_bid, shifu_bid="", key=key)
        )
        db.session.add(
            VariableValue(
                variable_value_bid=uuid4().hex,
                user_bid=user.bid,
                shifu_bid="",
                key=key,
                value="Historical global value",
            )
        )
    with user.app.app_context():
        old_rows = {
            row.id: (row.key, row.value, row.deleted)
            for row in VariableValue.query.filter_by(user_bid=user.bid).all()
        }
        assert key not in {
            item.profile_key
            for item in profile_manage.get_profile_item_definition_list(
                user.app, user.course
            )
        }
        assert key not in funcs.get_user_profiles(user.app, user.bid, user.course)
        assert set(funcs.get_profile_labels()) == ACTIVE_SYSTEM_PROFILE_KEYS
        assert {
            item.key
            for item in funcs.get_user_profile_labels(
                user.app, user.bid, user.course
            ).profiles
        } == ACTIVE_SYSTEM_PROFILE_KEYS
        with unit_of_work():
            # Model an existing course definition without granting new sys_ declarations.
            db.session.add(
                Variable(
                    variable_bid=local_definition_bid, shifu_bid=user.course, key=key
                )
            )
            if writer == "runtime":
                funcs.save_user_profiles(
                    user.app,
                    user.bid,
                    user.course,
                    [ProfileToSave(key, "Course value", local_definition_bid)],
                )
            else:
                funcs.update_user_profile_with_lable(
                    user.app,
                    user.bid,
                    [{"key": key, "value": "Course value"}],
                    course_id=user.course,
                )
        db.session.remove()
        local_definition = next(
            item
            for item in profile_manage.get_profile_item_definition_list(
                user.app, user.course
            )
            if item.profile_key == key
        )
        assert (local_definition.profile_scope, local_definition.profile_id) == (
            "user",
            local_definition_bid,
        )
        row = VariableValue.query.filter_by(
            user_bid=user.bid, shifu_bid=user.course, key=key
        ).one()
        assert row.variable_bid == local_definition_bid
        assert (
            funcs.get_user_profiles(user.app, user.bid, user.course)[key]
            == "Course value"
        )
        assert key not in funcs.get_user_profiles(user.app, user.bid, "other-course")
        account = load_user_aggregate(user.bid)
        assert (account.avatar, account.language, account.birthday) == (
            "current-avatar.png",
            "en-US",
            date(2000, 1, 2),
        )
        assert {
            row.id: (row.key, row.value, row.deleted)
            for row in VariableValue.query.filter_by(
                user_bid=user.bid, shifu_bid=""
            ).all()
        } == old_rows
        global_definition = Variable.query.filter_by(
            variable_bid=global_definition_bid
        ).one()
        assert (
            global_definition.shifu_bid,
            global_definition.key,
            global_definition.deleted,
        ) == (
            "",
            key,
            0,
        )


@pytest.mark.parametrize("writer", ["runtime", "settings"])
@pytest.mark.parametrize("course_id", [None, "", "   "])
def test_custom_writes_require_course_before_any_system_write_or_moderation(
    retired_profile_user: object,
    monkeypatch: pytest.MonkeyPatch,
    writer: str,
    course_id: str | None,
) -> None:
    user = retired_profile_user
    with user.app.app_context():
        checked = []
        monkeypatch.setattr(
            funcs, "check_text_content", lambda *_args: checked.append(True)
        )
        if writer == "runtime":
            write_profiles = partial(
                funcs.save_user_profiles,
                user.app,
                user.bid,
                course_id,
                [
                    ProfileToSave("sys_user_nickname", "Changed", ""),
                    ProfileToSave("sex", "Local", ""),
                ],
            )
        else:
            write_profiles = partial(
                funcs.update_user_profile_with_lable,
                user.app,
                user.bid,
                [
                    {"key": "sys_user_nickname", "value": "Changed"},
                    {"key": "sex", "value": "Local"},
                ],
                course_id=course_id,
            )
        with pytest.raises(AppError) as error:
            write_profiles()
        assert error.value.code == ERROR_CODE["server.common.paramsError"]
        assert checked == []
        assert load_user_aggregate(user.bid).nickname == "Current nickname"
        assert VariableValue.query.filter_by(user_bid=user.bid).count() == 0


def test_profile_update_api_keeps_envelope_and_rejects_unscoped_retired_fields(
    retired_profile_user: object,
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = retired_profile_user
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda *_args: SimpleNamespace(user_id=user.bid, language="en-US"),
    )
    response = test_client.post(
        "/api/user/update_profile",
        json={"profiles": [{"key": "avatar", "value": "old.png"}]},
    )
    payload = response.get_json()
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]
    assert "message" in payload
    with user.app.app_context():
        assert load_user_aggregate(user.bid).avatar == "current-avatar.png"
        assert VariableValue.query.filter_by(user_bid=user.bid).count() == 0


@pytest.mark.parametrize(
    "key",
    [
        "sex",
        "birth",
        "avatar",
        "language",
        "sys_user_style",
        "learner_requested_note",
        "SYS_USER_STYLE",
    ],
)
@pytest.mark.parametrize("writer", ["runtime", "settings"])
def test_undeclared_course_values_never_gain_a_definition(
    retired_profile_user: object,
    key: str,
    writer: str,
) -> None:
    user = retired_profile_user
    with user.app.app_context(), unit_of_work():
        if writer == "runtime":
            funcs.save_user_profiles(
                user.app,
                user.bid,
                user.course,
                [ProfileToSave(key, "Requested note", "")],
            )
        else:
            funcs.update_user_profile_with_lable(
                user.app,
                user.bid,
                [{"key": key, "value": "Requested note"}],
                course_id=user.course,
            )
    with user.app.app_context():
        assert Variable.query.filter_by(shifu_bid=user.course, key=key).count() == 0
        assert key not in funcs.get_user_profiles(user.app, user.bid, user.course)
        row = VariableValue.query.filter_by(
            user_bid=user.bid, shifu_bid=user.course, key=key
        ).one()
        assert (row.value, row.variable_bid) == ("Requested note", "")
        supplementary = load_course_variables(user.bid, user.course)
        if key.startswith("sys_"):
            assert key not in supplementary
        else:
            assert supplementary[key] == "Requested note"


@pytest.mark.parametrize("key", ["language", "sys_user_style", "favorite_color"])
def test_course_value_keeps_supplied_definition_id_and_reads_by_course_key(
    retired_profile_user: object, key: str
) -> None:
    user = retired_profile_user
    supplied_bid = f"{user.bid}-old-global-{key}"
    local_bid = f"{user.bid}-current-course-{key}"
    global_value_bid = uuid4().hex
    with user.app.app_context(), unit_of_work():
        db.session.add_all(
            [
                Variable(variable_bid=supplied_bid, shifu_bid="", key=key),
                Variable(variable_bid=local_bid, shifu_bid=user.course, key=key),
                VariableValue(
                    variable_value_bid=global_value_bid,
                    variable_bid=supplied_bid,
                    user_bid=user.bid,
                    shifu_bid="",
                    key=key,
                    value="Existing global value",
                ),
            ]
        )
    with user.app.app_context():
        with unit_of_work():
            funcs.save_user_profiles(
                user.app,
                user.bid,
                user.course,
                [ProfileToSave(key, "Current course value", supplied_bid)],
            )
        db.session.expire_all()
        row = VariableValue.query.filter_by(
            user_bid=user.bid, shifu_bid=user.course, key=key
        ).one()
        assert row.variable_bid == supplied_bid
        assert funcs.get_user_profiles(user.app, user.bid, user.course)[key] == (
            "Current course value"
        )
        assert key not in funcs.get_user_profiles(user.app, user.bid, "other-course")
        historical = VariableValue.query.filter_by(
            variable_value_bid=global_value_bid
        ).one()
        assert (
            historical.variable_bid,
            historical.shifu_bid,
            historical.key,
            historical.value,
            historical.deleted,
        ) == (supplied_bid, "", key, "Existing global value", 0)

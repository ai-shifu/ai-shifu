"""Retire built-in fields without changing their historical stored records."""

from datetime import date
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.profile import funcs, profile_manage
from flaskr.service.profile.constants import (
    ACTIVE_SYSTEM_PROFILE_KEYS,
    RETIRED_PROFILE_KEYS,
)
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.shifu.question_validation import (
    assert_course_question_names_allowed,
)
from flaskr.service.user.repository import (
    UserEntity,
    create_user_entity,
    load_user_aggregate,
)
from markdownflow import MarkdownFlowDocument


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


@pytest.mark.parametrize("writer", ["runtime", "settings"])
def test_retired_global_definitions_and_values_stay_stored_but_are_not_active(
    retired_profile_user: object,
    writer: str,
) -> None:
    user = retired_profile_user
    with user.app.app_context(), unit_of_work():
        for key in RETIRED_PROFILE_KEYS:
            db.session.add(
                Variable(variable_bid=f"{user.bid}-global-{key}", shifu_bid="", key=key)
            )
            db.session.add(
                VariableValue(
                    variable_value_bid=uuid4().hex,
                    user_bid=user.bid,
                    shifu_bid="",
                    key=key,
                    value=f"Old global {key}",
                )
            )
    with user.app.app_context():
        old_rows = {
            row.id: (row.key, row.value, row.deleted)
            for row in VariableValue.query.filter_by(user_bid=user.bid).all()
        }
        definitions = profile_manage.get_profile_item_definition_list(
            user.app, user.course
        )
        assert not (RETIRED_PROFILE_KEYS & {item.profile_key for item in definitions})
        assert not (
            RETIRED_PROFILE_KEYS
            & funcs.get_user_profiles(user.app, user.bid, user.course).keys()
        )
        assert set(funcs.get_profile_labels()) == ACTIVE_SYSTEM_PROFILE_KEYS
        assert {
            item.key
            for item in funcs.get_user_profile_labels(
                user.app, user.bid, user.course
            ).profiles
        } == ACTIVE_SYSTEM_PROFILE_KEYS
        with unit_of_work():
            if writer == "runtime":
                funcs.save_user_profiles(
                    user.app,
                    user.bid,
                    user.course,
                    [
                        ProfileToSave(key, f"Local {key}", f"{user.bid}-global-{key}")
                        for key in RETIRED_PROFILE_KEYS
                    ],
                )
            else:
                funcs.update_user_profile_with_lable(
                    user.app,
                    user.bid,
                    [
                        {"key": key, "value": f"Local {key}"}
                        for key in RETIRED_PROFILE_KEYS
                    ],
                    course_id=user.course,
                )
        db.session.remove()
        local_definitions = {
            item.profile_key: item
            for item in profile_manage.get_profile_item_definition_list(
                user.app, user.course
            )
            if item.profile_key in RETIRED_PROFILE_KEYS
        }
        assert set(local_definitions) == RETIRED_PROFILE_KEYS
        for key, item in local_definitions.items():
            assert item.profile_scope == "user"
            assert item.profile_id != f"{user.bid}-global-{key}"
            row = VariableValue.query.filter_by(
                user_bid=user.bid, shifu_bid=user.course, key=key
            ).one()
            assert row.variable_bid == item.profile_id
        runtime = funcs.get_user_profiles(user.app, user.bid, user.course)
        for key in RETIRED_PROFILE_KEYS:
            assert runtime[key] == f"Local {key}"
        assert not (
            RETIRED_PROFILE_KEYS
            & funcs.get_user_profiles(user.app, user.bid, "other-course").keys()
        )
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
        assert Variable.query.filter(
            Variable.variable_bid.in_(
                [f"{user.bid}-global-{key}" for key in RETIRED_PROFILE_KEYS]
            )
        ).count() == len(RETIRED_PROFILE_KEYS)


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


@pytest.mark.parametrize("key", ["learner_requested_note", "SYS_USER_STYLE"])
def test_unrelated_undeclared_memory_never_gains_a_definition(
    retired_profile_user: object, key: str
) -> None:
    user = retired_profile_user
    with user.app.app_context(), unit_of_work():
        funcs.save_user_profiles(
            user.app, user.bid, user.course, [ProfileToSave(key, "Requested note", "")]
        )
    with user.app.app_context():
        assert Variable.query.filter_by(shifu_bid=user.course, key=key).count() == 0
        assert key not in funcs.get_user_profiles(user.app, user.bid, user.course)


@pytest.mark.parametrize("marker", ["{{sys_user_style}}", "%{{sys_user_style}}"])
def test_legacy_runtime_definition_never_allows_new_reserved_question_bindings(
    retired_profile_user: object, marker: str
) -> None:
    user = retired_profile_user
    with user.app.app_context(), unit_of_work():
        funcs.save_user_profiles(
            user.app,
            user.bid,
            user.course,
            [ProfileToSave("sys_user_style", "Legacy published-course answer", "")],
        )
    document = MarkdownFlowDocument(f"?[{marker}...Answer]")
    with pytest.raises(AppError) as error:
        assert_course_question_names_allowed(document)
    assert error.value.code == ERROR_CODE["server.profile.keyReserved"]
    with user.app.app_context():
        assert funcs.get_user_profiles(user.app, user.bid, user.course)[
            "sys_user_style"
        ] == ("Legacy published-course answer")

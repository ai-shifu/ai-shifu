"""Keep profile-label writes aligned with canonical user fields and scoped values."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.profile import funcs
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.dtos import UserProfileLabelDTO, UserProfileLabelItemDTO
from flaskr.service.user.repository import (
    UserEntity,
    create_user_entity,
    load_user_aggregate,
)


@pytest.fixture
def user(app: object, monkeypatch: pytest.MonkeyPatch) -> object:
    key = uuid.uuid4().hex
    monkeypatch.setattr(funcs, "get_profile_item_definition_list", lambda *_a: [])
    with app.app_context():
        with unit_of_work():
            create_user_entity(
                user_bid=key, identify=key, nickname="Original", language="en-US"
            )
        yield SimpleNamespace(app=app, bid=key)
        with unit_of_work():
            VariableValue.query.filter_by(user_bid=key).delete()
            Variable.query.filter_by(created_user_bid=key).delete()
            UserEntity.query.filter_by(user_bid=key).delete()


def _label(key: str, value: object) -> UserProfileLabelItemDTO:
    return UserProfileLabelItemDTO(
        key=key, value=value, label=key, type="text", items=None
    )


@pytest.mark.parametrize(
    "key", ["sex", "birth", "avatar", "language", "sys_user_style"]
)
def test_retired_profile_label_writes_are_course_scoped(user: object, key: str) -> None:
    with unit_of_work():
        funcs.update_user_profile_with_lable(
            user.app,
            user.bid,
            _label(key, "Course value"),
            update_all=True,
            course_id="course",
        )
    db.session.expire_all()
    account = load_user_aggregate(user.bid)
    assert account.birthday is None
    assert account.avatar == ""
    assert account.language == "en-US"
    row = VariableValue.query.filter_by(user_bid=user.bid, key=key).one()
    assert (row.value, row.shifu_bid) == ("Course value", "course")
    assert key not in funcs.get_user_profiles(user.app, user.bid, "another-course")


def test_profile_dto_saves_course_avatar_without_changing_account_or_empty_keys(
    user: object,
) -> None:
    payload = UserProfileLabelDTO(
        profiles=[_label("avatar", "avatar.png"), _label("", "ignored")],
        language="en-US",
    )
    for _ in range(2):
        with unit_of_work():
            assert (
                funcs.update_user_profile_with_lable(
                    user.app, user.bid, payload, course_id="course"
                )
                is True
            )
    db.session.expire_all()
    assert load_user_aggregate(user.bid).avatar == ""
    values = VariableValue.query.filter_by(user_bid=user.bid).all()
    assert [(item.key, item.value, item.shifu_bid) for item in values] == [
        ("avatar", "avatar.png", "course")
    ]
    labels = funcs.get_user_profile_labels(user.app, user.bid, "course")
    assert "avatar" not in {item.key for item in labels.profiles}


def test_empty_profile_update_can_initialize_missing_user_without_variable_writes(
    user: object,
) -> None:
    with unit_of_work():
        UserEntity.query.filter_by(user_bid=user.bid).delete()
    assert load_user_aggregate(user.bid) is None
    with unit_of_work():
        assert (
            funcs.update_user_profile_with_lable(
                user.app, user.bid, [], course_id="course"
            )
            is True
        )
    db.session.expire_all()
    assert load_user_aggregate(user.bid) is not None
    assert VariableValue.query.filter_by(user_bid=user.bid).count() == 0


@pytest.mark.parametrize("legacy", ["not-a-number", "999"])
def test_retired_legacy_sex_value_is_not_displayed_or_rewritten(
    user: object, legacy: str
) -> None:
    with unit_of_work():
        db.session.add(
            VariableValue(
                variable_value_bid=uuid.uuid4().hex,
                user_bid=user.bid,
                variable_bid="sex",
                shifu_bid="",
                key="sex",
                value=legacy,
            )
        )
    labels = funcs.get_user_profile_labels(user.app, user.bid, "course").profiles
    assert "sex" not in {item.key for item in labels}
    assert (
        VariableValue.query.filter_by(user_bid=user.bid, key="sex").one().value
        == legacy
    )


def test_missing_birthday_does_not_read_retired_legacy_value(
    user: object,
) -> None:
    with unit_of_work():
        db.session.add(
            VariableValue(
                variable_value_bid=uuid.uuid4().hex,
                user_bid=user.bid,
                variable_bid="birth",
                shifu_bid="",
                key="birth",
                value="1999-08-07",
            )
        )
    assert load_user_aggregate(user.bid).birthday is None
    labels = funcs.get_user_profile_labels(user.app, user.bid, "course").profiles
    assert "birth" not in {item.key for item in labels}
    assert load_user_aggregate(user.bid).birthday is None


@pytest.mark.parametrize(
    "verdict", [funcs.CHECK_RESULT_PASS, funcs.CHECK_RESULT_REJECT, "unknown"]
)
def test_nickname_moderation_records_provider_verdict_and_rejects_only_explicit_failure(
    user: object,
    monkeypatch: pytest.MonkeyPatch,
    verdict: object,
) -> None:
    monkeypatch.setattr(
        funcs,
        "check_text",
        Mock(
            return_value=SimpleNamespace(
                provider="test-provider",
                check_result=verdict,
                raw_data={"result": verdict},
            )
        ),
    )
    audit = Mock()
    monkeypatch.setattr(funcs, "add_risk_control_result", audit)
    payload = [_label("sys_user_nickname", "Requested name")]
    if verdict == funcs.CHECK_RESULT_REJECT:
        with pytest.raises(AppError), unit_of_work():
            funcs.update_user_profile_with_lable(user.app, user.bid, payload)
    else:
        with unit_of_work():
            assert (
                funcs.update_user_profile_with_lable(user.app, user.bid, payload)
                is True
            )
    db.session.expire_all()
    assert load_user_aggregate(user.bid).nickname == (
        "Original" if verdict == funcs.CHECK_RESULT_REJECT else "Requested name"
    )
    assert VariableValue.query.filter_by(
        user_bid=user.bid, key="sys_user_nickname"
    ).count() == int(verdict != funcs.CHECK_RESULT_REJECT)
    audit.assert_called_once()
    assert audit.call_args.args[2:6] == (
        user.bid,
        "Requested name",
        "test-provider",
        verdict,
    )
    assert audit.call_args.args[-2:] == (
        int(verdict == funcs.CHECK_RESULT_PASS),
        "check_text",
    )


def test_labels_ignore_retired_global_and_course_style_values(
    user: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        funcs,
        "get_profile_item_definition_list",
        lambda *_a: [
            SimpleNamespace(profile_key="sys_user_style", profile_id="style-definition")
        ],
    )
    with unit_of_work():
        db.session.add_all(
            [
                VariableValue(
                    variable_value_bid=uuid.uuid4().hex,
                    user_bid=user.bid,
                    variable_bid="style-definition",
                    shifu_bid="",
                    key="sys_user_style",
                    value="Examples first",
                ),
                VariableValue(
                    variable_value_bid=uuid.uuid4().hex,
                    user_bid=user.bid,
                    variable_bid="style-definition",
                    shifu_bid="course",
                    key="sys_user_style",
                    value="Wrong course override",
                ),
            ]
        )
    labels = funcs.get_user_profile_labels(
        user.app, user.bid, "course", include_nickname=False, include_background=False
    ).profiles
    values = {item.key: item.value for item in labels}
    assert "sys_user_style" not in values
    assert (
        VariableValue.query.filter_by(user_bid=user.bid, key="sys_user_style").count()
        == 2
    )
    assert "sys_user_nickname" not in values
    assert "sys_user_background" not in values

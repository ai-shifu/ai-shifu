"""Keep profile-label writes aligned with canonical user fields and scoped values."""

import datetime
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.profile import funcs
from flaskr.service.profile.models import VariableValue
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
            UserEntity.query.filter_by(user_bid=key).delete()


def _label(key: str, value: object) -> UserProfileLabelItemDTO:
    return UserProfileLabelItemDTO(
        key=key, value=value, label=key, type="text", items=None
    )


@pytest.mark.parametrize(
    "raw",
    ["2020-02-29", datetime.date(2020, 2, 29), "2021-02-29", "not-a-date", None, ""],
)
def test_birth_label_normalizes_date_without_invalid_canonical_value(
    user: object, raw: object
) -> None:
    with unit_of_work():
        funcs.update_user_profile_with_lable(
            user.app, user.bid, _label("birth", raw), update_all=True
        )
    db.session.expire_all()
    expected = (
        datetime.date(2020, 2, 29)
        if raw in ("2020-02-29", datetime.date(2020, 2, 29))
        else None
    )
    assert load_user_aggregate(user.bid).birthday == expected
    runtime = funcs.get_user_profiles(user.app, user.bid, "course")
    if expected:
        assert runtime["birth"] == "2020-02-29"
    else:
        assert "birth" not in runtime


def test_profile_dto_updates_avatar_and_ignores_empty_keys(user: object) -> None:
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
    assert load_user_aggregate(user.bid).avatar == "avatar.png"
    values = VariableValue.query.filter_by(user_bid=user.bid).all()
    assert [(item.key, item.value, item.shifu_bid) for item in values] == [
        ("avatar", "avatar.png", "")
    ]
    labels = funcs.get_user_profile_labels(user.app, user.bid, "course")
    assert (
        next(item.value for item in labels.profiles if item.key == "avatar")
        == "avatar.png"
    )


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
def test_invalid_legacy_sex_value_uses_display_default_without_rewriting_storage(
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
    expected = funcs.get_profile_labels()["sex"]["items"][0]
    assert next(item.value for item in labels if item.key == "sex") == expected
    assert (
        VariableValue.query.filter_by(user_bid=user.bid, key="sex").one().value
        == legacy
    )


def test_missing_birthday_reads_legacy_value_without_replacing_canonical_field(
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
    assert next(item.value for item in labels if item.key == "birth") == "1999-08-07"
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


def test_labels_find_global_nonmapped_values_with_profile_definition(
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
    assert values["sys_user_style"] == "Examples first"
    assert "sys_user_nickname" not in values
    assert "sys_user_background" not in values

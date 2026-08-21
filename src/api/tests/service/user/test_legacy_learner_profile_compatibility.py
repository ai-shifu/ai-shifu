"""Verify legacy learner profile compatibility behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.funcs import (
    get_user_profiles,
    save_user_profiles,
    update_user_profile_with_lable,
)
from flaskr.service.profile.learner_profile import (
    PROFILE_ONBOARDING_SCENE_KEY,
    PROFILE_ONBOARDING_VERSION,
    replace_learner_profile,
)
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.common import update_user_info
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    create_user_entity,
    load_user_aggregate,
)
from flaskr.util.datetime import now_utc


def _create_user_with_v2_state(user_bid: str, *, status: str) -> None:
    create_user_entity(
        user_bid=user_bid,
        identify=user_bid,
        nickname="Test learner",
        language="zh-CN",
    )
    db.session.add(
        UserOnboardingState(
            user_bid=user_bid,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
            status=status,
            trigger_source="test",
            completed_at=now_utc(),
        )
    )
    db.session.commit()


def _active_legacy_values(user_bid: str) -> list[VariableValue]:
    return (
        VariableValue.query.filter(
            VariableValue.user_bid == user_bid,
            VariableValue.shifu_bid == "",
            VariableValue.key.in_(["sys_user_background", "sys_user_style"]),
            VariableValue.deleted == 0,
        )
        .order_by(VariableValue.id.asc())
        .all()
    )


@pytest.mark.parametrize(
    "writer",
    ["save", "label", "user-info"],
)
def test_legacy_nickname_writers_keep_pre_profile_mapping_behavior(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    writer: object,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.get_profile_item_definition_list",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        user_bid = f"legacy-nickname-lock-{writer}"
        create_user_entity(
            user_bid=user_bid,
            identify=user_bid,
            nickname="Before",
            language="en-US",
        )
        db.session.commit()
        aggregate = load_user_aggregate(user_bid)
        assert aggregate is not None
        user_dto = build_user_info_from_aggregate(aggregate)

        query_type = type(UserInfo.query)
        original_first = query_type.first
        reads: list[tuple[str, str, bool, bool]] = []

        def track_first(query: object) -> object:
            statement = str(query.statement)
            parameters = query.statement.compile().params
            table = (
                "user_onboarding_states"
                if "user_onboarding_states" in statement
                else "user_users"
                if "user_users" in statement
                else "other"
            )
            reads.append(
                (
                    table,
                    str(parameters.get("user_bid_1", "")),
                    query._for_update_arg is not None,
                    bool(query.load_options._populate_existing),
                )
            )
            return original_first(query)

        monkeypatch.setattr(query_type, "first", track_first)
        if writer == "save":
            save_user_profiles(
                app,
                user_bid,
                "",
                [ProfileToSave("sys_user_nickname", "After", None)],
            )
            db.session.commit()
        elif writer == "label":
            update_user_profile_with_lable(
                app,
                user_bid,
                [{"key": "sys_user_nickname", "value": "After"}],
                update_all=True,
            )
            db.session.commit()
        else:
            update_user_info(app, user_dto, name="After")

        assert not any(read[0] == "user_onboarding_states" for read in reads)

        db.session.expire_all()
        stored_user = UserInfo.query.filter_by(user_bid=user_bid).one()
        assert stored_user.nickname == "After"


def test_completed_v2_state_preserves_legacy_profile_read_write_paths(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    definitions = [
        SimpleNamespace(
            profile_key="sys_user_background", profile_id="background-variable"
        ),
        SimpleNamespace(profile_key="sys_user_style", profile_id="style-variable"),
    ]
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.get_profile_item_definition_list",
        lambda *_args, **_kwargs: definitions,
    )
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        user_bid = "profile-v2-legacy-compatible"
        _create_user_with_v2_state(user_bid, status="completed")

        save_user_profiles(
            app,
            user_bid,
            "course-one",
            [
                ProfileToSave("sys_user_background", "legacy background", None),
                ProfileToSave("sys_user_style", "legacy style", None),
            ],
        )
        update_user_profile_with_lable(
            app,
            user_bid,
            [
                {"key": "sys_user_background", "value": "another background"},
                {"key": "sys_user_style", "value": "another style"},
            ],
            course_id="course-one",
        )
        db.session.commit()

        profiles = get_user_profiles(app, user_bid, "course-one")
        values = _active_legacy_values(user_bid)

        assert [(value.key, value.value) for value in values] == [
            ("sys_user_background", "legacy background"),
            ("sys_user_style", "legacy style"),
            ("sys_user_background", "another background"),
            ("sys_user_style", "another style"),
        ]
        assert profiles["sys_user_background"] == "another background"
        assert profiles["sys_user_style"] == "another style"


def test_skipped_v2_state_preserves_legacy_profile_behavior(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.get_profile_item_definition_list",
        lambda *_args, **_kwargs: [],
    )

    with app.app_context():
        user_bid = "profile-v2-skipped-legacy"
        _create_user_with_v2_state(user_bid, status="skipped")

        save_user_profiles(
            app,
            user_bid,
            "course-one",
            [ProfileToSave("sys_user_background", "preserved background", None)],
        )
        db.session.commit()

        values = _active_legacy_values(user_bid)
        assert [(value.key, value.value) for value in values] == [
            ("sys_user_background", "preserved background")
        ]


def test_legacy_nickname_writers_still_update_user_and_runtime_nickname(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definitions = [
        SimpleNamespace(
            profile_key="sys_user_nickname",
            profile_id="nickname-variable",
        )
    ]
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.get_profile_item_definition_list",
        lambda *_args, **_kwargs: definitions,
    )
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        user_bid = "profile-v2-canonical-nickname"
        user = create_user_entity(
            user_bid=user_bid,
            identify=user_bid,
            nickname="Canonical Name",
            learner_profile="Please call me Canonical Name.",
            learner_profile_updated_at=now_utc(),
            language="en-US",
        )
        db.session.add(
            UserOnboardingState(
                user_bid=user_bid,
                scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                version=PROFILE_ONBOARDING_VERSION,
                status="completed",
                trigger_source="settings",
                completed_at=now_utc(),
            )
        )
        db.session.commit()

        save_user_profiles(
            app,
            user_bid,
            "",
            [ProfileToSave("sys_user_nickname", "Legacy One", None)],
        )
        update_user_profile_with_lable(
            app,
            user_bid,
            [{"key": "sys_user_nickname", "value": "Legacy Two"}],
        )
        db.session.commit()
        aggregate = load_user_aggregate(user_bid)
        assert aggregate is not None
        update_user_info(
            app,
            build_user_info_from_aggregate(aggregate),
            name="Legacy API",
        )
        db.session.expire_all()

        stored_user = db.session.get(UserInfo, user.id)
        legacy_values = (
            VariableValue.query.filter_by(
                user_bid=user_bid,
                shifu_bid="",
                key="sys_user_nickname",
                deleted=0,
            )
            .order_by(VariableValue.id.asc())
            .all()
        )
        runtime_profiles = get_user_profiles(app, user_bid, "")

        assert stored_user is not None
        assert stored_user.nickname == "Legacy API"
        assert [value.value for value in legacy_values] == [
            "Legacy One",
            "Legacy Two",
            "Legacy API",
        ]
        assert runtime_profiles["sys_user_nickname"] == "Legacy API"


def test_explicit_nickname_uses_existing_runtime_precedence_without_rewriting_legacy_rows(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        user_bid = "explicit-nickname-legacy-runtime"
        user = create_user_entity(
            user_bid=user_bid,
            identify=user_bid,
            nickname="Old account name",
            language="zh-CN",
        )
        db.session.add(
            VariableValue(
                variable_value_bid="explicit-nickname-legacy-row",
                variable_bid="",
                shifu_bid="",
                user_bid=user_bid,
                key="sys_user_nickname",
                value="Legacy row name",
            )
        )
        db.session.commit()

        replace_learner_profile(
            app,
            user_id=user_bid,
            learner_profile="",
            nickname="Explicit account name",
        )
        db.session.expire_all()

        stored_user = db.session.get(UserInfo, user.id)
        legacy_values = VariableValue.query.filter_by(
            user_bid=user_bid,
            shifu_bid="",
            key="sys_user_nickname",
            deleted=0,
        ).all()
        runtime_profiles = get_user_profiles(app, user_bid, "")

        assert stored_user is not None
        assert stored_user.nickname == "Explicit account name"
        assert [value.value for value in legacy_values] == ["Legacy row name"]
        assert runtime_profiles["sys_user_nickname"] == "Explicit account name"

from __future__ import annotations

from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.common.profile_onboarding import (
    PROFILE_ONBOARDING_SCENE_KEY,
    PROFILE_ONBOARDING_VERSION,
)
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.funcs import (
    get_user_profiles,
    save_user_profiles,
    update_user_profile_with_lable,
)
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.models import UserOnboardingState
from flaskr.service.user.repository import create_user_entity
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


def test_completed_v2_state_preserves_legacy_profile_read_write_paths(app, monkeypatch):
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


def test_skipped_v2_state_preserves_legacy_profile_behavior(app, monkeypatch):
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

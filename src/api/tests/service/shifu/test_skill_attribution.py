"""Verify Skill attribution is stored atomically with course creation."""

import pytest
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.common.skill_attribution import SkillAttributionInput
from flaskr.service.shifu.models import DraftShifu, ShifuSkillAttribution
from flaskr.service.shifu.shifu_draft_funcs import create_shifu_draft


def test_course_creation_persists_skill_attribution_and_reuses_handoff(
    app: object,
) -> None:
    attribution = SkillAttributionInput(
        host_platform="lobster",
        skill_id="ai-shifu-course-creator",
        skill_version="3.0.0",
        handoff_id="123e4567-e89b-12d3-a456-426614174020",
    )

    first = create_shifu_draft(
        app,
        "skill-course-owner",
        "Skill-created course",
        "",
        "",
        skill_attribution=attribution,
    )
    second = create_shifu_draft(
        app,
        "skill-course-owner",
        "A retry must not create another course",
        "",
        "",
        skill_attribution=attribution,
    )

    with app.app_context():
        saved = ShifuSkillAttribution.query.filter_by(
            handoff_id=attribution.handoff_id
        ).one()
        assert saved.shifu_bid == first.bid
        assert saved.user_bid == "skill-course-owner"
        assert saved.host_platform == "lobster"
        assert second.bid == first.bid
        assert (
            ShifuSkillAttribution.query.filter_by(
                handoff_id=attribution.handoff_id
            ).count()
            == 1
        )

        with pytest.raises(AppError):
            create_shifu_draft(
                app,
                "skill-course-owner",
                "Conflicting retry",
                "",
                "",
                skill_attribution=SkillAttributionInput(
                    host_platform="workbuddy",
                    skill_id=attribution.skill_id,
                    skill_version=attribution.skill_version,
                    handoff_id=attribution.handoff_id,
                ),
            )


def test_course_handoff_replay_rejects_a_former_owner(app: object) -> None:
    attribution = SkillAttributionInput(
        host_platform="direct",
        skill_id="ai-shifu-course-creator",
        skill_version="3.0.0",
        handoff_id="123e4567-e89b-12d3-a456-426614174021",
    )
    created = create_shifu_draft(
        app, "former-owner", "Transferred course", "", "", skill_attribution=attribution
    )
    with app.app_context(), unit_of_work():
        draft = DraftShifu.query.filter_by(shifu_bid=created.bid).one()
        draft.created_user_bid = "current-owner"

    with pytest.raises(AppError):
        create_shifu_draft(
            app,
            "former-owner",
            "Replay after transfer",
            "",
            "",
            skill_attribution=attribution,
        )

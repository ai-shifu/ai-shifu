"""Verify Skill journey event validation, deduplication and reporting."""

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.shifu.models import ShifuSkillAttribution
from flaskr.service.shifu.shifu_draft_funcs import create_shifu_draft
from flaskr.service.user.models import SkillJourneyEvent, UserSkillAttribution
from flaskr.service.user.skill_journey import (
    get_skill_attribution_report,
    record_skill_journey_event,
)
from sqlalchemy.dialects import mysql

USER_ID = "skill-journey-user"
EVENT_ID = "123e4567-e89b-12d3-a456-426614174010"


@pytest.fixture(autouse=True)
def clean_skill_journey_tables(app: object) -> None:
    """Keep session-scoped database state from coupling these tests."""
    with app.app_context(), unit_of_work():
        SkillJourneyEvent.query.delete()
        ShifuSkillAttribution.query.delete()
        UserSkillAttribution.query.delete()


def _event(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": EVENT_ID,
        "event_name": "course_creation_started",
        "host_platform": "workbuddy",
        "skill_id": "ai-shifu-course-creator",
        "skill_version": "1.0.0",
    }
    payload.update(overrides)
    return payload


def test_event_is_idempotent_for_the_same_authenticated_user(app: object) -> None:
    with app.app_context():
        first = record_skill_journey_event(user_id=USER_ID, payload=_event())
        second = record_skill_journey_event(user_id=USER_ID, payload=_event())

        assert first == {"accepted": True, "duplicate": False}
        assert second == {"accepted": True, "duplicate": True}
        assert SkillJourneyEvent.query.filter_by(event_bid=EVENT_ID).count() == 1


def test_mysql_duplicate_recovery_supports_a_locking_current_read(app: object) -> None:
    with app.app_context():
        statement = (
            SkillJourneyEvent.query.filter_by(event_bid=EVENT_ID)
            .with_for_update()
            .statement
        )

    compiled = str(statement.compile(dialect=mysql.dialect()))
    assert "FOR UPDATE" in compiled


def test_event_id_cannot_be_reused_for_different_evidence(app: object) -> None:
    with app.app_context():
        record_skill_journey_event(user_id=USER_ID, payload=_event())
        with pytest.raises(AppError):
            record_skill_journey_event(
                user_id=USER_ID,
                payload=_event(event_name="course_creation_completed"),
            )


def test_event_rejects_unexpected_content_fields(app: object) -> None:
    with app.app_context(), pytest.raises(AppError):
        record_skill_journey_event(
            user_id=USER_ID,
            payload=_event(prompt="must not enter analytics"),
        )


def test_course_completion_requires_a_course_identifier(app: object) -> None:
    with app.app_context(), pytest.raises(AppError):
        record_skill_journey_event(
            user_id=USER_ID,
            payload=_event(event_name="course_creation_completed"),
        )


def test_non_course_event_rejects_a_course_identifier(app: object) -> None:
    with app.app_context(), pytest.raises(AppError):
        record_skill_journey_event(
            user_id=USER_ID,
            payload=_event(event_name="authorization_completed", shifu_bid="course"),
        )


def test_course_event_requires_current_course_ownership(app: object) -> None:
    created = create_shifu_draft(app, USER_ID, "Journey course", "", "")
    with app.app_context():
        result = record_skill_journey_event(
            user_id=USER_ID,
            payload=_event(
                event_name="course_publish_completed", shifu_bid=created.bid
            ),
        )
        assert result == {"accepted": True, "duplicate": False}

        with pytest.raises(AppError):
            record_skill_journey_event(
                user_id="different-user",
                payload=_event(
                    event_id="123e4567-e89b-12d3-a456-426614174019",
                    event_name="course_publish_completed",
                    shifu_bid=created.bid,
                ),
            )


def test_report_groups_acquisitions_and_events_without_user_identifiers(
    app: object,
) -> None:
    with app.app_context(), unit_of_work():
        db.session.add(
            UserSkillAttribution(
                user_bid="report-user",
                host_platform="workbuddy",
                skill_id="ai-shifu-course-creator",
                skill_version="1.0.0",
                handoff_id="123e4567-e89b-12d3-a456-426614174011",
            )
        )
        db.session.add(
            ShifuSkillAttribution(
                shifu_bid="report-course",
                user_bid="report-user",
                host_platform="workbuddy",
                skill_id="ai-shifu-course-creator",
                skill_version="1.0.0",
                handoff_id="123e4567-e89b-12d3-a456-426614174012",
            )
        )

    with app.app_context():
        report = get_skill_attribution_report(
            start="2000-01-01T00:00:00Z", end="2100-01-01T00:00:00Z"
        )
        assert any(row["users"] >= 1 for row in report["acquisitions"])
        assert any(
            row["event_name"] == "course_creation_completed" and row["events"] >= 1
            for row in report["events"]
        )
        assert all("skill_version" in row for row in report["acquisitions"])
        assert all("skill_version" in row for row in report["events"])
        assert "user_bid" not in str(report)

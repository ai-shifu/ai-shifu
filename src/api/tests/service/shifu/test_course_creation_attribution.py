"""Verify immutable course creation attribution behavior."""

from uuid import uuid4

import pytest


def _valid_payload(handoff_id: str | None = None) -> dict[str, str]:
    return {
        "creation_source": "ai_assistant",
        "source_product": "lobster",
        "handoff_id": handoff_id or str(uuid4()),
    }


def test_attribution_payload_is_optional() -> None:
    from flaskr.service.common.source_attribution import parse_source_attribution

    assert parse_source_attribution(None, field_name="creation_attribution") is None


def test_lobster_attribution_payload_is_normalized() -> None:
    from flaskr.service.common.source_attribution import parse_source_attribution

    handoff_id = str(uuid4())

    result = parse_source_attribution(
        _valid_payload(handoff_id), field_name="creation_attribution"
    )

    assert result is not None
    assert result.creation_source == "ai_assistant"
    assert result.source_product == "lobster"
    assert result.handoff_id == handoff_id


@pytest.mark.parametrize(
    "payload",
    [
        "lobster",
        {},
        {
            "creation_source": "manual",
            "source_product": "lobster",
            "handoff_id": "52cefd54-930a-4c06-b62d-00de456cd56f",
        },
        {
            "creation_source": "ai_assistant",
            "source_product": "unknown",
            "handoff_id": "52cefd54-930a-4c06-b62d-00de456cd56f",
        },
        {
            "creation_source": "ai_assistant",
            "source_product": "lobster",
            "handoff_id": "not-a-uuid",
        },
        {
            **_valid_payload("52cefd54-930a-4c06-b62d-00de456cd56f"),
            "course_title": "sensitive free-form value",
        },
    ],
)
def test_invalid_attribution_payload_is_rejected(payload: object) -> None:
    from flaskr.service.common.models import AppError
    from flaskr.service.common.source_attribution import parse_source_attribution

    with pytest.raises(AppError):
        parse_source_attribution(payload, field_name="creation_attribution")


def test_create_persists_attribution_in_course_transaction(app: object) -> None:
    from flaskr import dao
    from flaskr.service.common.source_attribution import parse_source_attribution
    from flaskr.service.shifu.models import CourseCreationAttribution
    from flaskr.service.shifu.shifu_draft_funcs import create_shifu_draft

    teacher_bid = "teacher-lobster-attribution"
    handoff_id = str(uuid4())
    attribution = parse_source_attribution(
        _valid_payload(handoff_id), field_name="creation_attribution"
    )

    created = create_shifu_draft(
        app=app,
        user_id=teacher_bid,
        shifu_name="Attributed course",
        shifu_description="Created through Lobster",
        shifu_image="",
        creation_attribution=attribution,
    )

    with app.app_context():
        row = CourseCreationAttribution.query.filter_by(shifu_bid=created.bid).one()
        assert row.created_user_bid == teacher_bid
        assert row.creation_source == "ai_assistant"
        assert row.source_product == "lobster"
        assert row.handoff_id == handoff_id
        assert row.created_at is not None
        dao.db.session.delete(row)
        dao.db.session.commit()


def test_create_without_attribution_does_not_infer_origin(app: object) -> None:
    from flaskr.service.shifu.models import CourseCreationAttribution
    from flaskr.service.shifu.shifu_draft_funcs import create_shifu_draft

    created = create_shifu_draft(
        app=app,
        user_id="teacher-manual-course",
        shifu_name="Manual course",
        shifu_description="Created without attribution",
        shifu_image="",
    )

    with app.app_context():
        assert (
            CourseCreationAttribution.query.filter_by(
                shifu_bid=created.bid
            ).one_or_none()
            is None
        )

"""Persist and aggregate authenticated Skill journey milestones."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.skill_attribution import (
    ALLOWED_SKILL_EVENT_NAMES,
    parse_skill_identity,
)
from flaskr.service.shifu.models import DraftShifu, ShifuSkillAttribution
from flaskr.service.user.models import SkillJourneyEvent, UserSkillAttribution
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

_EVENTS_REQUIRING_COURSE = frozenset(
    {
        "course_creation_completed",
        "course_import_completed",
        "course_publish_started",
        "course_publish_completed",
    }
)
_EVENTS_WITHOUT_COURSE = ALLOWED_SKILL_EVENT_NAMES - _EVENTS_REQUIRING_COURSE


def _canonical_uuid(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise_param_error(field_name)
    try:
        canonical = str(UUID(value))
    except (AttributeError, TypeError, ValueError):
        raise_param_error(field_name)
    if canonical != value:
        raise_param_error(field_name)
    return canonical


def record_skill_journey_event(*, user_id: str, payload: object) -> dict[str, object]:
    """Store one idempotent event after validating ownership and dimensions."""
    if not isinstance(payload, dict):
        raise_param_error("event")
    allowed_fields = {
        "event_id",
        "event_name",
        "host_platform",
        "skill_id",
        "skill_version",
        "shifu_bid",
    }
    if not set(payload).issubset(allowed_fields):
        raise_param_error("event")
    event_bid = _canonical_uuid(payload.get("event_id"), field_name="event_id")
    event_name = payload.get("event_name")
    if event_name not in ALLOWED_SKILL_EVENT_NAMES:
        raise_param_error("event_name")
    identity = parse_skill_identity(payload, field_name="event")
    shifu_bid = str(payload.get("shifu_bid") or "").strip()
    if event_name in _EVENTS_REQUIRING_COURSE and not shifu_bid:
        raise_param_error("shifu_bid")
    if event_name in _EVENTS_WITHOUT_COURSE and shifu_bid:
        raise_param_error("shifu_bid")
    if shifu_bid:
        owned = DraftShifu.query.filter_by(
            shifu_bid=shifu_bid,
            created_user_bid=user_id,
            deleted=0,
        ).first()
        if owned is None:
            raise_param_error("shifu_bid")

    with unit_of_work():
        existing = SkillJourneyEvent.query.filter_by(event_bid=event_bid).first()
        if existing is not None:
            same_event = (
                existing.user_bid == user_id
                and existing.event_name == event_name
                and existing.host_platform == identity.host_platform
                and existing.skill_id == identity.skill_id
                and existing.skill_version == identity.skill_version
                and existing.shifu_bid == shifu_bid
            )
            if not same_event:
                raise_param_error("event_id")
            return {"accepted": True, "duplicate": True}
        try:
            with db.session.begin_nested():
                db.session.add(
                    SkillJourneyEvent(
                        event_bid=event_bid,
                        user_bid=user_id,
                        shifu_bid=shifu_bid,
                        host_platform=identity.host_platform,
                        skill_id=identity.skill_id,
                        skill_version=identity.skill_version,
                        event_name=event_name,
                    )
                )
                db.session.flush()
        except IntegrityError:
            existing = SkillJourneyEvent.query.filter_by(event_bid=event_bid).first()
            if existing is None:
                raise
            same_event = (
                existing.user_bid == user_id
                and existing.event_name == event_name
                and existing.host_platform == identity.host_platform
                and existing.skill_id == identity.skill_id
                and existing.skill_version == identity.skill_version
                and existing.shifu_bid == shifu_bid
            )
            if not same_event:
                raise_param_error("event_id")
            return {"accepted": True, "duplicate": True}
    return {"accepted": True, "duplicate": False}


def _parse_utc_boundary(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise_param_error(field_name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise_param_error(field_name)
    return parsed.replace(tzinfo=None)


def get_skill_attribution_report(*, start: object, end: object) -> dict[str, object]:
    """Return low-cardinality operator aggregates for one UTC interval."""
    start_at = _parse_utc_boundary(start, field_name="start")
    end_at = _parse_utc_boundary(end, field_name="end")
    if end_at <= start_at:
        raise_param_error("end")

    acquisition_rows = (
        db.session.query(
            UserSkillAttribution.host_platform,
            UserSkillAttribution.skill_id,
            UserSkillAttribution.skill_version,
            func.count(UserSkillAttribution.id),
        )
        .filter(
            UserSkillAttribution.created_at >= start_at,
            UserSkillAttribution.created_at < end_at,
        )
        .group_by(
            UserSkillAttribution.host_platform,
            UserSkillAttribution.skill_id,
            UserSkillAttribution.skill_version,
        )
        .all()
    )
    event_rows = (
        db.session.query(
            SkillJourneyEvent.host_platform,
            SkillJourneyEvent.skill_id,
            SkillJourneyEvent.skill_version,
            SkillJourneyEvent.event_name,
            func.count(SkillJourneyEvent.id),
            func.count(func.distinct(SkillJourneyEvent.user_bid)),
        )
        .filter(
            SkillJourneyEvent.created_at >= start_at,
            SkillJourneyEvent.created_at < end_at,
            SkillJourneyEvent.event_name != "course_creation_completed",
        )
        .group_by(
            SkillJourneyEvent.host_platform,
            SkillJourneyEvent.skill_id,
            SkillJourneyEvent.skill_version,
            SkillJourneyEvent.event_name,
        )
        .all()
    )
    creation_rows = (
        db.session.query(
            ShifuSkillAttribution.host_platform,
            ShifuSkillAttribution.skill_id,
            ShifuSkillAttribution.skill_version,
            func.count(ShifuSkillAttribution.id),
            func.count(func.distinct(ShifuSkillAttribution.user_bid)),
        )
        .filter(
            ShifuSkillAttribution.created_at >= start_at,
            ShifuSkillAttribution.created_at < end_at,
        )
        .group_by(
            ShifuSkillAttribution.host_platform,
            ShifuSkillAttribution.skill_id,
            ShifuSkillAttribution.skill_version,
        )
        .all()
    )
    return {
        "start": start,
        "end": end,
        "acquisitions": [
            {
                "host_platform": row[0],
                "skill_id": row[1],
                "skill_version": row[2],
                "users": row[3],
            }
            for row in acquisition_rows
        ],
        "events": [
            {
                "host_platform": row[0],
                "skill_id": row[1],
                "skill_version": row[2],
                "event_name": row[3],
                "events": row[4],
                "users": row[5],
            }
            for row in event_rows
        ]
        + [
            {
                "host_platform": row[0],
                "skill_id": row[1],
                "skill_version": row[2],
                "event_name": "course_creation_completed",
                "events": row[3],
                "users": row[4],
            }
            for row in creation_rows
        ],
    }

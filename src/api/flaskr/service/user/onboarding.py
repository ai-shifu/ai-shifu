from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flask import Flask
from sqlalchemy.exc import IntegrityError

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.config.funcs import get_config as get_dynamic_config
from flaskr.service.shifu.dtos import resolve_demo_course_for_language
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.models import UserOnboardingState


ONBOARDING_VERSION = "v1"
SCENE_ADMIN_HOME = "admin_home_onboarding"
SCENE_COURSE_EDITOR = "course_editor_onboarding"
SUPPORTED_SCENES = {
    SCENE_ADMIN_HOME,
    SCENE_COURSE_EDITOR,
}
SUPPORTED_TRIGGER_SOURCES = {
    "admin_entry",
    "editor_entry",
    "manual_create",
    "lobster_create",
    "skills_create",
}
STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"
ROLLOUT_CONFIG_KEY = "ADMIN_ONBOARDING_ENABLED_FROM"
EXISTING_CREATOR_ROLLOUT_CONFIG_KEY = "ADMIN_EXISTING_CREATOR_ONBOARDING_ENABLED_FROM"
USER_SEGMENT_NEW_CREATOR = "new_creator"
USER_SEGMENT_EXISTING_CREATOR_ROLLOUT = "existing_creator_rollout"
USER_SEGMENT_INELIGIBLE = "ineligible"


@dataclass(frozen=True)
class OnboardingSceneStatus:
    completed: bool
    completed_at: str | None
    eligible: bool
    status: str | None


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return f"{value.isoformat()}Z"
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_rollout_threshold(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    for candidate in (
        normalized,
        normalized.replace(" ", "T", 1),
    ):
        try:
            parsed = datetime.fromisoformat(candidate)
            return (
                parsed.astimezone(timezone.utc).replace(tzinfo=None)
                if parsed.tzinfo
                else parsed
            )
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _normalize_language(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "zh-CN"
    lowered = text.lower()
    if lowered.startswith("zh"):
        return "zh-CN"
    return "en-US"


def _load_user_entity(user_bid: str) -> UserEntity | None:
    normalized_user_bid = str(user_bid or "").strip()
    if not normalized_user_bid:
        return None
    return UserEntity.query.filter(
        UserEntity.user_bid == normalized_user_bid,
        UserEntity.deleted == 0,
    ).first()


def _resolve_user_segment(user: UserEntity | None) -> str:
    if user is None:
        return USER_SEGMENT_INELIGIBLE
    if not bool(getattr(user, "is_creator", 0)):
        return USER_SEGMENT_INELIGIBLE

    threshold = _parse_rollout_threshold(get_dynamic_config(ROLLOUT_CONFIG_KEY, ""))
    eligible_at = getattr(user, "created_at", None)
    if eligible_at is None:
        return USER_SEGMENT_INELIGIBLE
    if getattr(eligible_at, "tzinfo", None) is not None:
        eligible_at = eligible_at.astimezone(timezone.utc).replace(tzinfo=None)

    existing_rollout_threshold = _parse_rollout_threshold(
        get_dynamic_config(EXISTING_CREATOR_ROLLOUT_CONFIG_KEY, "")
    )
    now = datetime.utcnow()

    if threshold is None:
        if existing_rollout_threshold is not None and now >= existing_rollout_threshold:
            return USER_SEGMENT_EXISTING_CREATOR_ROLLOUT
        return USER_SEGMENT_INELIGIBLE

    if eligible_at >= threshold:
        return USER_SEGMENT_NEW_CREATOR

    if existing_rollout_threshold is None:
        return USER_SEGMENT_INELIGIBLE

    if now >= existing_rollout_threshold:
        return USER_SEGMENT_EXISTING_CREATOR_ROLLOUT

    return USER_SEGMENT_INELIGIBLE


def _build_scene_status(
    *,
    scene_key: str,
    states: dict[str, UserOnboardingState],
    user_segment: str,
) -> OnboardingSceneStatus:
    row = states.get(scene_key)
    is_eligible = user_segment in {
        USER_SEGMENT_NEW_CREATOR,
        USER_SEGMENT_EXISTING_CREATOR_ROLLOUT,
    }

    return OnboardingSceneStatus(
        completed=row is not None and row.status == STATUS_COMPLETED,
        completed_at=_serialize_datetime(
            getattr(row, "completed_at", None) if row else None
        ),
        eligible=is_eligible,
        status=getattr(row, "status", None) if row else None,
    )


def build_onboarding_status(
    app: Flask, user_bid: str, language: str | None
) -> dict[str, Any]:
    with app.app_context():
        user = _load_user_entity(user_bid)
        user_segment = _resolve_user_segment(user)
        normalized_language = _normalize_language(
            language or getattr(user, "language", "")
        )
        guide_course = resolve_demo_course_for_language(app, normalized_language)
        states = {
            state.scene_key: state
            for state in UserOnboardingState.query.filter(
                UserOnboardingState.user_bid == str(user_bid or "").strip(),
                UserOnboardingState.version == ONBOARDING_VERSION,
            ).all()
        }

        scenes = {
            SCENE_ADMIN_HOME: _build_scene_status(
                scene_key=SCENE_ADMIN_HOME,
                states=states,
                user_segment=user_segment,
            ).__dict__,
            SCENE_COURSE_EDITOR: _build_scene_status(
                scene_key=SCENE_COURSE_EDITOR,
                states=states,
                user_segment=user_segment,
            ).__dict__,
        }

        return {
            "eligible": any(scene["eligible"] for scene in scenes.values()),
            "user_segment": user_segment,
            "version": ONBOARDING_VERSION,
            "scenes": scenes,
            "guide_course": guide_course,
        }


def complete_onboarding_scene(
    app: Flask,
    user_bid: str,
    *,
    scene_key: str,
    version: str,
    trigger_source: str,
    status: str = STATUS_COMPLETED,
) -> dict[str, Any]:
    normalized_user_bid = str(user_bid or "").strip()
    normalized_scene_key = str(scene_key or "").strip()
    normalized_version = str(version or "").strip()
    normalized_trigger_source = str(trigger_source or "").strip()
    normalized_status = str(status or "").strip() or STATUS_COMPLETED

    if not normalized_user_bid:
        raise_error("server.user.userNotLogin")
    if normalized_scene_key not in SUPPORTED_SCENES:
        raise_param_error("scene_key")
    if normalized_version != ONBOARDING_VERSION:
        raise_param_error("version")
    if normalized_trigger_source not in SUPPORTED_TRIGGER_SOURCES:
        raise_param_error("trigger_source")
    if normalized_status not in {STATUS_COMPLETED, STATUS_SKIPPED}:
        raise_param_error("status")

    with app.app_context():
        user = _load_user_entity(normalized_user_bid)
        if _resolve_user_segment(user) == USER_SEGMENT_INELIGIBLE:
            raise_error("server.user.userNotPermission")

        existing = UserOnboardingState.query.filter(
            UserOnboardingState.user_bid == normalized_user_bid,
            UserOnboardingState.scene_key == normalized_scene_key,
            UserOnboardingState.version == normalized_version,
        ).first()
        now = datetime.utcnow()
        if existing is None:
            existing = UserOnboardingState(
                user_bid=normalized_user_bid,
                scene_key=normalized_scene_key,
                version=normalized_version,
                status=normalized_status,
                trigger_source=normalized_trigger_source,
                completed_at=now,
            )
            db.session.add(existing)
        else:
            existing.status = normalized_status
            existing.trigger_source = normalized_trigger_source
            # completed_at records the first time the scene was handled
            # (completed or skipped); keep it stable on later writes.
            if existing.completed_at is None:
                existing.completed_at = now

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing = UserOnboardingState.query.filter(
                UserOnboardingState.user_bid == normalized_user_bid,
                UserOnboardingState.scene_key == normalized_scene_key,
                UserOnboardingState.version == normalized_version,
            ).first()
            if existing is None:
                raise
            # A concurrent first-insert won the race; reapply this request's
            # outcome so the persisted row and the response stay consistent.
            existing.status = normalized_status
            existing.trigger_source = normalized_trigger_source
            if existing.completed_at is None:
                existing.completed_at = now
            db.session.commit()

        return {
            "scene_key": normalized_scene_key,
            "version": normalized_version,
            "completed": getattr(existing, "status", None) == STATUS_COMPLETED,
            "status": getattr(existing, "status", None),
            "completed_at": _serialize_datetime(
                getattr(existing, "completed_at", None)
            ),
        }

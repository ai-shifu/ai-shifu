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
}
STATUS_COMPLETED = "completed"
ROLLOUT_CONFIG_KEY = "ADMIN_ONBOARDING_ENABLED_FROM"


@dataclass(frozen=True)
class OnboardingSceneStatus:
    completed: bool
    completed_at: str | None


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


def _is_user_eligible(user: UserEntity | None) -> bool:
    if user is None:
        return False
    if not bool(getattr(user, "is_creator", 0)):
        return False
    if bool(getattr(user, "is_operator", 0)):
        return False

    threshold = _parse_rollout_threshold(get_dynamic_config(ROLLOUT_CONFIG_KEY, ""))
    eligible_at = getattr(user, "creator_activated_at", None) or getattr(
        user, "created_at", None
    )
    if threshold is None:
        return True
    if eligible_at is None:
        return False
    if getattr(eligible_at, "tzinfo", None) is not None:
        eligible_at = eligible_at.astimezone(timezone.utc).replace(tzinfo=None)
    return eligible_at >= threshold


def build_onboarding_status(
    app: Flask, user_bid: str, language: str | None
) -> dict[str, Any]:
    with app.app_context():
        user = _load_user_entity(user_bid)
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

        def build_scene_status(scene_key: str) -> OnboardingSceneStatus:
            row = states.get(scene_key)
            return OnboardingSceneStatus(
                completed=row is not None and row.status == STATUS_COMPLETED,
                completed_at=_serialize_datetime(
                    getattr(row, "completed_at", None) if row else None
                ),
            )

        return {
            "eligible": _is_user_eligible(user),
            "version": ONBOARDING_VERSION,
            "scenes": {
                SCENE_ADMIN_HOME: build_scene_status(SCENE_ADMIN_HOME).__dict__,
                SCENE_COURSE_EDITOR: build_scene_status(SCENE_COURSE_EDITOR).__dict__,
            },
            "guide_course": guide_course,
        }


def complete_onboarding_scene(
    app: Flask,
    user_bid: str,
    *,
    scene_key: str,
    version: str,
    trigger_source: str,
) -> dict[str, Any]:
    normalized_user_bid = str(user_bid or "").strip()
    normalized_scene_key = str(scene_key or "").strip()
    normalized_version = str(version or "").strip()
    normalized_trigger_source = str(trigger_source or "").strip()

    if not normalized_user_bid:
        raise_error("server.user.userNotLogin")
    if normalized_scene_key not in SUPPORTED_SCENES:
        raise_param_error("scene_key")
    if normalized_version != ONBOARDING_VERSION:
        raise_param_error("version")
    if normalized_trigger_source not in SUPPORTED_TRIGGER_SOURCES:
        raise_param_error("trigger_source")

    with app.app_context():
        user = _load_user_entity(normalized_user_bid)
        if not _is_user_eligible(user):
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
                status=STATUS_COMPLETED,
                trigger_source=normalized_trigger_source,
                completed_at=now,
            )
            db.session.add(existing)
        else:
            existing.status = STATUS_COMPLETED
            existing.trigger_source = normalized_trigger_source
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

        return {
            "scene_key": normalized_scene_key,
            "version": normalized_version,
            "completed": True,
            "completed_at": _serialize_datetime(
                getattr(existing, "completed_at", None)
            ),
        }

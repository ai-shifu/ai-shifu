"""Repository helpers bridging legacy user records and new entities."""

from __future__ import annotations

from typing import Optional, Tuple

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.dtos import UserInfo
from flaskr.service.user.auth.support import (
    ensure_user_entity,
    sync_user_entity_from_legacy,
)
from flaskr.service.user.consts import USER_STATE_UNREGISTERED
from flaskr.service.user.models import User, UserInfo as UserEntity
from flaskr.service.user.utils import get_user_language, get_user_openid


def fetch_legacy_user(user_id: str) -> Optional[User]:
    return User.query.filter_by(user_id=user_id).first()


def sync_user_entity_for_legacy(app: Flask, legacy_user: User) -> Optional[UserEntity]:
    if not legacy_user:
        return None
    entity, _ = ensure_user_entity(app, legacy_user)
    sync_user_entity_from_legacy(entity, legacy_user)
    db.session.flush()
    return entity


def load_user_with_entity(
    app: Flask, user_id: str
) -> Tuple[Optional[User], Optional[UserEntity]]:
    legacy_user = fetch_legacy_user(user_id)
    if not legacy_user:
        return None, None
    entity = sync_user_entity_for_legacy(app, legacy_user)
    return legacy_user, entity


def build_user_info_dto(legacy_user: User) -> UserInfo:
    if not legacy_user:
        raise ValueError("Cannot build UserInfo DTO without a legacy user record")

    return UserInfo(
        user_id=legacy_user.user_id,
        username=legacy_user.username,
        name=legacy_user.name,
        email=legacy_user.email,
        mobile=legacy_user.mobile,
        user_state=legacy_user.user_state or USER_STATE_UNREGISTERED,
        wx_openid=get_user_openid(legacy_user),
        language=get_user_language(legacy_user),
        user_avatar=legacy_user.user_avatar,
        is_admin=legacy_user.is_admin,
        is_creator=legacy_user.is_creator,
    )

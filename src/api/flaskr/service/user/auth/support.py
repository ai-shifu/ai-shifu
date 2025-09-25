"""Shared helpers for authentication providers."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Dict, Optional, Tuple

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.dtos import (
    USER_STATE_PAID as LEGACY_STATE_PAID,
    USER_STATE_REGISTERED as LEGACY_STATE_REGISTERED,
    USER_STATE_TRAIL as LEGACY_STATE_TRAIL,
    USER_STATE_UNREGISTERED as LEGACY_STATE_UNREGISTERED,
)
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import AuthCredential, User, UserInfo as UserEntity
from flaskr.service.user.utils import get_user_language
from flaskr.util.uuid import generate_id


STATE_MAPPING = {
    LEGACY_STATE_UNREGISTERED: USER_STATE_UNREGISTERED,
    LEGACY_STATE_REGISTERED: USER_STATE_REGISTERED,
    LEGACY_STATE_TRAIL: USER_STATE_TRAIL,
    LEGACY_STATE_PAID: USER_STATE_PAID,
}


def _normalize_birthday(value: Optional[datetime]) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return date(2000, 1, 1)
    return date(2000, 1, 1)


def _pick_nickname(user: User) -> str:
    for candidate in (user.username, user.name, user.mobile, user.email):
        if candidate:
            return candidate
    return user.user_id


def ensure_user_entity(app: Flask, legacy_user: User) -> Tuple[UserEntity, bool]:
    user_bid = legacy_user.user_id
    existing = UserEntity.query.filter_by(user_bid=user_bid).first()
    if existing:
        return existing, False

    entity = UserEntity(
        user_bid=user_bid,
        nickname=_pick_nickname(legacy_user),
        avatar=legacy_user.user_avatar or "",
        birthday=_normalize_birthday(getattr(legacy_user, "user_birth", None)),
        language=get_user_language(legacy_user),
        state=STATE_MAPPING.get(legacy_user.user_state, USER_STATE_REGISTERED),
        deleted=0,
    )
    if getattr(legacy_user, "created", None):
        entity.created_at = legacy_user.created
    if getattr(legacy_user, "updated", None):
        entity.updated_at = legacy_user.updated
    db.session.add(entity)
    db.session.flush()
    return entity, True


def upsert_credential(
    app: Flask,
    *,
    user_bid: str,
    provider_name: str,
    subject_id: str,
    subject_format: str,
    identifier: str,
    raw_metadata: Dict[str, Optional[str]],
    verified: bool,
) -> AuthCredential:
    credential = AuthCredential.query.filter_by(
        user_bid=user_bid,
        provider_name=provider_name,
        identifier=identifier,
    ).first()

    raw_profile = json.dumps(
        {"provider": provider_name, "metadata": raw_metadata},
        ensure_ascii=False,
    )
    state = CREDENTIAL_STATE_VERIFIED if verified else CREDENTIAL_STATE_UNVERIFIED

    if credential:
        credential.subject_id = subject_id
        credential.subject_format = subject_format
        credential.identifier = identifier
        credential.raw_profile = raw_profile
        credential.state = state
        credential.deleted = 0
    else:
        credential = AuthCredential(
            credential_bid=generate_id(app),
            user_bid=user_bid,
            provider_name=provider_name,
            subject_id=subject_id,
            subject_format=subject_format,
            identifier=identifier,
            raw_profile=raw_profile,
            state=state,
            deleted=0,
        )
        db.session.add(credential)

    db.session.flush()
    return credential

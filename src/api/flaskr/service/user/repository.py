"""Repository helpers bridging legacy user records and new entities."""

from __future__ import annotations

import json
from datetime import date, datetime
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.dtos import UserInfo
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import (
    AuthCredential,
    User,
    UserInfo as UserEntity,
)
from flaskr.service.user.utils import get_user_language, get_user_openid
from flaskr.util.uuid import generate_id


STATE_MAPPING = {
    USER_STATE_UNREGISTERED: USER_STATE_UNREGISTERED,
    USER_STATE_REGISTERED: USER_STATE_REGISTERED,
    USER_STATE_TRAIL: USER_STATE_TRAIL,
    USER_STATE_PAID: USER_STATE_PAID,
    1101: USER_STATE_UNREGISTERED,
    1102: USER_STATE_REGISTERED,
    1103: USER_STATE_TRAIL,
    1104: USER_STATE_PAID,
    "1101": USER_STATE_UNREGISTERED,
    "1102": USER_STATE_REGISTERED,
    "1103": USER_STATE_TRAIL,
    "1104": USER_STATE_PAID,
}

VALID_USER_STATES = {
    USER_STATE_UNREGISTERED,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_PAID,
}


def _normalize_user_state(raw_state) -> int:
    if raw_state is None:
        return USER_STATE_UNREGISTERED

    # direct mapping (covers 0-3 and string variations we added)
    if raw_state in STATE_MAPPING:
        return STATE_MAPPING[raw_state]

    # attempt numeric normalization
    try:
        numeric = int(float(str(raw_state).strip()))
        if numeric in STATE_MAPPING:
            return STATE_MAPPING[numeric]
        if numeric in VALID_USER_STATES:
            return numeric
    except (TypeError, ValueError):
        pass

    # final attempt: string key
    string_key = str(raw_state).strip()
    if string_key in STATE_MAPPING:
        return STATE_MAPPING[string_key]

    return USER_STATE_UNREGISTERED


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


def fetch_legacy_user(user_id: str) -> Optional[User]:
    return User.query.filter_by(user_id=user_id).first()


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
        state=_normalize_user_state(legacy_user.user_state),
        deleted=0,
    )
    if getattr(legacy_user, "created", None):
        entity.created_at = legacy_user.created
    if getattr(legacy_user, "updated", None):
        entity.updated_at = legacy_user.updated
    db.session.add(entity)
    db.session.flush()
    return entity, True


def sync_user_entity_from_legacy(entity: UserEntity, legacy_user: User) -> UserEntity:
    entity.nickname = _pick_nickname(legacy_user)
    entity.avatar = legacy_user.user_avatar or entity.avatar or ""
    entity.language = get_user_language(legacy_user)
    entity.state = _normalize_user_state(legacy_user.user_state)
    entity.deleted = 0
    if getattr(legacy_user, "user_birth", None):
        entity.birthday = _normalize_birthday(getattr(legacy_user, "user_birth", None))
    if getattr(legacy_user, "updated", None):
        entity.updated_at = legacy_user.updated
    return entity


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

    normalized_state = _normalize_user_state(legacy_user.user_state)

    return UserInfo(
        user_id=legacy_user.user_id,
        username=legacy_user.username,
        name=legacy_user.name,
        email=legacy_user.email,
        mobile=legacy_user.mobile,
        user_state=normalized_state,
        wx_openid=get_user_openid(legacy_user),
        language=get_user_language(legacy_user),
        user_avatar=legacy_user.user_avatar,
        is_admin=legacy_user.is_admin,
        is_creator=legacy_user.is_creator,
    )


@dataclass
class UserProfileSnapshot:
    user_bid: str
    legacy: Dict[str, Any] = field(default_factory=dict)
    credentials: List[Dict[str, Optional[str]]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_bid": self.user_bid,
            "legacy": self.legacy,
            "credentials": self.credentials,
        }


def _serialize_credentials(
    credentials: List[AuthCredential],
) -> List[Dict[str, Optional[str]]]:
    payload = []
    for credential in credentials:
        payload.append(
            {
                "credential_bid": credential.credential_bid,
                "provider": credential.provider_name,
                "identifier": credential.identifier,
                "subject_id": credential.subject_id,
                "subject_format": credential.subject_format,
                "state": credential.state,
                "metadata": deserialize_raw_profile(credential),
            }
        )
    return payload


def build_user_profile_snapshot(
    legacy_user: User,
    *,
    credentials: Optional[List[AuthCredential]] = None,
) -> UserProfileSnapshot:
    if not legacy_user:
        raise ValueError("Cannot build snapshot without a legacy user record")

    legacy_summary = {
        "user_id": legacy_user.user_id,
        "username": legacy_user.username,
        "name": legacy_user.name,
        "email": legacy_user.email,
        "mobile": legacy_user.mobile,
        "user_state": legacy_user.user_state or USER_STATE_UNREGISTERED,
        "language": get_user_language(legacy_user),
        "avatar": legacy_user.user_avatar,
        "is_admin": legacy_user.is_admin,
        "is_creator": legacy_user.is_creator,
    }

    return UserProfileSnapshot(
        user_bid=legacy_user.user_id,
        legacy=legacy_summary,
        credentials=_serialize_credentials(credentials or []),
    )


def serialize_raw_profile(
    provider_name: str, metadata: Dict[str, Optional[str]]
) -> str:
    return json.dumps(
        {"provider": provider_name, "metadata": metadata}, ensure_ascii=False
    )


def deserialize_raw_profile(record: AuthCredential) -> Dict[str, Optional[str]]:
    if not record.raw_profile:
        return {}
    try:
        payload = json.loads(record.raw_profile)
        return payload.get("metadata", {}) if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def upsert_credential(
    app: Flask,
    *,
    user_bid: str,
    provider_name: str,
    subject_id: str,
    subject_format: str,
    identifier: str,
    metadata: Dict[str, Optional[str]],
    verified: bool,
) -> AuthCredential:
    credential = AuthCredential.query.filter_by(
        user_bid=user_bid,
        provider_name=provider_name,
        identifier=identifier,
    ).first()

    raw_profile = serialize_raw_profile(provider_name, metadata)
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


def find_credential(
    *, provider_name: str, identifier: str, user_bid: Optional[str] = None
) -> Optional[AuthCredential]:
    query = AuthCredential.query.filter_by(
        provider_name=provider_name,
        identifier=identifier,
        deleted=0,
    )
    if user_bid:
        query = query.filter_by(user_bid=user_bid)
    return query.first()


def list_credentials(
    *, user_bid: str, provider_name: Optional[str] = None
) -> List[AuthCredential]:
    query = AuthCredential.query.filter_by(user_bid=user_bid, deleted=0)
    if provider_name:
        query = query.filter_by(provider_name=provider_name)
    return query.all()


def upsert_wechat_credentials(
    app: Flask,
    *,
    user_bid: str,
    open_id: Optional[str],
    union_id: Optional[str],
    open_identifier: Optional[str] = None,
    union_identifier: Optional[str] = None,
    metadata: Optional[Dict[str, Optional[str]]] = None,
    verified: bool = True,
) -> List[AuthCredential]:
    metadata = metadata or {}
    credentials: List[AuthCredential] = []

    if open_id:
        credentials.append(
            upsert_credential(
                app,
                user_bid=user_bid,
                provider_name="wechat",
                subject_id=open_id,
                subject_format="open_id",
                identifier=open_identifier or open_id,
                metadata={**metadata, "type": "open_id"},
                verified=verified,
            )
        )

    if union_id:
        credentials.append(
            upsert_credential(
                app,
                user_bid=user_bid,
                provider_name="wechat",
                subject_id=union_id,
                subject_format="unicon_id",
                identifier=union_identifier or union_id,
                metadata={**metadata, "type": "unicon_id"},
                verified=verified,
            )
        )

    return credentials


@contextmanager
def transactional_session():
    try:
        with db.session.begin_nested():
            yield
    except Exception:
        db.session.rollback()
        raise

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
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
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

STATE_TO_PUBLIC_STATE = {
    USER_STATE_UNREGISTERED: 0,
    USER_STATE_REGISTERED: 1,
    USER_STATE_TRAIL: 2,
    USER_STATE_PAID: 3,
}


@dataclass
class CredentialSummary:
    credential_bid: str
    provider: str
    identifier: str
    subject_id: str
    subject_format: str
    state: int
    metadata: Dict[str, Optional[str]] = field(default_factory=dict)

    @property
    def is_verified(self) -> bool:
        return self.state == CREDENTIAL_STATE_VERIFIED


@dataclass
class UserAggregate:
    user_bid: str
    identify: str
    nickname: str
    avatar: str
    birthday: Optional[date]
    language: str
    state: int
    deleted: bool
    created_at: datetime
    updated_at: datetime
    credentials: List[CredentialSummary] = field(default_factory=list)
    is_creator: bool = False

    def _preferred_identifier(
        self, provider: str, *, prefer_verified: bool = True
    ) -> Optional[CredentialSummary]:
        matches = [c for c in self.credentials if c.provider == provider]
        if not matches:
            return None
        if prefer_verified:
            for item in matches:
                if item.is_verified:
                    return item
        return matches[0]

    @property
    def email(self) -> str:
        credential = self._preferred_identifier("email")
        if credential:
            return credential.identifier
        if "@" in self.identify:
            return self.identify
        return ""

    @property
    def mobile(self) -> str:
        credential = self._preferred_identifier("phone")
        if credential:
            return credential.identifier
        if self.identify.isdigit():
            return self.identify
        return ""

    @property
    def wechat_open_id(self) -> str:
        for credential in self.credentials:
            if (
                credential.provider == "wechat"
                and credential.subject_format == "open_id"
            ):
                return credential.subject_id
        return ""

    @property
    def wechat_union_id(self) -> str:
        for credential in self.credentials:
            if (
                credential.provider == "wechat"
                and credential.subject_format == "unicon_id"
            ):
                return credential.subject_id
        return ""

    @property
    def username(self) -> str:
        if self.identify:
            return self.identify
        if self.email:
            return self.email
        if self.mobile:
            return self.mobile
        return self.user_bid

    @property
    def display_name(self) -> str:
        return self.nickname

    @property
    def user_language(self) -> str:
        return self.language or "en-US"

    @property
    def public_state(self) -> int:
        return STATE_TO_PUBLIC_STATE.get(self.state, 0)

    # Compatibility accessors for legacy call sites that previously relied on
    # ``user_info`` ORM objects. They allow downstream services to keep using
    # the familiar attribute names while the underlying data now comes from the
    # canonical ``user_users`` tables.

    @property
    def user_id(self) -> str:  # pragma: no cover - trivial alias
        return self.user_bid

    @property
    def name(self) -> str:  # pragma: no cover - trivial alias
        return self.display_name

    @property
    def user_state(self) -> int:  # pragma: no cover - trivial alias
        return self.state

    @property
    def user_avatar(self) -> str:  # pragma: no cover - trivial alias
        return self.avatar

    @property
    def user_open_id(self) -> str:  # pragma: no cover - trivial alias
        return self.wechat_open_id

    def to_user_info(self) -> UserInfo:
        return UserInfo(
            user_id=self.user_bid,
            username=self.username,
            name=self.display_name,
            email=self.email,
            mobile=self.mobile,
            user_state=self.public_state,
            wx_openid=self.wechat_open_id,
            language=self.user_language,
            user_avatar=self.avatar,
            is_creator=self.is_creator,
        )


def _normalize_identifier(provider: str, identifier: Optional[str]) -> str:
    if not identifier:
        return ""
    normalized = identifier.strip()
    if provider in {"email"}:
        return normalized.lower()
    return normalized


def _summarize_credentials(
    credentials: List[AuthCredential],
) -> List[CredentialSummary]:
    summaries: List[CredentialSummary] = []
    for credential in credentials:
        summaries.append(
            CredentialSummary(
                credential_bid=credential.credential_bid,
                provider=credential.provider_name,
                identifier=credential.identifier,
                subject_id=credential.subject_id,
                subject_format=credential.subject_format,
                state=credential.state,
                metadata=deserialize_raw_profile(credential),
            )
        )
    return summaries


def _build_user_aggregate(
    entity: UserEntity,
    *,
    credentials: Optional[List[AuthCredential]] = None,
) -> UserAggregate:
    summaries = _summarize_credentials(credentials or [])
    aggregate = UserAggregate(
        user_bid=entity.user_bid,
        identify=entity.user_identify or "",
        nickname=entity.nickname or "",
        avatar=entity.avatar or "",
        birthday=entity.birthday,
        language=entity.language or "",
        state=_normalize_user_state(entity.state),
        deleted=bool(entity.deleted),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        credentials=summaries,
        is_creator=bool(entity.is_creator),
    )
    return aggregate


def get_user_entity_by_bid(
    user_bid: str, *, include_deleted: bool = False
) -> Optional[UserEntity]:
    query = UserEntity.query.filter_by(user_bid=user_bid)
    if not include_deleted:
        query = query.filter_by(deleted=0)
    return query.first()


def _ensure_user_entity(user_bid: str) -> UserEntity:
    entity = get_user_entity_by_bid(user_bid, include_deleted=True)
    if entity:
        return entity
    identify = user_bid
    nickname: Optional[str] = None
    language: Optional[str] = None
    avatar: Optional[str] = None
    birthday: Optional[date] = None

    try:
        from flaskr.service.profile.models_v2 import UserProfile  # type: ignore
    except ImportError:  # pragma: no cover - defensive fallback
        UserProfile = None  # type: ignore[assignment]

    if UserProfile is not None:
        profile_rows = (
            UserProfile.query.filter(
                UserProfile.user_bid == user_bid,
                UserProfile.deleted == 0,
                UserProfile.profile_key.in_(
                    ["sys_user_nickname", "avatar", "language", "birth"]
                ),
            )
            .order_by(UserProfile.id.desc())
            .all()
        )
        for row in profile_rows:
            value = (row.profile_value or "").strip()
            if not value:
                continue
            if row.profile_key == "sys_user_nickname":
                nickname = value
            elif row.profile_key == "avatar" and not avatar:
                avatar = value
            elif row.profile_key == "language" and not language:
                language = value
            elif row.profile_key == "birth" and not birthday:
                try:
                    birthday = date.fromisoformat(value)
                except ValueError:
                    continue

    return create_user_entity(
        user_bid=user_bid,
        identify=identify,
        nickname=nickname,
        language=language,
        avatar=avatar,
        birthday=birthday,
    )


def load_user_aggregate(
    user_bid: str,
    *,
    include_deleted: bool = False,
    with_credentials: bool = True,
) -> Optional[UserAggregate]:
    entity = get_user_entity_by_bid(user_bid, include_deleted=include_deleted)
    if not entity:
        return None
    credentials: List[AuthCredential] = []
    if with_credentials:
        credentials = list_credentials(user_bid=user_bid)
    return _build_user_aggregate(entity, credentials=credentials)


def load_user_aggregate_by_identifier(
    identifier: str,
    *,
    providers: Optional[List[str]] = None,
) -> Optional[UserAggregate]:
    normalized = identifier.strip() if identifier else ""
    if not normalized:
        return None

    # Direct match on canonical identifier first
    entity = (
        UserEntity.query.filter_by(user_identify=normalized)
        .order_by(UserEntity.id.asc())
        .first()
    )
    if entity:
        return _build_user_aggregate(
            entity,
            credentials=list_credentials(user_bid=entity.user_bid),
        )

    provider_candidates = providers or []
    if not provider_candidates:
        if "@" in normalized:
            provider_candidates = ["email", "phone"]
        else:
            provider_candidates = ["phone", "email"]

    for provider in provider_candidates:
        credential = find_credential(
            provider_name=provider,
            identifier=_normalize_identifier(provider, normalized),
        )
        if credential:
            return load_user_aggregate(credential.user_bid)

    return None


def ensure_user_aggregate(
    app: Flask,
    *,
    user_bid: str,
    defaults: Optional[Dict[str, Any]] = None,
) -> Tuple[UserAggregate, bool]:
    """Ensure a user aggregate exists for ``user_bid``.

    Returns the aggregate together with a flag indicating whether it was created.
    ``defaults`` is forwarded to :func:`upsert_user_entity` when creation or updates
    are required.
    """

    defaults = defaults or {}
    entity, created = upsert_user_entity(user_bid=user_bid, defaults=defaults)
    aggregate = load_user_aggregate(entity.user_bid)
    if not aggregate:
        raise RuntimeError(f"Failed to load user aggregate for {user_bid}")
    return aggregate, created


def ensure_user_for_identifier(
    app: Flask,
    *,
    provider: str,
    identifier: str,
    defaults: Optional[Dict[str, Any]] = None,
) -> Tuple[UserAggregate, bool]:
    """Find or create a user aggregate bound to a provider identifier."""

    defaults = defaults or {}
    normalized = _normalize_identifier(provider, identifier)
    aggregate = load_user_aggregate_by_identifier(normalized, providers=[provider])
    if aggregate:
        entity = get_user_entity_by_bid(aggregate.user_bid, include_deleted=True)
        update_defaults = {
            key: value
            for key, value in defaults.items()
            if key
            in {"identify", "nickname", "avatar", "language", "state", "birthday"}
        }
        if update_defaults:
            update_user_entity_fields(entity, **update_defaults)
        db.session.flush()
        refreshed = load_user_aggregate(aggregate.user_bid)
        if not refreshed:
            raise RuntimeError(
                f"Failed to refresh user aggregate for provider {provider}"
            )
        return refreshed, False

    user_bid = defaults.get("user_bid") or generate_id(app)
    create_defaults = {
        "identify": normalized or defaults.get("identify", user_bid),
        "nickname": defaults.get("nickname", ""),
        "avatar": defaults.get("avatar"),
        "language": defaults.get("language"),
        "state": defaults.get("state"),
        "birthday": defaults.get("birthday"),
    }
    create_user_entity(user_bid=user_bid, **create_defaults)
    db.session.flush()
    aggregate = load_user_aggregate(user_bid)
    if not aggregate:
        raise RuntimeError(f"Failed to create user aggregate for provider {provider}")
    return aggregate, True


def mark_user_roles(
    user_bid: str,
    *,
    is_creator: Optional[bool] = None,
) -> None:
    """Persist creator role flag on the canonical entity."""

    if is_creator is None:
        return

    entity = _ensure_user_entity(user_bid)
    entity.is_creator = 1 if is_creator else 0
    db.session.flush()


def create_user_entity(
    *,
    user_bid: str,
    identify: str,
    nickname: Optional[str] = None,
    language: Optional[str] = None,
    avatar: Optional[str] = None,
    state: Optional[int] = None,
    birthday: Optional[date] = None,
) -> UserEntity:
    entity = UserEntity(
        user_bid=user_bid,
        user_identify=_normalize_identifier("", identify) or user_bid,
        nickname=nickname or "",
        avatar=avatar or "",
        birthday=birthday,
        language=language or "en-US",
        state=_normalize_user_state(state)
        if state is not None
        else USER_STATE_UNREGISTERED,
        deleted=0,
    )
    db.session.add(entity)
    db.session.flush()
    return entity


def update_user_entity_fields(
    entity: UserEntity,
    *,
    identify: Optional[str] = None,
    nickname: Optional[str] = None,
    avatar: Optional[str] = None,
    language: Optional[str] = None,
    state: Optional[int] = None,
    birthday: Optional[date] = None,
    deleted: Optional[bool] = None,
) -> UserEntity:
    if identify is not None:
        entity.user_identify = _normalize_identifier("", identify)
    if nickname is not None:
        entity.nickname = nickname
    if avatar is not None:
        entity.avatar = avatar
    if language is not None:
        entity.language = language
    if state is not None:
        entity.state = _normalize_user_state(state)
    if birthday is not None:
        entity.birthday = birthday
    if deleted is not None:
        entity.deleted = 1 if deleted else 0
    db.session.flush()
    return entity


def upsert_user_entity(
    *,
    user_bid: str,
    defaults: Optional[Dict[str, Any]] = None,
) -> Tuple[UserEntity, bool]:
    defaults = defaults or {}
    entity = get_user_entity_by_bid(user_bid, include_deleted=True)
    created = False
    if entity:
        update_user_entity_fields(entity, **defaults)
    else:
        created = True
        entity = create_user_entity(
            user_bid=user_bid,
            identify=defaults.get("identify", user_bid),
            nickname=defaults.get("nickname"),
            language=defaults.get("language"),
            avatar=defaults.get("avatar"),
            state=defaults.get("state"),
            birthday=defaults.get("birthday"),
        )
    return entity, created


def set_user_state(user_bid: str, state: int) -> None:
    """Persist the given user state in the canonical ``user_users`` table."""

    entity = _ensure_user_entity(user_bid)
    update_user_entity_fields(entity, state=state)


def build_user_info_from_aggregate(user: UserAggregate) -> UserInfo:
    return user.to_user_info()


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


def build_user_profile_snapshot_from_aggregate(
    aggregate: UserAggregate,
) -> UserProfileSnapshot:
    legacy_summary = {
        "user_id": aggregate.user_bid,
        "username": aggregate.username,
        "name": aggregate.display_name,
        "email": aggregate.email,
        "mobile": aggregate.mobile,
        "user_state": aggregate.state,
        "language": aggregate.user_language,
        "avatar": aggregate.avatar,
        "is_creator": aggregate.is_creator,
    }

    credentials_payload = [
        {
            "credential_bid": summary.credential_bid,
            "provider": summary.provider,
            "identifier": summary.identifier,
            "subject_id": summary.subject_id,
            "subject_format": summary.subject_format,
            "state": summary.state,
            "metadata": summary.metadata,
        }
        for summary in aggregate.credentials
    ]

    return UserProfileSnapshot(
        user_bid=aggregate.user_bid,
        legacy=legacy_summary,
        credentials=credentials_payload,
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

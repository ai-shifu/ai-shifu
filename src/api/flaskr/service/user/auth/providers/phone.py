"""Phone authentication provider implementation."""

from __future__ import annotations

import json
from datetime import date
from typing import Dict, Optional, Tuple

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.dtos import (
    USER_STATE_PAID as LEGACY_STATE_PAID,
    USER_STATE_REGISTERED as LEGACY_STATE_REGISTERED,
    USER_STATE_TRAIL as LEGACY_STATE_TRAIL,
    USER_STATE_UNREGISTERED as LEGACY_STATE_UNREGISTERED,
)
from flaskr.service.user.auth.base import (
    AuthProvider,
    AuthResult,
    ChallengeRequest,
    ChallengeResponse,
    VerificationRequest,
)
from flaskr.service.user.auth.factory import (
    has_provider,
    register_provider,
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
from flaskr.service.user.phone_flow import verify_phone_code
from flaskr.service.user.utils import get_user_language, send_sms_code
from flaskr.util.uuid import generate_id


STATE_MAPPING = {
    LEGACY_STATE_UNREGISTERED: USER_STATE_UNREGISTERED,
    LEGACY_STATE_REGISTERED: USER_STATE_REGISTERED,
    LEGACY_STATE_TRAIL: USER_STATE_TRAIL,
    LEGACY_STATE_PAID: USER_STATE_PAID,
}


def _normalize_birthday(value) -> date:
    if isinstance(value, date):
        return value
    return date(2000, 1, 1)


def _ensure_user_entity(app: Flask, legacy_user: User) -> Tuple[UserEntity, bool]:
    user_bid = legacy_user.user_id
    existing = UserEntity.query.filter_by(user_bid=user_bid).first()
    if existing:
        return existing, False

    entity = UserEntity(
        user_bid=user_bid,
        nickname=legacy_user.username
        or legacy_user.name
        or legacy_user.mobile
        or legacy_user.email
        or user_bid,
        avatar=legacy_user.user_avatar or "",
        birthday=_normalize_birthday(legacy_user.user_birth),
        language=get_user_language(legacy_user),
        state=STATE_MAPPING.get(legacy_user.user_state, USER_STATE_REGISTERED),
        deleted=0,
    )
    entity.created_at = legacy_user.created
    entity.updated_at = legacy_user.updated or legacy_user.created
    db.session.add(entity)
    db.session.flush()
    return entity, True


def _upsert_phone_credential(
    app: Flask,
    user_bid: str,
    identifier: str,
    raw_metadata: Dict[str, Optional[str]],
    verified: bool,
) -> AuthCredential:
    credential = AuthCredential.query.filter_by(
        user_bid=user_bid,
        provider_name="phone",
        identifier=identifier,
    ).first()

    raw_profile = json.dumps(
        {
            "provider": "phone",
            "metadata": raw_metadata,
        },
        ensure_ascii=False,
    )
    state = CREDENTIAL_STATE_VERIFIED if verified else CREDENTIAL_STATE_UNVERIFIED

    if credential:
        credential.subject_id = identifier
        credential.subject_format = "phone"
        credential.identifier = identifier
        credential.raw_profile = raw_profile
        credential.state = state
        credential.deleted = 0
    else:
        credential = AuthCredential(
            credential_bid=generate_id(app),
            user_bid=user_bid,
            provider_name="phone",
            subject_id=identifier,
            subject_format="phone",
            identifier=identifier,
            raw_profile=raw_profile,
            state=state,
            deleted=0,
        )
        db.session.add(credential)

    db.session.flush()
    return credential


class PhoneAuthProvider(AuthProvider):
    provider_name = "phone"
    supports_challenge = True

    def send_challenge(
        self, app: Flask, request: ChallengeRequest
    ) -> ChallengeResponse:
        response = send_sms_code(app, request.identifier, request.metadata.get("ip"))
        metadata = {"ip": request.metadata.get("ip")}
        return ChallengeResponse(
            identifier=request.identifier,
            expire_in=response.get("expire_in", 0),
            metadata=metadata,
        )

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        user_token, created_user, context = verify_phone_code(
            app,
            request.metadata.get("user_id"),
            request.identifier,
            request.code,
            course_id=request.metadata.get("course_id"),
            language=request.metadata.get("language"),
        )

        legacy_user = User.query.filter_by(user_id=user_token.userInfo.user_id).first()
        if not legacy_user:
            raise RuntimeError("Legacy user record missing after phone verification")

        user_entity, created_entity = _ensure_user_entity(app, legacy_user)
        credential = _upsert_phone_credential(
            app,
            user_entity.user_bid,
            request.identifier,
            {
                "course_id": context.get("course_id"),
                "language": context.get("language"),
                "ip": request.metadata.get("ip"),
            },
            verified=True,
        )

        db.session.flush()

        return AuthResult(
            user=user_token.userInfo,
            token=user_token,
            credential=credential,
            is_new_user=created_user or created_entity,
            metadata={"user_bid": user_entity.user_bid},
        )


if not has_provider(PhoneAuthProvider.provider_name):
    register_provider(PhoneAuthProvider)

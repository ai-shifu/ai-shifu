"""Email authentication provider implementation."""

from __future__ import annotations

from flask import Flask

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
from flaskr.service.user.repository import (
    ensure_user_entity,
    sync_user_entity_from_legacy,
    upsert_credential,
)
from flaskr.service.user.email_flow import verify_email_code
from flaskr.service.user.utils import send_email_code
from flaskr.service.user.models import User


class EmailAuthProvider(AuthProvider):
    provider_name = "email"
    supports_challenge = True

    def send_challenge(
        self, app: Flask, request: ChallengeRequest
    ) -> ChallengeResponse:
        response = send_email_code(
            app,
            request.identifier,
            ip=request.metadata.get("ip"),
            language=request.metadata.get("language"),
        )
        metadata = {
            "ip": request.metadata.get("ip"),
            "language": request.metadata.get("language"),
        }
        return ChallengeResponse(
            identifier=request.identifier,
            expire_in=response.get("expire_in", 0),
            metadata=metadata,
        )

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        user_token, created_user, context = verify_email_code(
            app,
            request.metadata.get("user_id"),
            request.identifier.lower(),
            request.code,
            course_id=request.metadata.get("course_id"),
            language=request.metadata.get("language"),
        )

        legacy_user = User.query.filter_by(user_id=user_token.userInfo.user_id).first()
        if not legacy_user:
            raise RuntimeError("Legacy user record missing after email verification")

        user_entity, created_entity = ensure_user_entity(app, legacy_user)
        sync_user_entity_from_legacy(user_entity, legacy_user)
        identifier = request.identifier.lower()
        credential = upsert_credential(
            app,
            user_bid=user_entity.user_bid,
            provider_name="email",
            subject_id=identifier,
            subject_format="email",
            identifier=identifier,
            metadata={
                "course_id": context.get("course_id"),
                "language": context.get("language"),
            },
            verified=True,
        )

        return AuthResult(
            user=user_token.userInfo,
            token=user_token,
            credential=credential,
            is_new_user=created_user or created_entity,
            metadata={"user_bid": user_entity.user_bid},
        )


if not has_provider(EmailAuthProvider.provider_name):
    register_provider(EmailAuthProvider)

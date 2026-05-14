"""Phone authentication provider implementation."""

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
from flaskr.service.common.phone_numbers import normalize_phone_identifier
from flaskr.service.user.repository import find_credential, load_user_aggregate
from flaskr.service.user.phone_flow import verify_phone_code
from flaskr.service.user.utils import send_sms_code


class PhoneAuthProvider(AuthProvider):
    provider_name = "phone"
    supports_challenge = True

    def send_challenge(
        self, app: Flask, request: ChallengeRequest
    ) -> ChallengeResponse:
        identifier = normalize_phone_identifier(request.identifier)
        response = send_sms_code(
            app,
            identifier,
            request.metadata.get("ip"),
            request.metadata.get("captcha_ticket"),
        )
        metadata = {"ip": request.metadata.get("ip")}
        return ChallengeResponse(
            identifier=identifier,
            expire_in=response.get("expire_in", 0),
            metadata=metadata,
        )

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        identifier = normalize_phone_identifier(request.identifier)
        user_token, created_user, context = verify_phone_code(
            app,
            request.metadata.get("user_id"),
            identifier,
            request.code,
            course_id=request.metadata.get("course_id"),
            language=request.metadata.get("language"),
            login_context=request.metadata.get("login_context"),
        )

        aggregate = load_user_aggregate(user_token.userInfo.user_id)
        if not aggregate:
            raise RuntimeError("User aggregate missing after phone verification")

        credential = find_credential(
            provider_name="phone",
            identifier=identifier,
            user_bid=aggregate.user_bid,
        )

        return AuthResult(
            user=user_token.userInfo,
            token=user_token,
            credential=credential,
            is_new_user=created_user,
            metadata={
                "user_bid": aggregate.user_bid,
                **{k: v for k, v in context.items() if v is not None},
            },
        )


if not has_provider(PhoneAuthProvider.provider_name):
    register_provider(PhoneAuthProvider)

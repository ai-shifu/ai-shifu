"""Authentication provider abstractions for user credential workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from flask import Flask
from pydantic import BaseModel, Field

from flaskr.service.common.dtos import UserInfo, UserToken
from flaskr.service.user.models import AuthCredential


class _BaseDTO(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class ChallengeRequest(_BaseDTO):
    """Request payload for providers that deliver a verification challenge."""

    identifier: str = Field(..., description="Unique identifier such as phone or email")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific auxiliary data"
    )


class ChallengeResponse(_BaseDTO):
    """Provider response after issuing a verification challenge."""

    identifier: str = Field(..., description="Identifier the challenge was sent to")
    expire_in: int = Field(..., description="Expiration time in seconds")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific auxiliary data"
    )


class VerificationRequest(_BaseDTO):
    """Request payload for code-based verification providers."""

    identifier: str = Field(..., description="Identifier being verified")
    code: str = Field(..., description="Verification code or token")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific auxiliary data"
    )


class OAuthCallbackRequest(_BaseDTO):
    """Normalized payload for OAuth callback handlers."""

    state: Optional[str] = Field(
        None, description="Opaque state value returned by OAuth"
    )
    code: Optional[str] = Field(None, description="Authorization code or token")
    raw_request_args: Dict[str, Any] = Field(
        default_factory=dict, description="Complete callback request arguments"
    )


class AuthResult(_BaseDTO):
    """Standardized output of a provider authentication attempt."""

    user: UserInfo = Field(..., description="Resolved user information DTO")
    token: UserToken = Field(..., description="Issued login token")
    credential: Optional[AuthCredential] = Field(
        None, description="Persisted credential record when available"
    )
    is_new_user: bool = Field(
        False, description="Indicates whether the auth flow created a new user"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific auxiliary data"
    )


class AuthProvider(ABC):
    """Base contract for a user authentication provider."""

    #: Provider identifier used when persisting credentials
    provider_name: str

    #: Whether the provider can issue a challenge (e.g., SMS, email)
    supports_challenge: bool = False

    #: Whether the provider participates in an OAuth redirect flow
    supports_oauth: bool = False

    def send_challenge(
        self, app: Flask, request: ChallengeRequest
    ) -> ChallengeResponse:
        """Dispatch a verification challenge to the user."""

        raise NotImplementedError(
            f"Provider '{self.provider_name}' does not issue challenges"
        )

    @abstractmethod
    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        """Validate a user based on the incoming verification request."""

    def begin_oauth(self, app: Flask, metadata: Dict[str, Any]) -> Any:
        """Initiate an OAuth flow (optional)."""

        raise NotImplementedError(
            f"Provider '{self.provider_name}' does not support OAuth begin"
        )

    def handle_oauth_callback(
        self, app: Flask, request: OAuthCallbackRequest
    ) -> AuthResult:
        """Complete an OAuth flow and produce an authentication result."""

        raise NotImplementedError(
            f"Provider '{self.provider_name}' does not support OAuth callbacks"
        )

"""Authentication provider abstractions for user credential workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from flaskr.service.common.dtos import UserInfo, UserToken
from flaskr.service.user.models import AuthCredential
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from flask import Flask


class _BaseDTO(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class ChallengeRequest(_BaseDTO):
    """Request payload for providers that deliver a verification challenge."""

    identifier: str = Field(..., description="Unique identifier such as phone or email")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific auxiliary data"
    )


class ChallengeResponse(_BaseDTO):
    """Provider response after issuing a verification challenge."""

    identifier: str = Field(..., description="Identifier the challenge was sent to")
    expire_in: int = Field(..., description="Expiration time in seconds")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific auxiliary data"
    )


class VerificationRequest(_BaseDTO):
    """Request payload for code-based verification providers."""

    identifier: str = Field(..., description="Identifier being verified")
    code: str = Field(..., description="Verification code or token")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific auxiliary data"
    )


class OAuthCallbackRequest(_BaseDTO):
    """Normalized payload for OAuth callback handlers."""

    state: str | None = Field(None, description="Opaque state value returned by OAuth")
    code: str | None = Field(None, description="Authorization code or token")
    raw_request_args: dict[str, Any] = Field(
        default_factory=dict, description="Complete callback request arguments"
    )
    current_user_id: str | None = Field(
        None,
        description="User ID resolved from temporary token, if any",
    )


class AuthResult(_BaseDTO):
    """Standardized output of a provider authentication attempt."""

    user: UserInfo = Field(..., description="Resolved user information DTO")
    token: UserToken = Field(..., description="Issued login token")
    credential: AuthCredential | None = Field(
        None, description="Persisted credential record when available"
    )
    is_new_user: bool = Field(
        default=False, description="Indicates whether the auth flow created a new user"
    )
    metadata: dict[str, Any] = Field(
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
        message = f"Provider '{self.provider_name}' does not issue challenges"
        raise NotImplementedError(message)

    @abstractmethod
    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        """Validate a user based on the incoming verification request."""

    def begin_oauth(self, app: Flask, metadata: dict[str, object]) -> object:
        """Initiate an OAuth flow (optional)."""
        message = f"Provider '{self.provider_name}' does not support OAuth begin"
        raise NotImplementedError(message)

    def handle_oauth_callback(
        self, app: Flask, request: OAuthCallbackRequest
    ) -> AuthResult:
        """Complete an OAuth flow and produce an authentication result."""
        message = f"Provider '{self.provider_name}' does not support OAuth callbacks"
        raise NotImplementedError(message)

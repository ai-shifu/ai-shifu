"""Authentication provider package exports."""

from .base import (
    AuthProvider,
    AuthResult,
    ChallengeRequest,
    ChallengeResponse,
    OAuthCallbackRequest,
    VerificationRequest,
)
from .factory import (
    clear_providers,
    get_provider,
    has_provider,
    register_provider,
    registered_providers,
)

# Ensure built-in providers are registered on import.
from .providers import phone as _phone_provider  # noqa: F401
from .providers import email as _email_provider  # noqa: F401
from .providers import google as _google_provider  # noqa: F401

__all__ = [
    "AuthProvider",
    "AuthResult",
    "ChallengeRequest",
    "ChallengeResponse",
    "OAuthCallbackRequest",
    "VerificationRequest",
    "clear_providers",
    "get_provider",
    "has_provider",
    "register_provider",
    "registered_providers",
]

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
from .providers import phone as _phone_provider
from .providers import email as _email_provider
from .providers import google as _google_provider

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
    "_phone_provider",
    "_email_provider",
    "_google_provider",
]

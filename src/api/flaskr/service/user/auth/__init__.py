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
    "register_builtin_providers",
]


def register_builtin_providers() -> None:
    """Ensure built-in providers are loaded and registered."""
    from importlib import import_module

    for module_name in ("phone", "email", "google", "password"):
        import_module(f"{__name__}.providers.{module_name}")

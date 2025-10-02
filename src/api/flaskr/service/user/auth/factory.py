"""Provider factory registration utilities."""

from __future__ import annotations

from typing import Dict, Iterable, Type

from .base import AuthProvider


class ProviderAlreadyRegisteredError(RuntimeError):
    """Raised when attempting to register a provider twice."""


class ProviderNotFoundError(RuntimeError):
    """Raised when the requested provider has not been registered."""


_REGISTRY: Dict[str, Type[AuthProvider]] = {}


def register_provider(provider_cls: Type[AuthProvider]) -> None:
    """Register a provider class with the global registry."""

    provider_name = getattr(provider_cls, "provider_name", None)
    if not provider_name:
        raise ValueError("Auth providers must define a non-empty provider_name")

    normalized = provider_name.lower()
    if normalized in _REGISTRY:
        raise ProviderAlreadyRegisteredError(
            f"Provider '{provider_name}' already registered"
        )

    _REGISTRY[normalized] = provider_cls


def get_provider(provider_name: str) -> AuthProvider:
    """Instantiate a provider by name."""

    normalized = provider_name.lower()
    provider_cls = _REGISTRY.get(normalized)
    if provider_cls is None:
        raise ProviderNotFoundError(f"Provider '{provider_name}' is not registered")
    return provider_cls()


def has_provider(provider_name: str) -> bool:
    """Return ``True`` when a provider has been registered."""

    return provider_name.lower() in _REGISTRY


def registered_providers() -> Iterable[str]:
    """Iterate over registered provider names."""

    return tuple(_REGISTRY.keys())


def clear_providers() -> None:
    """Utility for tests to reset the provider registry."""

    _REGISTRY.clear()

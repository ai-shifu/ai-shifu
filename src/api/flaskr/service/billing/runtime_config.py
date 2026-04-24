"""Billing-driven runtime config extensions for v1.1."""

from __future__ import annotations

from flask import Flask

from .dtos import (
    RuntimeBillingBrandingDTO,
    RuntimeBillingContextDTO,
    RuntimeBillingEntitlementsDTO,
)
from .domains import resolve_runtime_domain_result
from .entitlements import (
    resolve_creator_entitlement_state,
    serialize_creator_entitlements,
)


def build_runtime_billing_context(
    app: Flask,
    *,
    creator_bid: str,
    request_host: str = "",
) -> RuntimeBillingContextDTO:
    """Build entitlement, branding, and domain payloads for runtime-config."""

    normalized_creator_bid = str(creator_bid or "").strip()
    entitlement_state = resolve_creator_entitlement_state(normalized_creator_bid)
    entitlements = RuntimeBillingEntitlementsDTO(
        **serialize_creator_entitlements(entitlement_state).__json__()
    )
    branding = _build_branding_payload(entitlement_state)
    domain = resolve_runtime_domain_result(
        app,
        request_host,
        creator_bid=normalized_creator_bid,
    )
    return RuntimeBillingContextDTO(
        entitlements=entitlements,
        branding=branding,
        domain=domain,
    )


def _build_branding_payload(
    entitlement_state,
) -> RuntimeBillingBrandingDTO:
    normalized_feature_payload = entitlement_state.feature_payload.to_metadata_json()
    branding_payload = normalized_feature_payload.get("branding")
    normalized_branding_payload = (
        branding_payload if isinstance(branding_payload, dict) else {}
    )

    def pick(*keys: str) -> str | None:
        for key in keys:
            value = normalized_branding_payload.get(key)
            if value is None:
                value = normalized_feature_payload.get(key)
            normalized_value = str(value or "").strip()
            if normalized_value:
                return normalized_value
        return None

    if not bool(entitlement_state.branding_enabled):
        return RuntimeBillingBrandingDTO(
            logo_wide_url=None,
            logo_square_url=None,
            favicon_url=None,
            home_url=None,
        )

    return RuntimeBillingBrandingDTO(
        logo_wide_url=pick("logo_wide_url", "logoWideUrl"),
        logo_square_url=pick("logo_square_url", "logoSquareUrl"),
        favicon_url=pick("favicon_url", "faviconUrl"),
        home_url=pick("home_url", "homeUrl"),
    )

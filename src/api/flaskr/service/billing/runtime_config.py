"""Billing-driven runtime config extensions for v1.1."""

from __future__ import annotations

from flask import Flask

from .consts import (
    BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC,
    BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD,
    BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS,
    BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE,
)
from .dtos import (
    RuntimeBillingBrandingDTO,
    RuntimeBillingContextDTO,
    RuntimeBillingDomainDTO,
    RuntimeBillingEntitlementsDTO,
)
from .domains import normalize_domain_host, resolve_runtime_domain_result
from .entitlements import (
    resolve_creator_entitlement_state,
    serialize_creator_entitlements,
)
from .primitives import normalize_bid


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


def build_default_runtime_billing_context(
    *,
    creator_bid: str = "",
    request_host: str = "",
) -> RuntimeBillingContextDTO:
    """Build an empty billing payload without touching billing tables."""

    normalized_creator_bid = normalize_bid(creator_bid) or None
    normalized_host = normalize_domain_host(request_host, strict=False) or None
    return RuntimeBillingContextDTO(
        entitlements=RuntimeBillingEntitlementsDTO(
            branding_enabled=False,
            custom_domain_enabled=False,
            priority_class=BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS.get(
                BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD,
                "standard",
            ),
            analytics_tier=BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS.get(
                BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC,
                "basic",
            ),
            support_tier=BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS.get(
                BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE,
                "self_serve",
            ),
        ),
        branding=RuntimeBillingBrandingDTO(
            logo_wide_url=None,
            logo_square_url=None,
            favicon_url=None,
            home_url=None,
        ),
        domain=RuntimeBillingDomainDTO(
            request_host=normalized_host,
            matched=False,
            is_custom_domain=False,
            creator_bid=normalized_creator_bid,
            domain_binding_bid=None,
            host=None,
            binding_status=None,
        ),
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

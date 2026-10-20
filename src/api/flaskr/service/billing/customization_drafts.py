"""Admin creator customization draft identity and normalization helpers.

Shared customization constants and normalizers are read through
``_customization_facade()`` so patches applied to ``customization`` keep
reaching this code.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from flaskr.service.common.contact_identifiers import (
    CONTACT_TYPE_EMAIL,
    normalize_contact_identifier,
    resolve_contact_type,
)
from flaskr.service.common.models import raise_param_error

from .primitives import normalize_bid

if TYPE_CHECKING:
    from types import ModuleType


def _customization_facade() -> ModuleType:
    """Resolve collaborators through ``customization`` so patches stay live."""
    from . import customization

    return customization


def _admin_draft_contact_digest(creator_mobile: str) -> str:
    """Digest the contact identifier an unsaved draft is keyed by.

    Emails are lowercased first so a draft stored as ``A@x.com`` is still found
    when the dialog is reopened with ``a@x.com``. Phone numbers keep their raw
    trimmed form so drafts written before email support remain reachable.
    """
    normalized_creator_contact = str(creator_mobile or "").strip()
    if not normalized_creator_contact:
        raise_param_error("creator_mobile")
    contact_type = resolve_contact_type(normalized_creator_contact)
    if contact_type == CONTACT_TYPE_EMAIL:
        normalized_creator_contact = normalize_contact_identifier(
            normalized_creator_contact, contact_type
        )
    return hashlib.sha256(normalized_creator_contact.encode("utf-8")).hexdigest()


def _admin_draft_owner_bid(*, creator_bid: str = "", creator_mobile: str = "") -> str:
    normalized_creator_bid = normalize_bid(creator_bid)
    if normalized_creator_bid:
        return f"billing-admin-draft:creator:{normalized_creator_bid}"

    contact_digest = _admin_draft_contact_digest(creator_mobile)
    return f"billing-admin-draft:mobile:{contact_digest}"


def _admin_draft_storage_identity(
    *, creator_bid: str = "", creator_mobile: str = ""
) -> tuple[str, str]:
    customization = _customization_facade()
    normalized_creator_bid = normalize_bid(creator_bid)
    if normalized_creator_bid:
        return normalized_creator_bid, f"{customization.ADMIN_DRAFT_KEY}.CREATOR"

    contact_digest = _admin_draft_contact_digest(creator_mobile)
    return contact_digest[:36], f"{customization.ADMIN_DRAFT_KEY}.MOBILE"


def _empty_admin_creator_customization_draft(
    *, creator_mobile: str = ""
) -> dict[str, object]:
    customization = _customization_facade()
    return {
        "creator_mobile": str(creator_mobile or "").strip(),
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "custom_wechat_enabled": False,
        "custom_payment_enabled": False,
        "config_status": "pending",
        "note": "",
        "branding": {
            "logo_wide_url": "",
            "logo_square_url": "",
            "favicon_url": "",
            "home_url": "",
        },
        "domain": {
            "host": "",
        },
        "integrations": {
            provider: {"public_config": {}, "secret_config": {}}
            for provider in customization.INTEGRATION_PROVIDERS
        },
    }


def _normalize_admin_creator_customization_draft(
    payload: dict[str, object],
    *,
    creator_mobile: str = "",
) -> dict[str, object]:
    customization = _customization_facade()
    base = _empty_admin_creator_customization_draft(creator_mobile=creator_mobile)
    result = dict(base)
    result["creator_mobile"] = str(
        payload.get("creator_mobile") or creator_mobile or ""
    ).strip()
    for key in (
        "branding_enabled",
        "custom_domain_enabled",
        "custom_wechat_enabled",
        "custom_payment_enabled",
    ):
        result[key] = customization._to_bool(payload.get(key))

    config_status = str(payload.get("config_status") or "pending").strip().lower()
    result["config_status"] = (
        config_status
        if config_status in {"pending", "in_progress", "completed", "exception"}
        else "pending"
    )
    result["note"] = str(payload.get("note") or "")[:500]

    branding_payload = payload.get("branding")
    if isinstance(branding_payload, dict):
        result["branding"] = {
            "logo_wide_url": customization._normalize_logo_url(
                branding_payload.get("logo_wide_url"), "logo_wide_url"
            )
            if branding_payload.get("logo_wide_url")
            else "",
            "logo_square_url": customization._normalize_logo_url(
                branding_payload.get("logo_square_url"), "logo_square_url"
            )
            if branding_payload.get("logo_square_url")
            else "",
            "favicon_url": customization._normalize_logo_url(
                branding_payload.get("favicon_url"), "favicon_url"
            )
            if branding_payload.get("favicon_url")
            else "",
            "home_url": customization._normalize_home_url_lenient(
                branding_payload.get("home_url")
            ),
        }

    domain_payload = payload.get("domain")
    if isinstance(domain_payload, dict):
        result["domain"] = {"host": str(domain_payload.get("host") or "").strip()}

    integrations_payload = payload.get("integrations")
    if isinstance(integrations_payload, dict):
        normalized_integrations = {}
        for provider in customization.INTEGRATION_PROVIDERS:
            provider_payload = integrations_payload.get(provider)
            if isinstance(provider_payload, dict):
                normalized_integrations[provider] = {
                    "public_config": customization._normalize_config(
                        provider, provider_payload.get("public_config"), secret=False
                    ),
                    "secret_config": customization._normalize_config(
                        provider, provider_payload.get("secret_config"), secret=True
                    ),
                }
            else:
                normalized_integrations[provider] = {
                    "public_config": {},
                    "secret_config": {},
                }
        result["integrations"] = normalized_integrations

    return result

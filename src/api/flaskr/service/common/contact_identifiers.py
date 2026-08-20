"""Shared helpers for phone/email contact identifiers.

Deployments differ in how a person is identified: the China site signs users in
with an SMS phone number, while the overseas site uses Google/email. There is no
region flag in the codebase; ``LOGIN_METHODS_ENABLED`` is the established signal
for that difference, so admin flows that take "the account to act on" resolve
the accepted contact type from it instead of hardcoding phone numbers.
"""

from __future__ import annotations

import re

from flaskr.common.config import get_config
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.phone_numbers import (
    is_valid_sms_mobile,
    normalize_phone_identifier,
)

CONTACT_TYPE_PHONE = "phone"
CONTACT_TYPE_EMAIL = "email"

CONTACT_IDENTIFIER_MAX_LENGTH = 320

EMAIL_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)

# Providers to search when looking an account up by a normalized identifier.
CONTACT_LOOKUP_PROVIDERS = {
    CONTACT_TYPE_PHONE: ["phone"],
    CONTACT_TYPE_EMAIL: ["email", "google"],
}


def resolve_enabled_login_methods() -> set[str]:
    """Resolve the login methods this deployment accepts.

    ``google`` implies ``email`` because a Google account is addressed by its
    email address everywhere in the admin console.
    """
    raw = get_config("LOGIN_METHODS_ENABLED", "phone")
    items = raw if isinstance(raw, (list, tuple, set)) else str(raw).split(",")
    methods = {str(item).strip().lower() for item in items if str(item).strip()}
    if "google" in methods:
        methods.add(CONTACT_TYPE_EMAIL)
    return methods


def resolve_enabled_contact_types() -> set[str]:
    """Return the contact types usable on this deployment, never empty."""
    methods = resolve_enabled_login_methods()
    contact_types = {
        contact_type
        for contact_type in (CONTACT_TYPE_PHONE, CONTACT_TYPE_EMAIL)
        if contact_type in methods
    }
    return contact_types or {CONTACT_TYPE_PHONE}


def resolve_contact_type(identifier: str, *, allowed: set[str] | None = None) -> str:
    """Infer whether an identifier should be treated as a phone or an email.

    When the deployment accepts a single contact type the answer is that type,
    so a malformed value still fails with the error message operators expect.
    When both are accepted the ``@`` character decides.
    """
    allowed_types = allowed if allowed is not None else resolve_enabled_contact_types()
    if CONTACT_TYPE_EMAIL not in allowed_types:
        return CONTACT_TYPE_PHONE
    if CONTACT_TYPE_PHONE not in allowed_types:
        return CONTACT_TYPE_EMAIL
    return CONTACT_TYPE_EMAIL if "@" in str(identifier or "") else CONTACT_TYPE_PHONE


def normalize_contact_identifier(identifier: str, contact_type: str) -> str:
    """Normalize an identifier without validating it.

    Emails are lowercased so callers that key storage by the raw value stay
    consistent; phone numbers only lose an optional ``+86`` prefix.
    """
    if contact_type == CONTACT_TYPE_EMAIL:
        return str(identifier or "").strip().lower()
    return normalize_phone_identifier(identifier)


def validate_contact_identifier(
    identifier: str,
    contact_type: str,
    *,
    empty_error: str = "contact",
) -> str:
    """Normalize and validate an identifier, raising a param error when invalid.

    ``empty_error`` lets callers keep their existing error key for blank input
    while format errors stay type specific (``mobile`` / ``email``).
    """
    normalized = normalize_contact_identifier(identifier, contact_type)
    if not normalized:
        raise_param_error(empty_error)
    if len(normalized) > CONTACT_IDENTIFIER_MAX_LENGTH:
        raise_param_error(contact_type)
    if contact_type == CONTACT_TYPE_EMAIL:
        if not EMAIL_IDENTIFIER_PATTERN.fullmatch(normalized):
            raise_param_error("email")
        return normalized
    if not is_valid_sms_mobile(normalized):
        raise_param_error("mobile")
    return normalized


def resolve_contact_lookup_providers(contact_type: str) -> list[str]:
    """Return the auth providers to search for a given contact type."""
    return list(
        CONTACT_LOOKUP_PROVIDERS.get(
            contact_type, CONTACT_LOOKUP_PROVIDERS[CONTACT_TYPE_PHONE]
        )
    )

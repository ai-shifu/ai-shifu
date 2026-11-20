"""Username identifiers for password-only accounts.

A username is stored as an ``AuthCredential`` with ``provider_name="username"``
so it resolves through the same identifier lookup as phone numbers and email
addresses. The format is deliberately disjoint from both: a username starts
with a letter (phone numbers never do) and cannot contain ``@`` (every email
address does), so one login field can accept all three without ambiguity.
"""

from __future__ import annotations

import re

from flaskr.service.common.models import raise_error
from flaskr.service.common.phone_numbers import normalize_phone_identifier

USERNAME_PROVIDER = "username"

#: Identifier credentials that a password login may resolve.
PASSWORD_LOGIN_IDENTIFIER_PROVIDERS = ["phone", "email", USERNAME_PROVIDER]

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = re.compile(
    rf"^[a-z][a-z0-9_.-]{{{USERNAME_MIN_LENGTH - 1},{USERNAME_MAX_LENGTH - 1}}}$"
)


def normalize_username(raw: str | None) -> str:
    """Return the canonical (trimmed, lower-case) form of a username."""
    return str(raw or "").strip().lower()


def is_username(raw: str | None) -> bool:
    """Return whether ``raw`` normalizes to a well-formed username."""
    return bool(USERNAME_PATTERN.fullmatch(normalize_username(raw)))


def validate_username(raw: str | None) -> str:
    """Return the canonical username or raise ``server.user.usernameInvalid``."""
    normalized = normalize_username(raw)
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise_error("server.user.usernameInvalid")
    return normalized


def normalize_login_identifier(raw: str | None) -> str:
    """Normalize a password-login identifier: email, username, or phone."""
    stripped = str(raw or "").strip()
    if "@" in stripped or is_username(stripped):
        return stripped.lower()
    return normalize_phone_identifier(stripped)

"""Password utility functions: hashing, verification, strength validation."""

from __future__ import annotations

import hashlib
import re

import bcrypt
from flaskr.service.common.models import raise_error


def password_credential_version(password_hash: str) -> str:
    """Bind successful password verification to the exact credential version."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()


def validate_password(password: str) -> None:
    """Apply the shared password rules without silent bcrypt truncation."""
    validate_password_strength(password)
    if len(password.encode("utf-8")) > 72:
        raise_error("server.installation.passwordTooLong")


def hash_password(plain_text: str) -> str:
    """Hash a plaintext password using bcrypt with cost factor 12."""
    return bcrypt.hashpw(plain_text.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode(
        "utf-8"
    )


def verify_password(plain_text: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_text.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> None:
    """Validate password strength, raising an error on failure.

    Rules:
    - Minimum 8 characters
    - Must contain at least one letter
    - Must contain at least one digit
    """
    if len(password) < 8:
        raise_error("server.user.passwordTooShort")
    if not re.search(r"[a-zA-Z]", password):
        raise_error("server.user.passwordNeedsLetter")
    if not re.search(r"[0-9]", password):
        raise_error("server.user.passwordNeedsDigit")

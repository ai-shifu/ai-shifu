"""Password utility functions: hashing, verification, strength validation."""

from __future__ import annotations

import re

import bcrypt


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


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength.

    Rules:
    - Minimum 8 characters
    - Must contain at least one letter
    - Must contain at least one digit

    Returns (is_valid, error_message).
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r"[a-zA-Z]", password):
        return False, "Password must contain at least one letter"
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one digit"
    return True, ""

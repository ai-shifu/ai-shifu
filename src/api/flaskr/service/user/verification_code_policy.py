"""Shared policy for test-only universal verification codes."""

from __future__ import annotations

from flask import Flask

_PRODUCTION_ENVIRONMENTS = {"prod", "production"}
_TRUE_VALUES = {"true", "1", "yes", "on"}


def is_production_environment(app: Flask) -> bool:
    environment_values = (
        app.config.get("ENV"),
        app.config.get("MODE"),
        app.config.get("ENVIRONMENT"),
        app.config.get("ENVERIMENT"),
    )
    return any(
        str(value or "").strip().lower() in _PRODUCTION_ENVIRONMENTS
        for value in environment_values
    )


def _is_universal_verification_code_enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_VALUES
    return False


def get_enabled_universal_verification_code(app: Flask) -> str:
    """Return the universal code only when explicitly enabled outside production."""

    code = str(app.config.get("UNIVERSAL_VERIFICATION_CODE") or "").strip()
    if not code:
        return ""
    if not _is_universal_verification_code_enabled(
        app.config.get("UNIVERSAL_VERIFICATION_CODE_ENABLED", False)
    ):
        return ""
    if is_production_environment(app):
        return ""
    return code


def is_universal_verification_code_match(app: Flask, code: str) -> bool:
    """Return True when code matches the enabled universal verification code."""

    fix_code = get_enabled_universal_verification_code(app)
    return bool(fix_code) and code == fix_code

"""Shared policy for test-only universal verification codes."""

from __future__ import annotations

from flask import Flask

_PRODUCTION_ENVIRONMENTS = {"prod", "production"}


def is_production_environment(app: Flask) -> bool:
    environment = app.config.get("ENV") or app.config.get("MODE") or ""
    return str(environment).strip().lower() in _PRODUCTION_ENVIRONMENTS


def get_enabled_universal_verification_code(app: Flask) -> str:
    """Return the universal code only when explicitly enabled outside production."""

    code = str(app.config.get("UNIVERSAL_VERIFICATION_CODE") or "").strip()
    if not code:
        return ""
    if not bool(app.config.get("UNIVERSAL_VERIFICATION_CODE_ENABLED", False)):
        return ""
    if is_production_environment(app):
        return ""
    return code


def is_universal_verification_code_match(app: Flask, code: str) -> bool:
    """Return True when code matches the enabled universal verification code."""

    fix_code = get_enabled_universal_verification_code(app)
    return bool(fix_code) and code == fix_code

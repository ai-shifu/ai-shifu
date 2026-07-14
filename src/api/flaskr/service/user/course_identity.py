"""Course identity normalization for authentication workflows."""

from __future__ import annotations

from flask import Flask

from flaskr.service.shifu.api import resolve_shifu_identifier


def resolve_auth_course_id(app: Flask, course_id: str | None) -> str | None:
    """Return the canonical BID for a public course identifier when available."""

    normalized = str(course_id or "").strip()
    if not normalized:
        return None
    return resolve_shifu_identifier(app, normalized) or normalized

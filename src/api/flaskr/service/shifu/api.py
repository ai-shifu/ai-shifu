"""Stable cross-service API for public course identities."""

from .slug import (
    build_course_public_path,
    get_shifu_slug,
    resolve_shifu_identifier,
)

__all__ = [
    "build_course_public_path",
    "get_shifu_slug",
    "resolve_shifu_identifier",
]

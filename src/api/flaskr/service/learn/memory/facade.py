"""Access current course variables through the existing profile services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.profile.api import get_user_profiles, save_user_profiles

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.profile.dtos import ProfileToSave


def load_course_variables(app: Flask, user_bid: str, shifu_bid: str) -> dict[str, str]:
    """Read effective variables, including settings edits and canonical fields.

    Callers supply an authorized user/course context. Runtime profile resolution
    remains authoritative; the broad memory reader's ``elsewhere`` is not merged.
    """
    return get_user_profiles(app, user_bid, shifu_bid)


def stage_course_variables(
    app: Flask,
    user_bid: str,
    shifu_bid: str,
    assignments: list[ProfileToSave],
) -> bool:
    """Stage accepted assignments in the caller's existing app/DB context.

    Preserve the profile writer's normalization and in-place DTO mappings used
    by variable-update events. The caller owns the commit; this operation only
    delegates to the existing writer, which flushes the staged changes.
    """
    return save_user_profiles(app, user_bid, shifu_bid, assignments)

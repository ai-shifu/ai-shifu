"""Stable public entry points for cross-service profile operations."""

from flaskr.service.profile.learner_profile import (
    has_learner_profile_or_state,
    merge_learner_profile_for_sign_in,
)

__all__ = [
    "has_learner_profile_or_state",
    "merge_learner_profile_for_sign_in",
]

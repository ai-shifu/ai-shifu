"""Stable public entry points for cross-service profile operations."""

from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.profile.learner_profile import (
    LEARNER_PROFILE_MAX_LENGTH,
    LEARNER_PROFILE_NICKNAME_MAX_LENGTH,
    has_learner_profile_or_state,
    merge_learner_profile_for_sign_in,
)

__all__ = [
    "LEARNER_PROFILE_MAX_LENGTH",
    "LEARNER_PROFILE_NICKNAME_MAX_LENGTH",
    "get_user_profiles",
    "has_learner_profile_or_state",
    "merge_learner_profile_for_sign_in",
]

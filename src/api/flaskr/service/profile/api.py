"""Stable public entry points for cross-service profile operations."""

from flaskr.service.profile.learner_profile import merge_learner_profile_for_sign_in

__all__ = ["merge_learner_profile_for_sign_in"]

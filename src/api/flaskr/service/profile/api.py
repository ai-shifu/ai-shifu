"""Stable public entry points for cross-service profile operations."""

from flaskr.service.profile.constants import SYS_USER_LANGUAGE, SYS_USER_NICKNAME
from flaskr.service.profile.course_memory import (
    course_memory_deletion_state,
    delete_course_memory,
    list_course_memory,
)
from flaskr.service.profile.course_references import (
    COURSE_REFERENCE_PREFIX,
    SHARED_ANSWER_PREFIX,
    is_course_reference,
)
from flaskr.service.profile.funcs import (
    get_global_profile_keys,
    get_user_profiles,
    save_user_profiles,
)
from flaskr.service.profile.learner_profile import (
    LEARNER_PROFILE_MAX_LENGTH,
    LEARNER_PROFILE_NICKNAME_MAX_LENGTH,
    has_learner_profile_or_state,
    merge_learner_profile_for_sign_in,
)

__all__ = [
    "COURSE_REFERENCE_PREFIX",
    "LEARNER_PROFILE_MAX_LENGTH",
    "LEARNER_PROFILE_NICKNAME_MAX_LENGTH",
    "SHARED_ANSWER_PREFIX",
    "SYS_USER_LANGUAGE",
    "SYS_USER_NICKNAME",
    "course_memory_deletion_state",
    "delete_course_memory",
    "get_global_profile_keys",
    "get_user_profiles",
    "has_learner_profile_or_state",
    "is_course_reference",
    "list_course_memory",
    "merge_learner_profile_for_sign_in",
    "save_user_profiles",
]

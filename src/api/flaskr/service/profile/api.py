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
    is_course_reference_name,
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
from flaskr.service.profile.shared_answers import (
    SharedAnswer,
    load_shared_answers,
    shared_answer_names,
    stage_shared_answers,
)

__all__ = [
    "COURSE_REFERENCE_PREFIX",
    "LEARNER_PROFILE_MAX_LENGTH",
    "LEARNER_PROFILE_NICKNAME_MAX_LENGTH",
    "SHARED_ANSWER_PREFIX",
    "SYS_USER_LANGUAGE",
    "SYS_USER_NICKNAME",
    "SharedAnswer",
    "course_memory_deletion_state",
    "delete_course_memory",
    "get_global_profile_keys",
    "get_user_profiles",
    "has_learner_profile_or_state",
    "is_course_reference",
    "is_course_reference_name",
    "list_course_memory",
    "load_shared_answers",
    "merge_learner_profile_for_sign_in",
    "save_user_profiles",
    "shared_answer_names",
    "stage_shared_answers",
]

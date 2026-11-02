"""Stable public entry points for cross-service profile operations.

The profile service owns the account-backed learner fields (nickname, language,
learner profile) and the learner profile itself. Course-scoped learner memory
lives in :mod:`flaskr.service.memory`.
"""

from flaskr.service.profile.account_fields import (
    apply_core_mapping,
    check_text_content,
    current_core_value,
    ensure_user_aggregate,
    get_global_profile_keys,
    get_profile_labels,
    get_user_profile_labels,
    global_profile_value_versions,
    load_user_aggregate_without_credentials,
    update_aggregate_field,
)
from flaskr.service.profile.constants import (
    ACTIVE_SYSTEM_PROFILE_KEYS,
    SYS_USER_BACKGROUND,
    SYS_USER_LANGUAGE,
    SYS_USER_NICKNAME,
)
from flaskr.service.profile.learner_profile import (
    LEARNER_PROFILE_MAX_LENGTH,
    LEARNER_PROFILE_NICKNAME_MAX_LENGTH,
    apply_learner_profile_system_value,
    has_learner_profile_or_state,
    merge_learner_profile_for_sign_in,
    validate_learner_profile_system_value,
)
from flaskr.service.profile.profile_manage import get_profile_item_definition_list

__all__ = [
    "ACTIVE_SYSTEM_PROFILE_KEYS",
    "LEARNER_PROFILE_MAX_LENGTH",
    "LEARNER_PROFILE_NICKNAME_MAX_LENGTH",
    "SYS_USER_BACKGROUND",
    "SYS_USER_LANGUAGE",
    "SYS_USER_NICKNAME",
    "apply_core_mapping",
    "apply_learner_profile_system_value",
    "check_text_content",
    "current_core_value",
    "ensure_user_aggregate",
    "get_global_profile_keys",
    "get_profile_item_definition_list",
    "get_profile_labels",
    "get_user_profile_labels",
    "global_profile_value_versions",
    "has_learner_profile_or_state",
    "load_user_aggregate_without_credentials",
    "merge_learner_profile_for_sign_in",
    "update_aggregate_field",
    "validate_learner_profile_system_value",
]

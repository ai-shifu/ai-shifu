"""Write the learner settings page: account fields and the course's own values.

The settings form mixes account-backed system fields (see ``account_fields``)
with course-scoped custom values (see ``course_values``); this writer routes each
submitted field to its owner.
"""

import logging

from flask import Flask
from flaskr.dao import db
from flaskr.service.common import raise_error
from flaskr.service.profile.course_references import is_course_reference
from flaskr.service.profile.profile_manage import get_profile_item_definition_list
from flaskr.service.user.dtos import UserProfileLabelDTO, UserProfileLabelItemDTO
from flaskr.util.uuid import generate_id

from .account_fields import (
    apply_core_mapping,
    check_text_content,
    current_core_value,
    ensure_user_aggregate,
    get_profile_labels,
    update_aggregate_field,
)
from .constants import SYS_USER_BACKGROUND, SYS_USER_NICKNAME
from .course_values import (
    _get_latest_variable_value,
    _validate_profile_write_scope,
    load_scoped_values,
)
from .learner_profile import validate_learner_profile_system_value
from .models import VariableValue

logger = logging.getLogger(__name__)


def update_user_profile_with_lable(
    app: Flask,
    user_id: str,
    profiles: list,
    update_all: bool = False,
    course_id: str | None = None,
) -> bool:
    """Update user profile with lable."""
    app.logger.info(
        "update user profiles course_scoped=%s count=%s",
        bool(course_id),
        len(profiles.profiles or [])
        if isinstance(profiles, UserProfileLabelDTO)
        else 1
        if isinstance(profiles, UserProfileLabelItemDTO)
        else len(profiles),
    )
    profile_labels = get_profile_labels()
    if isinstance(profiles, UserProfileLabelDTO):
        profiles = profiles.profiles or []
    elif isinstance(profiles, UserProfileLabelItemDTO):
        profiles = [profiles]

    if profiles and isinstance(profiles[0], UserProfileLabelItemDTO):
        profiles = [item.__json__() for item in profiles]

    course_id = _validate_profile_write_scope(
        [profile.get("key") for profile in profiles], course_id
    )
    for profile in profiles:
        if profile.get("key") == SYS_USER_BACKGROUND:
            profile["value"] = validate_learner_profile_system_value(
                app,
                user_id=user_id,
                learner_profile=profile.get("value"),
            )

    aggregate = ensure_user_aggregate(user_id)
    profile_items = get_profile_item_definition_list(app, course_id)

    if not profiles:
        db.session.flush()
        return True

    nickname = next((p for p in profiles if p.get("key") == SYS_USER_NICKNAME), None)
    if nickname and not check_text_content(app, user_id, nickname.get("value")):
        raise_error("server.common.nicknameNotAllowed")

    user_values = load_scoped_values(app, user_id, course_id)

    for profile in profiles:
        key = profile.get("key")
        if not key or is_course_reference(key):
            continue
        profile_value = profile.get("value")
        profile_item = next(
            (
                item
                for item in profile_items
                if item.profile_key == key or item.profile_id == profile.get("id")
            ),
            None,
        )

        profile_lable = profile_labels.get(key, None)
        default_value = profile_lable.get("default", None) if profile_lable else None

        if profile_lable and profile_lable.get("items_mapping"):
            for source_value, mapped in profile_lable["items_mapping"].items():
                if mapped == profile_value:
                    profile_value = source_value
                    break

        mapping = profile_lable.get("mapping") if profile_lable else None
        mapping_already_applied = False
        if mapping == "learner_profile":
            profile_value = apply_core_mapping(
                user_id,
                mapping,
                profile_value,
            )
            update_aggregate_field(aggregate, mapping, profile_value)
            mapping_already_applied = True
        if mapping and (
            not mapping_already_applied
            and (
                update_all
                or (
                    profile_value != default_value
                    and current_core_value(aggregate, mapping) != profile_value
                )
            )
        ):
            normalized = apply_core_mapping(user_id, mapping, profile_value)
            update_aggregate_field(aggregate, mapping, normalized)

        # System variables (in profile_labels) are global; custom variables
        # are scoped to the course.  This must match save_user_profiles() so
        # that the run interface reads the same value the settings page wrote.
        target_shifu = "" if key in profile_labels else (course_id or "")

        should_persist_value = key == SYS_USER_BACKGROUND or (
            profile_value not in (None, "") and profile_value != default_value
        )
        if should_persist_value:
            latest_value = _get_latest_variable_value(
                user_values,
                variable_key=key,
                shifu_bid=target_shifu,
            )
            if latest_value is None or latest_value.value != profile_value:
                variable_bid = profile_item.profile_id if profile_item else ""
                new_value = VariableValue(
                    variable_value_bid=generate_id(app),
                    user_bid=user_id,
                    shifu_bid=target_shifu,
                    variable_bid=variable_bid,
                    key=key,
                    value=str(profile_value) if profile_value is not None else "",
                    deleted=0,
                )
                db.session.add(new_value)
                user_values.insert(0, new_value)
    db.session.flush()
    return True

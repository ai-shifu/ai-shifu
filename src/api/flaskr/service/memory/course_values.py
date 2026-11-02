"""Learner variable values stored per course, and the global rows of system keys.

Custom keys are scoped to the course (``shifu_bid=course_id``); registered system
keys are global (``shifu_bid=''``) and mirror the account-backed fields.
"""

from flask import Flask
from flaskr.dao import db
from flaskr.service.common.models import raise_param_error
from flaskr.service.memory.course_references import is_course_reference
from flaskr.service.profile.api import (
    ACTIVE_SYSTEM_PROFILE_KEYS,
    SYS_USER_BACKGROUND,
    SYS_USER_LANGUAGE,
    SYS_USER_NICKNAME,
    apply_core_mapping,
    apply_learner_profile_system_value,
    current_core_value,
    ensure_user_aggregate,
    get_profile_item_definition_list,
    get_profile_labels,
    update_aggregate_field,
    validate_learner_profile_system_value,
)
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.repository import load_user_aggregate
from flaskr.util.uuid import generate_id


def _get_latest_variable_value(
    values: list[VariableValue],
    variable_key: str,
    shifu_bid: str,
) -> VariableValue | None:
    """Return the newest variable value row from a pre-fetched, id-desc sorted collection.

    Matching is by key only (not variable_bid) so the newest row for the
    logical profile field wins even if the underlying Variable definition was
    recreated and now has a different variable_bid.

    Match only the requested scope. Callers select the empty scope for registered
    system fields; a missing course value never falls back to a global custom value.
    """
    target_shifu = shifu_bid or ""
    return next(
        (
            item
            for item in values
            if item.shifu_bid == target_shifu and item.key == variable_key
        ),
        None,
    )


def load_scoped_values(app: Flask, user_id: str, course_id: str) -> list[VariableValue]:
    """Load the user's live value rows for the course and global scopes, newest first."""
    candidate_shifus = [course_id or ""]
    if course_id:
        candidate_shifus.append("")
    try:
        return (
            VariableValue.query.filter(
                VariableValue.user_bid == user_id,
                VariableValue.deleted == 0,
                VariableValue.shifu_bid.in_(candidate_shifus),
            )
            .order_by(VariableValue.id.desc())
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load var_variable_values: %s", exc)
        return []


def _validate_profile_write_scope(keys: list[str], course_id: str | None) -> str:
    """Require an explicit course before any custom-variable write is staged."""
    normalized_course_id = course_id.strip() if isinstance(course_id, str) else ""
    if not normalized_course_id and any(
        key and key not in ACTIVE_SYSTEM_PROFILE_KEYS and not is_course_reference(key)
        for key in keys
    ):
        raise_param_error("course_id")
    return normalized_course_id


def save_user_profiles(
    app: Flask, user_id: str, course_id: str, profiles: list[ProfileToSave]
) -> bool:
    """Persist user profiles."""
    course_id = _validate_profile_write_scope(
        [profile.key for profile in profiles], course_id
    )
    profile_labels = get_profile_labels()
    app.logger.info("save user profiles count=%s", len(profiles))
    for profile in profiles:
        if profile.key == SYS_USER_BACKGROUND:
            profile.value = validate_learner_profile_system_value(
                app,
                user_id=user_id,
                learner_profile=profile.value,
            )
    aggregate = ensure_user_aggregate(user_id)
    profiles_items = get_profile_item_definition_list(app, course_id)

    user_values = load_scoped_values(app, user_id, course_id)

    for profile in profiles:
        if is_course_reference(profile.key):
            continue
        profile_item = next(
            (item for item in profiles_items if item.profile_key == profile.key), None
        )
        variable_bid = (profile.bid or "").strip() or (
            profile_item.profile_id if profile_item else ""
        )
        target_shifu = "" if profile.key in profile_labels else (course_id or "")

        if profile.key == SYS_USER_BACKGROUND:
            profile.value = apply_learner_profile_system_value(
                user_id=user_id,
                learner_profile=str(profile.value or ""),
            )
            update_aggregate_field(aggregate, "learner_profile", profile.value)

        latest_value = _get_latest_variable_value(
            user_values,
            variable_key=profile.key,
            shifu_bid=target_shifu,
        )
        if not latest_value or latest_value.value != profile.value:
            user_value = VariableValue(
                variable_value_bid=generate_id(app),
                user_bid=user_id,
                shifu_bid=target_shifu,
                variable_bid=variable_bid,
                key=profile.key,
                value=profile.value or "",
                deleted=0,
            )
            db.session.add(user_value)
            user_values.insert(0, user_value)

        if profile.key in profile_labels and profile.key != SYS_USER_BACKGROUND:
            profile_lable = profile_labels[profile.key]
            if profile_lable.get("mapping"):
                normalized = apply_core_mapping(
                    user_id,
                    profile_lable["mapping"],
                    profile.value,
                )
                update_aggregate_field(aggregate, profile_lable["mapping"], normalized)

    db.session.flush()
    return True


def get_user_profiles(
    app: Flask,
    user_id: str,
    course_id: str,
    *,
    reference_text: str | tuple[str, ...] = "",
) -> dict:
    """Get user profiles for Mdflow run.

    Note:
    - Some profile keys ("labels") are stored globally with ``shifu_bid=''``.
    - Other profile keys are stored per-course with ``shifu_bid=course_id``.

    This function must follow the same shifu_bid routing rules as
    :func:`save_user_profiles`, otherwise the run context may see values different
    from what the user sees in the personal settings page.

    Author documents cannot grant access to another course. ``reference_text``
    remains a compatibility argument and never changes the selected storage scope.

    """
    _ = reference_text  # Kept for call-site compatibility; author text grants no scope.
    profile_labels = get_profile_labels()
    profiles_items = get_profile_item_definition_list(app, course_id)

    user_values = load_scoped_values(app, user_id, course_id)

    aggregate = load_user_aggregate(user_id, with_credentials=False)

    result: dict[str, str] = {}
    for profile_item in profiles_items:
        if is_course_reference(profile_item.profile_key) or (
            not course_id and profile_item.profile_key not in ACTIVE_SYSTEM_PROFILE_KEYS
        ):
            continue
        # Follow save_user_profiles routing: label keys are global, others per-course.
        target_shifu = (
            "" if profile_item.profile_key in profile_labels else (course_id or "")
        )

        user_value = (
            _get_latest_variable_value(
                user_values,
                variable_key=profile_item.profile_key,
                shifu_bid=target_shifu,
            )
            if user_values
            else None
        )
        if user_value:
            result[profile_item.profile_key] = user_value.value

    # Keep runtime variable resolution aligned with /api/user/get_profile:
    # mapped system fields should use the latest canonical user entity values.
    if aggregate:
        for key, profile_label in profile_labels.items():
            mapping = profile_label.get("mapping")
            if not mapping:
                continue
            raw_value = current_core_value(aggregate, mapping)
            if raw_value is None:
                continue
            result[key] = str(raw_value)
        # Runtime prompt variables must stay consistent with canonical user fields.
        result[SYS_USER_LANGUAGE] = aggregate.user_language
        result[SYS_USER_NICKNAME] = aggregate.nickname or ""

    # The historical variable row is write-only compatibility data.  Even a
    # missing aggregate must not make it the runtime source of truth again.
    result[SYS_USER_BACKGROUND] = aggregate.learner_profile if aggregate else ""

    # Ensure system variables are always available.
    if result.get(SYS_USER_LANGUAGE) is None:
        result[SYS_USER_LANGUAGE] = aggregate.user_language if aggregate else "en-US"

    if not result.get(SYS_USER_NICKNAME):
        result[SYS_USER_NICKNAME] = aggregate.nickname if aggregate else ""

    return result
